"""Base model and model lifecycle abstractions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .fields import AutoField, Field
from .meta import MetaOptions
from .registry import ModelRegistry
from .relationships import ManyToManyField

logger = logging.getLogger(__name__)


class ObjectDoesNotExist(Exception):
    """Raised when a query does not return any results."""
    pass


class MultipleObjectsReturned(Exception):
    """Raised when a query returns more than one result when only one was expected."""
    pass


class ConcurrencyError(Exception):
    """Raised when an optimistic lock fails due to concurrent modification."""
    pass


class ModelMeta(type):
    """Metaclass that collects field definitions and builds _meta."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        meta_attrs = {}
        meta_cls = namespace.get("Meta")
        if meta_cls is not None:
            for attr in ("table_name", "app_label", "indexes", "constraints", "ordering", "abstract", "managed"):
                if hasattr(meta_cls, attr):
                    meta_attrs[attr] = getattr(meta_cls, attr)

        fields = {}
        # Replace ManyToManyField with descriptor before class creation
        from .relationships import ManyToManyField

        class _M2MDescriptor:
            """Descriptor that returns a ManyToManyManager on instance access."""
            def __init__(self, field: ManyToManyField) -> None:
                self.field = field

            def __get__(self, instance: Any, owner: Any):
                if instance is None:
                    return self.field
                from .m2m import ManyToManyManager
                return ManyToManyManager(instance, self.field)

            def __set__(self, instance: Any, value: Any) -> None:
                raise AttributeError("Cannot assign to ManyToManyField directly. Use manager methods (add, remove, clear).")

        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                value.name = key
                if hasattr(value, "__post_init__"):
                    value.__post_init__()
                fields[key] = value
                if isinstance(value, ManyToManyField):
                    # Install descriptor in the class namespace
                    namespace[key] = _M2MDescriptor(value)

        cls = super().__new__(mcs, name, bases, namespace)

        # Ensure every model class has its own table creation tracking flag
        cls._table_created = False

        if name != "Model":
            for base in bases:
                if hasattr(base, "_meta") and hasattr(base._meta, "fields"):
                    for fname, fobj in base._meta.fields.items():
                        if fname not in fields:
                            fields[fname] = fobj

            has_pk = any(f.primary_key for f in fields.values())
            if not has_pk:
                auto = AutoField()
                auto.name = "id"
                # Add version field for optimistic locking
                if "version" not in fields:
                    from mikiorm.models.fields import IntegerField
                    fields["version"] = IntegerField(default=1, null=False)
                fields["id"] = auto

            meta_options = MetaOptions(**meta_attrs)
            meta_options.fields = fields
            cls._meta = meta_options  # type: ignore[attr-defined]

            from ..managers.base import Manager, ManagerDescriptor
            has_custom_manager = any(
                isinstance(namespace.get(attr_name), Manager)
                for attr_name in namespace
            )
            if not has_custom_manager:
                cls._default_manager = Manager(cls)
            cls.objects = ManagerDescriptor()  # type: ignore[assignment]

            ModelRegistry.register_model(cls)

            # Install reverse ManyToMany descriptors for any M2M field on this model
            # that defines a related_name. The descriptor is attached to the target model.
            for fname, field in fields.items():
                if isinstance(field, ManyToManyField) and field.related_name:
                    # Determine target model class
                    target = field.to
                    if isinstance(target, str):
                        target_cls = ModelRegistry.get_model(target)
                        if target_cls is None:
                            # Target not yet registered; skip for now; will be wired later
                            continue
                    else:
                        target_cls = target
                    from .m2m import ReverseManyToManyDescriptor
                    setattr(target_cls, field.related_name, ReverseManyToManyDescriptor(field, cls))

            # Install reverse FK/OneToOne descriptors for models referenced via ForeignKey/OneToOneField
            from .relationships import (
                ForeignKey,
                OneToOneField,
                ReverseForeignKeyDescriptor,
                ReverseOneToOneDescriptor,
            )

            for fname, field in fields.items():
                if (
                    isinstance(field, (ForeignKey, OneToOneField))
                    and field.related_name
                ):
                    target = field.to
                    if isinstance(target, str):
                        target_cls = ModelRegistry.get_model(target)
                        if target_cls is None:
                            continue
                    else:
                        target_cls = target
                    descriptor = (
                        ReverseOneToOneDescriptor(field, cls)
                        if isinstance(field, OneToOneField)
                        else ReverseForeignKeyDescriptor(field, cls)
                    )
                    setattr(target_cls, field.related_name, descriptor)

            # Install forward descriptors for ForeignKey/OneToOneField so that
            # attribute access returns the related instance instead of the raw PK.
            from .relationships import ForwardForeignKeyDescriptor

            for fname, field in fields.items():
                if isinstance(field, (ForeignKey, OneToOneField)):
                    setattr(cls, fname, ForwardForeignKeyDescriptor(field))

        return cls

        return cls


def register(*models: type[Model], app_label: str | None = None) -> Any:
    """
    Universal standard way to register models. 
    Can be used as a decorator or a function call.
    
    This ensures models in any folder are discovered for migrations 
    as long as the file is imported once or the folder is listed in MODEL_PATHS.

    Usage:
        @register
        class User(Model): ...
        
        @register(app_label="catalog")
        class Product(Model): ...

        register(OtherModel, AnotherModel)
    """
    def _register_single(model: type[Model]) -> type[Model]:
        # Determine app_label if not explicitly set in Meta
        if hasattr(model, "_meta"):
            # Priority: explicit argument > Meta attribute > module inference
            if app_label is not None:
                model._meta.app_label = app_label

            if model._meta.app_label is None:
                module_name = model.__module__
                if ".models" in module_name:
                    # Extract app name from 'app.models.module'
                    inferred_label = module_name.split(".models")[0].split(".")[-1]
                else:
                    # Fallback to the top-level package name or module name
                    inferred_label = module_name.split(".")[0]
                model._meta.app_label = inferred_label

        ModelRegistry.register_model(model)
        return model

    if not models:
        # Used as @register(app_label="...")
        return _register_single

    for model in models:
        _register_single(model)

    if len(models) == 1:
        return models[0]
    return None

class Model(metaclass=ModelMeta):
    """Base model class with ORM-like behaviour."""

    _meta: MetaOptions
    _saved: bool = False
    _table_created: bool = False # Initialize for all models
    version: int = 1 # Default for optimistic locking

    @property
    def pk(self) -> Any:
        pk_name, pk_field = self._get_pk_field()
        return getattr(self, pk_name, None)

    def __init__(self, **kwargs: Any) -> None:
        from .relationships import ManyToManyField
        for field_name, field_obj in self._meta.fields.items():
            # Skip ManyToMany fields; they are managed via descriptor
            if isinstance(field_obj, ManyToManyField):
                continue
            if field_name == "version" and "version" not in kwargs:
                value = 1 # Initialize version for new objects
            value = kwargs.get(field_name, field_obj.default)
            if callable(value) and not isinstance(value, Field):
                value = value()
            value = field_obj.python_value(value)
            value = field_obj.validate(value)
            setattr(self, field_name, value)
        self._saved = False

    def _get_connection(self) -> Any:
        from ..conf.settings import connection_manager

        return connection_manager.get_connection()

    def _get_pk_field(self) -> tuple[str, Field]:
        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                return name, field_obj
        return "id", self._meta.fields["id"]

    def _build_insert(self) -> tuple[str, list[Any]]:
        from .fields import AutoField, DateTimeField
        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        cols = []
        vals = []

        for name, field_obj in self._meta.fields.items():
            if isinstance(field_obj, AutoField) and field_obj.primary_key:
                continue
            value = getattr(self, name, None)
            if isinstance(field_obj, DateTimeField) and field_obj.auto_now_add:
                if value is None or value == datetime.min:
                    value = datetime.now(timezone.utc)
                    setattr(self, name, value)
            elif isinstance(field_obj, DateTimeField) and field_obj.auto_now:
                value = datetime.now(timezone.utc)
                setattr(self, name, value)
            db_value = field_obj.db_value(value)
            cols.append(builder.quote_column(name))
            vals.append(db_value)

        ph = builder.param_placeholder
        placeholders = ", ".join(ph for _ in cols)
        col_names = ", ".join(cols)
        quoted_table = builder.quote_table(table)
        sql = f"INSERT INTO {quoted_table} ({col_names}) VALUES ({placeholders})"
        return sql, vals

    def _build_update(self) -> tuple[str, list[Any]]:
        from .fields import DateTimeField
        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        sets = []
        vals = []

        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                continue
            if name == "version": # Handle version field for optimistic locking
                sets.append(f"{builder.quote_column(name)} = {builder.quote_column(name)} + 1")
                continue

            value = getattr(self, name, None)
            if isinstance(field_obj, DateTimeField) and field_obj.auto_now:
                value = datetime.now(timezone.utc)
                setattr(self, name, value)
            db_value = field_obj.db_value(value) # type: ignore
            ph = builder.param_placeholder
            quoted_col = builder.quote_column(name)
            sets.append(f"{quoted_col} = {ph}")
            vals.append(db_value)

        vals.append(pk_value)
        quoted_pk = builder.quote_column(pk_name)
        quoted_table = builder.quote_table(table)
        ph = builder.param_placeholder # type: ignore
        sql = f"UPDATE {quoted_table} SET {', '.join(sets)} WHERE {quoted_pk} = {ph} AND {builder.quote_column('version')} = {ph}"
        return sql, vals

    def _execute_insert(self, connection: Any) -> None:
        sql, params = self._build_insert()
        logger.debug(f"Executing INSERT: {sql} with params: {params}")
        cursor = connection.execute(sql, params)
        if hasattr(cursor, "lastrowid") and cursor.lastrowid:
            pk_name, _ = self._get_pk_field()
            setattr(self, pk_name, cursor.lastrowid)
        self._saved = True
        logger.debug(f"Inserted {self.__class__.__name__} pk={self.pk}")

    def _execute_update(self, connection: Any) -> None:
        sql, params = self._build_update()
        # Add current version to params for optimistic locking WHERE clause
        params.append(self.version)
        logger.debug(f"Executing UPDATE: {sql} with params: {params}")
        cursor = connection.execute(sql, params)
        if cursor.rowcount == 0:
            raise ConcurrencyError(f"Optimistic lock failed for {self.__class__.__name__} pk={self.pk}. Record was modified concurrently.")
        self._saved = True
        self.version += 1 # Increment local version to match DB
        logger.debug(f"Updated {self.__class__.__name__} pk={self.pk}")

    def _execute_delete(self, connection: Any) -> None:
        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))
        table = self._meta.table_name or self.__class__.__name__.lower() + "s"

        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        quoted_table = builder.quote_table(table)
        quoted_pk = builder.quote_column(pk_name)
        ph = builder.param_placeholder
        sql = f"DELETE FROM {quoted_table} WHERE {quoted_pk} = {ph}"
        connection.execute(sql, (pk_value,))
        self._saved = False
        logger.debug(f"Deleted {self.__class__.__name__} pk={pk_value}")

    def _ensure_table_exists(self, connection: Any) -> None:
        if self.__class__._table_created:
            return
        from ..models.fields import (
            CharField, TextField, BooleanField, IntegerField,
            BigIntegerField, SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField,
            AutoField, FloatField, DecimalField, DurationField, DateTimeField, DateField,
            TimeField, UUIDField, JSONField, BinaryField, EmailField, URLField, SlugField,
            GenericIPAddressField, FilePathField
        )
        from ..models.relationships import ForeignKey, ManyToManyField
        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        quoted_table = builder.quote_table(table)

        col_defs = []
        for fname, fobj in self._meta.fields.items():
            # Skip virtual fields like ManyToManyField
            if isinstance(fobj, ManyToManyField):
                continue
            quoted_col = builder.quote_column(fname)
            if isinstance(fobj, AutoField) or (fobj.primary_key and isinstance(fobj, (IntegerField, AutoField))):
                sql_type = "INTEGER"
                constraints = ["PRIMARY KEY", "AUTOINCREMENT"]
            elif isinstance(fobj, ForeignKey):
                sql_type = "INTEGER"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, BigIntegerField):
                sql_type = "BIGINT"
                constraints = ["PRIMARY KEY"] if fobj.primary_key else ([] if fobj.null else ["NOT NULL"])
            elif isinstance(fobj, (IntegerField, SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField)):
                sql_type = "INTEGER"
                constraints = []
                if fobj.primary_key:
                    constraints.append("PRIMARY KEY")
                constraints.append("NOT NULL" if not fobj.null else "NULL")
            elif isinstance(fobj, CharField):
                ml = fobj.max_length or 255
                sql_type = f"VARCHAR({ml})"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, TextField):
                sql_type = "TEXT"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, BooleanField):
                sql_type = "INTEGER"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL", "DEFAULT 0"]
            elif isinstance(fobj, FloatField):
                sql_type = "REAL"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, DecimalField):
                sql_type = f"DECIMAL({fobj.max_digits}, {fobj.decimal_places})"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, DurationField):
                sql_type = "BIGINT"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, DateTimeField):
                sql_type = "DATETIME"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, DateField):
                sql_type = "DATE"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, TimeField):
                sql_type = "TIME"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, UUIDField):
                sql_type = "VARCHAR(36)"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, JSONField):
                sql_type = "TEXT"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, BinaryField):
                sql_type = "BLOB"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, EmailField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, URLField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, SlugField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, GenericIPAddressField):
                sql_type = "VARCHAR(45)"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, FilePathField):
                sql_type = "VARCHAR(255)"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            else:
                sql_type = "TEXT"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]

            if fobj.unique:
                constraints.append("UNIQUE")

            col_def = f"    {quoted_col} {sql_type} {' '.join(constraints)}"
            col_defs.append(col_def)

        sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} (\n{',\n'.join(col_defs)}\n)"
        try:
            logger.debug(f"Creating table: {sql}")
            connection.execute(sql, ())
            connection.commit()
            self.__class__._table_created = True
            logger.info(f"Created table {quoted_table} for {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Failed to create table {quoted_table}: {e}", exc_info=True)

    def save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Persist this model instance.

        When used within an atomic() block, changes are buffered and
        committed as a single unit when the transaction exits. Outside
        atomic(), each save commits immediately.
        """
        from ..unit_of_work.transaction import TransactionManager

        tx = TransactionManager.get_current()
        conn = connection or self._get_connection()

        # Defer to unit of work if inside atomic
        if tx is not None and tx.connection is conn:
            if not self._saved or force_insert:
                tx.tracker.register_new(self)
            else:
                tx.tracker.register_dirty(self)
            return

        # Immediate execution
        self.full_clean()
        self._ensure_table_exists(conn)
        try:
            if not self._saved or force_insert:
                self._execute_insert(conn)
            else:
                self._execute_update(conn)
        except Exception as e:
            logger.warning(
                f"INSERT failed for {self.__class__.__name__}: {e}. "
                f"Attempting UPDATE instead."
            )
            self._execute_update(conn)
        conn.commit()
        # Release the connection back to the pool if it's pooled
        if connection is None and hasattr(conn, 'close'):
            conn.close()

    def delete(self, connection: Any = None) -> None:
        """Delete this model instance.

        Inside an atomic() block, the deletion is deferred until commit.
        """
        from ..unit_of_work.transaction import TransactionManager

        tx = TransactionManager.get_current()
        conn = connection or self._get_connection()

        if tx is not None and tx.connection is conn:
            from .unit_of_work.tracker import UnitOfWorkTracker
            tx.tracker.register_deleted(self)
            return

        self._execute_delete(conn)
        conn.commit()
        # Release the connection back to the pool if it's pooled
        if connection is None and hasattr(conn, 'close'):
            conn.close()

    async def async_save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Asynchronously persist this model instance.

        When used within an async with atomic() block, changes are buffered.
        Outside atomic(), each save commits immediately.
        """
        from ..unit_of_work.transaction import AsyncTransactionManager
        from ..settings import async_connection_manager

        tx = AsyncTransactionManager.get_current()
        conn = connection or await async_connection_manager.get_connection()

        # Defer to unit of work if inside async atomic
        if tx is not None and tx.connection is conn:
            if not self._saved or force_insert:
                tx.tracker.register_new(self)
            else:
                tx.tracker.register_dirty(self)
            return

        # Immediate execution
        self.full_clean()
        await self._async_ensure_table_exists(conn)
        try:
            if not self._saved or force_insert:
                await self._async_execute_insert(conn)
            else:
                await self._async_execute_update(conn)
        except Exception as e:
            logger.warning(
                f"INSERT failed for {self.__class__.__name__}: {e}. "
                f"Attempting UPDATE instead."
            )
            await self._async_execute_update(conn)
        await conn.commit()

    async def async_delete(self, connection: Any = None) -> None:
        """Asynchronously delete this model instance.

        Inside an async atomic() block, the deletion is deferred until commit.
        """
        from ..unit_of_work.transaction import AsyncTransactionManager
        from ..settings import async_connection_manager

        tx = AsyncTransactionManager.get_current()
        conn = connection or await async_connection_manager.get_connection()

        if tx is not None and tx.connection is conn:
            from .unit_of_work.tracker import UnitOfWorkTracker
            tx.tracker.register_deleted(self)
            return

        await self._async_execute_delete(conn)
        await conn.commit()

    async def _async_execute_insert(self, connection: Any) -> None:
        """Async version of _execute_insert."""
        sql, params = self._build_insert()
        logger.debug(f"Executing INSERT: {sql} with params: {params}")
        cursor = await connection.execute(sql, params)
        if hasattr(cursor, "lastrowid") and cursor.lastrowid:
            pk_name, _ = self._get_pk_field()
            setattr(self, pk_name, cursor.lastrowid)
        self._saved = True
        logger.debug(f"Inserted {self.__class__.__name__} pk={self.pk}")

    async def _async_execute_update(self, connection: Any) -> None:
        """Async version of _execute_update."""
        sql, params = self._build_update()
        logger.debug(f"Executing UPDATE: {sql} with params: {params}")
        params.append(self.version) # Add current version for optimistic locking
        cursor = await connection.execute(sql, params)
        if cursor.rowcount == 0:
            raise ConcurrencyError(
                f"Optimistic lock failed for {self.__class__.__name__} pk={self.pk}. Record was modified concurrently."
            )
        self._saved = True
        logger.debug(f"Updated {self.__class__.__name__} pk={self.pk}")

    async def _async_execute_delete(self, connection: Any) -> None:
        """Async version of _execute_delete."""
        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))
        table = self._meta.table_name or self.__class__.__name__.lower() + "s"

        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        quoted_table = builder.quote_table(table)
        quoted_pk = builder.quote_column(pk_name)
        ph = builder.param_placeholder
        sql = f"DELETE FROM {quoted_table} WHERE {quoted_pk} = {ph}"
        await connection.execute(sql, (pk_value,))
        self._saved = False
        logger.debug(f"Deleted {self.__class__.__name__} pk={pk_value}")

    async def _async_ensure_table_exists(self, connection: Any) -> None:
        """Async version of _ensure_table_exists."""
        if self.__class__._table_created:
            return
        from ..models.fields import (
            CharField, TextField, BooleanField, IntegerField,
            BigIntegerField, SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField,
            AutoField, FloatField, DecimalField, DurationField, DateTimeField, DateField,
            TimeField, UUIDField, JSONField, BinaryField, EmailField, URLField, SlugField,
            GenericIPAddressField, FilePathField
        )
        from ..models.relationships import ForeignKey, ManyToManyField
        from ..query.safe_builder import get_safe_builder
        from ..conf.settings import settings

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        quoted_table = builder.quote_table(table)

        col_defs = []
        for fname, fobj in self._meta.fields.items():
            # Skip virtual fields like ManyToManyField
            if isinstance(fobj, ManyToManyField):
                continue
            quoted_col = builder.quote_column(fname)
            if isinstance(fobj, AutoField) or (fobj.primary_key and isinstance(fobj, (IntegerField, AutoField))):
                sql_type = "INTEGER"
                constraints = ["PRIMARY KEY", "AUTOINCREMENT"]
            elif isinstance(fobj, ForeignKey):
                sql_type = "INTEGER"
                constraints = ["NOT NULL"] if not fobj.null else ["NULL"]
            elif isinstance(fobj, BigIntegerField):
                sql_type = "BIGINT"
                constraints = ["PRIMARY KEY"] if fobj.primary_key else ([] if fobj.null else ["NOT NULL"])
            elif isinstance(fobj, (IntegerField, SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField)):
                sql_type = "INTEGER"
                constraints = []
                if fobj.primary_key:
                    constraints.append("PRIMARY KEY")
                constraints.append("NOT NULL" if not fobj.null else "NULL")
            elif isinstance(fobj, CharField):
                ml = fobj.max_length or 255
                sql_type = f"VARCHAR({ml})"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, TextField):
                sql_type = "TEXT"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, BooleanField):
                sql_type = "INTEGER"
                constraints = ["NOT NULL" if not fobj.null else "NULL", "DEFAULT 0"]
            elif isinstance(fobj, FloatField):
                sql_type = "REAL"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, DecimalField):
                sql_type = f"DECIMAL({fobj.max_digits}, {fobj.decimal_places})"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, DurationField):
                sql_type = "BIGINT"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, DateTimeField):
                sql_type = "DATETIME"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, DateField):
                sql_type = "DATE"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, TimeField):
                sql_type = "TIME"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, UUIDField):
                sql_type = "VARCHAR(36)"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, JSONField):
                sql_type = "TEXT"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, BinaryField):
                sql_type = "BLOB"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, EmailField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, URLField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, SlugField):
                sql_type = f"VARCHAR({fobj.max_length})"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, GenericIPAddressField):
                sql_type = "VARCHAR(45)"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            elif isinstance(fobj, FilePathField):
                sql_type = "VARCHAR(255)"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]
            else:
                sql_type = "TEXT"
                constraints = ["NOT NULL" if not fobj.null else "NULL"]

            if fobj.unique:
                constraints.append("UNIQUE")

            col_def = f"    {quoted_col} {sql_type} {' '.join(constraints)}"
            col_defs.append(col_def)

        sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} (\n{',\n'.join(col_defs)}\n)"
        try:
            logger.debug(f"Creating table: {sql}")
            await connection.execute(sql, ())
            await connection.commit()
            self.__class__._table_created = True
            logger.info(f"Created table {quoted_table} for {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Failed to create table {quoted_table}: {e}", exc_info=True)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._meta.fields}

    def refresh_from_db(self, connection: Any = None) -> None:
        """Reload this instance from the database."""
        conn = connection or self._get_connection()
        pk_name, pk_field = self._get_pk_field()
        pk_value = getattr(self, pk_name)
        if pk_value is None:
            raise ValueError("Cannot refresh unsaved instance")
        queryset = self.__class__.objects.filter(**{pk_name: pk_value})
        try:
            fresh = queryset.get()
            for name in self._meta.fields:
                setattr(self, name, getattr(fresh, name))
        except ObjectDoesNotExist:
            raise ObjectDoesNotExist(
                f"{self.__class__.__name__} with {pk_name}={pk_value} does not exist"
            )

    def full_clean(self) -> None:
        for name, field_obj in self._meta.fields.items():
            if isinstance(field_obj, ManyToManyField):
                continue
            value = getattr(self, name, None)
            if callable(value) and not isinstance(value, Field):
                value = value()
            valid_value = field_obj.validate(field_obj.python_value(value))
            setattr(self, name, valid_value)

    @classmethod
    def objects(cls) -> Any:
        from ..managers.base import Manager
        if not hasattr(cls, "_manager"):
            cls._manager = Manager(cls)
        return cls._manager

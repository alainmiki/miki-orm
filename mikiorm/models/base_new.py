"""Base model class with ORM-like behaviour - refactored for Unit of Work."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from .fields import AutoField, DateTimeField, Field
from .meta import MetaOptions
from .registry import ModelRegistry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .base import Model  # for self type hints


class ObjectDoesNotExist(Exception):
    pass


class MultipleObjectsReturned(Exception):
    pass


class ModelMeta(type):
    # ... unchanged from original ModelMeta code (keep as is)
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        meta_attrs = {}
        meta_cls = namespace.get("Meta")
        if meta_cls is not None:
            for attr in ("table_name", "indexes", "constraints", "ordering", "abstract", "managed"):
                if hasattr(meta_cls, attr):
                    meta_attrs[attr] = getattr(meta_cls, attr)

        fields = {}
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                value.name = key
                if hasattr(value, "__post_init__"):
                    value.__post_init__()
                fields[key] = value

        cls = super().__new__(mcs, name, bases, namespace)

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
                fields["id"] = auto

            meta_options = MetaOptions(**meta_attrs)
            meta_options.fields = fields
            cls._meta = meta_options

            from ..managers.base import Manager, ManagerDescriptor

            has_custom_manager = False
            for attr_name in namespace:
                if isinstance(namespace[attr_name], Manager):
                    has_custom_manager = True
                    break
            if not has_custom_manager:
                cls._default_manager = Manager(cls)
            cls.objects = ManagerDescriptor()

            ModelRegistry.register_model(cls)

        return cls


class Model(metaclass=ModelMeta):
    _meta: MetaOptions
    _saved: bool = False

    def __init__(self, **kwargs: Any) -> None:
        for field_name, field_obj in self._meta.fields.items():
            value = kwargs.get(field_name, field_obj.default)
            if callable(value) and not isinstance(value, Field):
                value = value()
            setattr(self, field_name, field_obj.python_value(value))
        self._saved = False

    # Note: _get_connection is used by both immediate and UOW modes, so we can't
    # directly import connection_manager there to avoid circular imports. We'll
    # do a lazy import inside methods.

    def _get_pk_field(self) -> tuple[str, Field]:
        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                return name, field_obj
        return "id", self._meta.fields["id"]

    def _ensure_table_exists(self, connection: Any) -> None:
        # This is for auto-creation in legacy mode; migrations are preferred
        pass  # no-op for MVP to avoid schema issues

    def _execute_insert(self, connection: Any) -> None:
        """Build and execute INSERT SQL, capture PK, set _saved=True."""
        from .fields import AutoField, DateTimeField

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        # Import safe builder
        from ..query.safe_builder import get_safe_builder
        from ..settings import settings
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        cols = []
        vals = []

        for name, field_obj in self._meta.fields.items():
            if isinstance(field_obj, AutoField):
                continue
            value = getattr(self, name, None)
            if isinstance(field_obj, DateTimeField) and field_obj.auto_now_add:
                if value is None or value == datetime.min:
                    value = datetime.now()
                    setattr(self, name, value)
            elif isinstance(field_obj, DateTimeField) and field_obj.auto_now:
                value = datetime.now()
                setattr(self, name, value)
            db_value = field_obj.db_value(value)
            cols.append(builder.quote_column(name))
            vals.append(db_value)

        ph = builder.param_placeholder
        placeholders = ", ".join(ph for _ in cols)
        col_names = ", ".join(cols)
        quoted_table = builder.quote_table(table)
        sql = f"INSERT INTO {quoted_table} ({col_names}) VALUES ({placeholders})"

        cursor = connection.execute(sql, vals)
        if hasattr(cursor, "lastrowid") and cursor.lastrowid:
            pk_name, _ = self._get_pk_field()
            setattr(self, pk_name, cursor.lastrowid)
        self._saved = True
        logger.debug(f"Inserted {self.__class__.__name__} pk={self.pk}")

    def _execute_update(self, connection: Any) -> None:
        """Build and execute UPDATE SQL, set _saved=True."""
        from .fields import DateTimeField

        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        from ..query.safe_builder import get_safe_builder
        from ..settings import settings
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        sets = []
        vals = []

        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                continue
            value = getattr(self, name, None)
            if isinstance(field_obj, DateTimeField) and field_obj.auto_now:
                value = datetime.now()
                setattr(self, name, value)
            db_value = field_obj.db_value(value)
            ph = builder.param_placeholder
            quoted_col = builder.quote_column(name)
            sets.append(f"{quoted_col} = {ph}")
            vals.append(db_value)

        vals.append(pk_value)
        quoted_pk = builder.quote_column(pk_name)
        quoted_table = builder.quote_table(table)
        ph = builder.param_placeholder
        sql = f"UPDATE {quoted_table} SET {', '.join(sets)} WHERE {quoted_pk} = {ph}"

        connection.execute(sql, vals)
        self._saved = True
        logger.debug(f"Updated {self.__class__.__name__} pk={self.pk}")

    def _execute_delete(self, connection: Any) -> None:
        """Build and execute DELETE SQL."""
        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))
        table = self._meta.table_name or self.__class__.__name__.lower() + "s"

        from ..query.safe_builder import get_safe_builder
        from ..settings import settings
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

    def save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Persist this model instance.

        If called within an atomic() block, changes are registered with
        the unit-of-work tracker and will be flushed at commit time.
        If called outside atomic(), changes are executed and committed
        immediately.
        """
        # Try to get current active transaction
        from .unit_of_work.transaction import TransactionManager

        tx = TransactionManager.get_current()
        conn = connection or self._get_connection()

        if tx is not None and tx.connection is conn:
            # Inside atomic block - register for later batch execution
            if not self._saved or force_insert:
                tx.tracker.register_new(self)
            else:
                tx.tracker.register_dirty(self)
            return

        # Immediate execution mode
        self._execute_insert(conn) if not self._saved else self._execute_update(conn)
        # Commit if not inside a transaction that manages it
        conn.commit()

    def delete(self, connection: Any = None) -> None:
        """Delete this model instance.

        Behavior mirrors save(): inside atomic() registers for deferred
        deletion; outside atomic() executes immediately and commits.
        """
        from .unit_of_work.transaction import TransactionManager

        tx = TransactionManager.get_current()
        conn = connection or self._get_connection()

        if tx is not None and tx.connection is conn:
            tx.tracker.register_deleted(self)
            return

        self._execute_delete(conn)
        conn.commit()

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._meta.fields}

    @classmethod
    def objects(cls) -> Any:
        from ..managers.base import Manager

        if not hasattr(cls, "_manager"):
            cls._manager = Manager(cls)
        return cls._manager

    # Property pk remains
    @property
    def pk(self) -> Any:
        pk_name, pk_field = self._get_pk_field()
        return getattr(self, pk_name, None)

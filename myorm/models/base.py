"""Base model and model lifecycle abstractions."""

from __future__ import annotations

from typing import Any, Dict, Type

from .fields import AutoField, Field
from .meta import MetaOptions
from .registry import ModelRegistry


class ObjectDoesNotExist(Exception):
    """Raised when a query does not return any results."""

    pass


class MultipleObjectsReturned(Exception):
    """Raised when a query returns more than one result when only one was expected."""

    pass


class ModelMeta(type):
    """Metaclass that collects field definitions and builds _meta.

    Walks the class namespace, finds every Field instance, calls its
    ``__post_init__`` (since dataclasses don't do this when the instance
    is created at class-scope), sets ``field.name``, and populates
    ``cls._meta.fields``.

    Also reads the inner ``Meta`` class and forwards its attributes to
    the ``MetaOptions`` instance.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        # Build MetaOptions from the inner ``Meta`` class, if present
        meta_attrs: dict[str, Any] = {}
        meta_cls = namespace.get("Meta")
        if meta_cls is not None:
            for attr in (
                "table_name",
                "indexes",
                "constraints",
                "ordering",
                "abstract",
                "managed",
            ):
                if hasattr(meta_cls, attr):
                    meta_attrs[attr] = getattr(meta_cls, attr)

        # Collect all Field instances declared directly on this class
        fields: dict[str, Field] = {}
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                value.name = key
                # Calling __post_init__ again is safe because we have
                # already set .name; dataclass already called it once
                # during field instantiation at class-scope, but some
                # subclasses (DateTimeField etc.) need it after .name
                # is available.
                if hasattr(value, "__post_init__"):
                    value.__post_init__()
                fields[key] = value

        # Create the class
        cls = super().__new__(mcs, name, bases, namespace)

        # Skip everything for the abstract base Model itself
        if name != "Model":
            # Inherit fields from parent classes
            for base in bases:
                if hasattr(base, "_meta") and hasattr(base._meta, "fields"):
                    for fname, fobj in base._meta.fields.items():
                        if fname not in fields:
                            fields[fname] = fobj

            # Auto-add an AutoField if no primary_key was declared
            has_pk = any(f.primary_key for f in fields.values())
            if not has_pk:
                auto = AutoField()
                auto.name = "id"
                fields["id"] = auto

            # Build and attach MetaOptions
            meta_options = MetaOptions(**meta_attrs)
            meta_options.fields = fields
            cls._meta = meta_options  # type: ignore[attr-defined]

            # Attach default manager (supports custom managers defined on the class)
            from ..managers.base import Manager, ManagerDescriptor

            # Check if user defined a custom manager in the class
            has_custom_manager = False
            for attr_name in namespace:
                if isinstance(namespace[attr_name], Manager):
                    has_custom_manager = True
                    break
            if not has_custom_manager:
                cls._default_manager = Manager(cls)
            cls.objects = ManagerDescriptor()  # type: ignore[assignment]

            # Register
            ModelRegistry.register_model(cls)

        return cls


class Model(metaclass=ModelMeta):
    """Base model class with ORM-like behaviour.

    After construction, ``self._meta`` contains a ``MetaOptions`` instance
    whose ``fields`` dict maps field names to their ``Field`` objects.
    """

    _meta: MetaOptions  # set by ModelMeta.__new__
    _saved: bool = False  # tracks whether this instance has been saved

    def __init__(self, **kwargs: Any) -> None:
        """Initialise the model, calling ``python_value`` on each field."""
        for field_name, field_obj in self._meta.fields.items():
            value = kwargs.get(field_name, field_obj.default)
            if callable(value) and not isinstance(value, Field):
                value = value()
            setattr(self, field_name, field_obj.python_value(value))
        self._saved = False

    def _get_connection(self) -> Any:
        from .. import settings

        db_config = settings.settings.get_database("default")
        adapter = db_config.get_adapter()
        return adapter.connect(db_config.get_connection_config())

    def _get_pk_field(self) -> tuple[str, Field]:
        """Return (field_name, field_obj) for the primary key."""
        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                return name, field_obj
        return "id", self._meta.fields["id"]

    def _build_insert(self) -> tuple[str, list[Any]]:
        """Build INSERT SQL and params."""
        from .fields import AutoField

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        cols: list[str] = []
        vals: list[Any] = []

        for name, field_obj in self._meta.fields.items():
            # Skip auto fields on insert (they are generated by DB)
            if isinstance(field_obj, AutoField):
                continue
            value = db_value = field_obj.db_value(getattr(self, name, None))
            cols.append(name)
            vals.append(db_value)

        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        return sql, vals

    def _build_update(self) -> tuple[str, list[Any]]:
        """Build UPDATE SQL and params."""
        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))

        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        sets: list[str] = []
        vals: list[Any] = []

        for name, field_obj in self._meta.fields.items():
            if field_obj.primary_key:
                continue
            db_value = field_obj.db_value(getattr(self, name, None))
            sets.append(f"{name} = ?")
            vals.append(db_value)

        vals.append(pk_value)
        sql = f"UPDATE {table} SET {', '.join(sets)} WHERE {pk_name} = ?"
        return sql, vals

    def save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Persist the model instance to the database."""
        conn = connection or self._get_connection()
        self._ensure_table_exists(conn)

        if not self._saved or force_insert:
            try:
                sql, params = self._build_insert()
                cursor = conn.execute(sql, params)
                # Capture auto-generated PK from cursor if available
                if hasattr(cursor, "lastrowid") and cursor.lastrowid:
                    pk_name, _ = self._get_pk_field()
                    setattr(self, pk_name, cursor.lastrowid)
                conn.commit()
                self._saved = True
                return
            except Exception:
                pass

        sql, params = self._build_update()
        cursor = conn.execute(sql, params)
        conn.commit()
        self._saved = True

    _table_created: bool = False

    def _ensure_table_exists(self, connection: Any) -> None:
        """Auto-create the table if it has not been created yet."""
        if self.__class__._table_created:
            return
        try:
            from ..migrations.engine import MigrationEngine
            from ..migrations import operations

            engine = MigrationEngine()
            op = operations.CreateTable(
                name=self._meta.table_name or
                    self.__class__.__name__.lower() + "s",
                columns=[
                    {
                        "name": fname,
                        "field_type": engine._get_internal_type(fobj),
                        **engine._collect_field_attrs(fobj),
                    }
                    for fname, fobj in self._meta.fields.items()
                ],
            )
            engine.migrate_direct([op], connection)
            self.__class__._table_created = True
        except Exception:
            pass

    def delete(self, connection: Any = None) -> None:
        """Delete the model instance from the database."""
        conn = connection or self._get_connection()
        pk_name, pk_field = self._get_pk_field()
        pk_value = pk_field.db_value(getattr(self, pk_name, None))
        table = self._meta.table_name or self.__class__.__name__.lower() + "s"
        sql = f"DELETE FROM {table} WHERE {pk_name} = ?"
        conn.execute(sql, (pk_value,))
        conn.commit()
        self._saved = False

    def to_dict(self) -> dict[str, Any]:
        """Return a dict mapping field names to their Python values."""
        return {name: getattr(self, name) for name in self._meta.fields}

    @classmethod
    def objects(cls) -> Any:
        """Return a manager for this model."""
        from ..managers.base import Manager

        if not hasattr(cls, "_manager"):
            cls._manager = Manager(cls)
        return cls._manager
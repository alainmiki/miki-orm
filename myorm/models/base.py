"""Base model and model lifecycle abstractions."""

from __future__ import annotations

from typing import Any, Dict, Type

from .fields import Field
from .meta import MetaOptions
from .registry import ModelRegistry


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

            # Build and attach MetaOptions
            meta_options = MetaOptions(**meta_attrs)
            meta_options.fields = fields
            cls._meta = meta_options  # type: ignore[attr-defined]

            # Register
            ModelRegistry.register_model(cls)

        return cls


class Model(metaclass=ModelMeta):
    """Base model class with ORM-like behaviour.

    After construction, ``self._meta`` contains a ``MetaOptions`` instance
    whose ``fields`` dict maps field names to their ``Field`` objects.
    """

    _meta: MetaOptions  # set by ModelMeta.__new__

    def __init__(self, **kwargs: Any) -> None:
        """Initialise the model, calling ``python_value`` on each field."""
        for field_name, field_obj in self._meta.fields.items():
            value = kwargs.get(field_name, field_obj.default)
            if callable(value) and not isinstance(value, Field):
                value = value()
            setattr(self, field_name, field_obj.python_value(value))

    def save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Persist the model instance (not yet implemented)."""
        raise NotImplementedError

    def delete(self, connection: Any = None) -> None:
        """Delete the model instance (not yet implemented)."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Return a dict mapping field names to their Python values."""
        return {name: getattr(self, name) for name in self._meta.fields}

    @classmethod
    def objects(cls) -> Any:
        """Return a manager for this model (not yet implemented)."""
        raise NotImplementedError
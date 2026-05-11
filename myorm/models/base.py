"""Base model and model lifecycle abstractions."""

from __future__ import annotations

from typing import Any, Dict, List, Type

from .fields import Field
from .registry import ModelRegistry


class ModelMeta(type):
    """Metaclass for automatic model registration."""

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
        cls = super().__new__(mcs, name, bases, namespace)
        if name != "Model":
            ModelRegistry.register_model(cls)
        return cls


class Model(metaclass=ModelMeta):
    """Base model class with ORM behavior."""

    _meta: "MetaOptions"

    def __init__(self, **kwargs: Any) -> None:
        for field_name, field in self._meta.fields.items():
            value = kwargs.get(field_name, field.default)
            setattr(self, field_name, field.python_value(value))

    def save(self, connection: Any = None, *, force_insert: bool = False) -> None:
        """Persist the model instance."""
        raise NotImplementedError

    def delete(self, connection: Any = None) -> None:
        """Delete the model instance."""
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self._meta.fields}

    @classmethod
    def objects(cls) -> "Manager":
        raise NotImplementedError

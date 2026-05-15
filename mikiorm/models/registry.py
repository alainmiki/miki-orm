"""Registry for all defined models and metadata introspection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Type

if TYPE_CHECKING:
    from .base import Model


class ModelRegistry:
    _models: Dict[str, Type[Any]] = {}

    @classmethod
    def register_model(cls, model: Type[Any]) -> None:
        cls._models[model.__name__] = model

    @classmethod
    def get_model(cls, name: str) -> Type[Any] | None:
        return cls._models.get(name)

    @classmethod
    def all_models(cls) -> list[Type[Any]]:
        return list(cls._models.values())
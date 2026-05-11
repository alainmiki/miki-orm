"""Registry for all defined models and metadata introspection."""

from __future__ import annotations

from typing import Dict, Type

from .base import Model


class ModelRegistry:
    _models: Dict[str, Type[Model]] = {}

    @classmethod
    def register_model(cls, model: Type[Model]) -> None:
        cls._models[model.__name__] = model

    @classmethod
    def get_model(cls, name: str) -> Type[Model] | None:
        return cls._models.get(name)

    @classmethod
    def all_models(cls) -> list[Type[Model]]:
        return list(cls._models.values())

"""Base manager class for query and persistence APIs."""

from __future__ import annotations

from typing import Any

from ..models.base import Model
from .queryset import QuerySet


class Manager:
    """Default manager exposing Django-like query methods."""

    model: type[Model]

    def __init__(self, model: type[Model]) -> None:
        self.model = model

    def all(self) -> QuerySet:
        return QuerySet(self.model)

    def filter(self, *args: Any, **kwargs: Any) -> QuerySet:
        return QuerySet(self.model).filter(*args, **kwargs)

    def exclude(self, *args: Any, **kwargs: Any) -> QuerySet:
        return QuerySet(self.model).exclude(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Model:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def exists(self) -> bool:
        raise NotImplementedError

    def first(self) -> Model | None:
        raise NotImplementedError

    def last(self) -> Model | None:
        raise NotImplementedError

    def update_or_create(self, defaults: dict[str, Any] | None = None, **kwargs: Any) -> tuple[Model, bool]:
        raise NotImplementedError

    def bulk_create(self, objs: list[Model], batch_size: int = 1000) -> list[Model]:
        raise NotImplementedError

    def update(self, **values: Any) -> int:
        raise NotImplementedError

    def values(self, *fields: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def values_list(self, *fields: str) -> list[tuple[Any, ...]]:
        raise NotImplementedError

    def select_related(self, *related: str) -> QuerySet:
        return QuerySet(self.model).select_related(*related)

    def prefetch_related(self, *related: str) -> QuerySet:
        return QuerySet(self.model).prefetch_related(*related)

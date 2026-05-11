"""QuerySet implementation with lazy evaluation and query composition."""

from __future__ import annotations

from typing import Any, Iterable

from ..models.base import Model
from ..query.builder import QueryBuilder


class QuerySet:
    """A lazy query container for model queries."""

    def __init__(self, model: type[Model]) -> None:
        self.model = model
        self._filters: list[Any] = []
        self._excludes: list[Any] = []
        self._order_by: list[str] = []
        self._selected_related: list[str] = []
        self._prefetch_related: list[str] = []

    def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
        self._filters.append((args, kwargs))
        return self

    def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
        self._excludes.append((args, kwargs))
        return self

    def order_by(self, *fields: str) -> "QuerySet":
        self._order_by.extend(fields)
        return self

    def select_related(self, *related: str) -> "QuerySet":
        self._selected_related.extend(related)
        return self

    def prefetch_related(self, *related: str) -> "QuerySet":
        self._prefetch_related.extend(related)
        return self

    def all(self, connection: Any = None) -> list[Model]:
        builder = QueryBuilder(self.model)
        sql, params = builder.build(self)
        if connection is None:
            raise ValueError("Connection is required for query execution")
        rows = connection.fetchall(sql, params)
        return [self.model(**dict(row)) for row in rows]

    def first(self, connection: Any = None) -> Model | None:
        results = self.order_by("id").all(connection)
        return results[0] if results else None

    def count(self, connection: Any = None) -> int:
        raise NotImplementedError

    def exists(self, connection: Any = None) -> bool:
        return bool(self.first(connection))

    def __iter__(self) -> Iterable[Model]:
        raise NotImplementedError

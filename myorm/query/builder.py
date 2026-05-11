"""Query builder for SQL AST and translation."""

from __future__ import annotations

from typing import Any

from .expressions import Expression


class QueryBuilder:
    """Builds SQL strings from QuerySet definitions."""

    def __init__(self, model: type[Any]) -> None:
        self.model = model

    def build(self, queryset: Any) -> tuple[str, tuple[Any, ...]]:
        sql = f"SELECT * FROM {self.model._meta.table_name or self.model.__name__.lower()}"
        params: list[Any] = []

        if queryset._filters:
            sql += " WHERE " + " AND ".join("1=1" for _ in queryset._filters)

        if queryset._order_by:
            sql += " ORDER BY " + ", ".join(queryset._order_by)

        return sql, tuple(params)

"""Query builder for SQL AST and translation."""

from __future__ import annotations

from typing import Any


class QueryBuilder:
    """Builds SQL strings from QuerySet definitions."""

    def __init__(self, model: type[Any]) -> None:
        self.model = model

    def build(self, queryset: Any) -> tuple[str, tuple[Any, ...]]:
        table = self.model._meta.table_name or self.model.__name__.lower()
        sql = f"SELECT * FROM {table}"
        params: list[Any] = []

        if queryset._filters:
            conditions = []
            for _, kwargs in queryset._filters:
                for key, value in kwargs.items():
                    conditions.append(f"{key} = ?")
                    params.append(value)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

        if queryset._excludes:
            excl_conditions = []
            for _, kwargs in queryset._excludes:
                for key, value in kwargs.items():
                    excl_conditions.append(f"{key} != ?")
                    params.append(value)
            if excl_conditions:
                if "WHERE" in sql:
                    sql += " AND " + " AND ".join(excl_conditions)
                else:
                    sql += " WHERE " + " AND ".join(excl_conditions)

        if queryset._order_by:
            sql += " ORDER BY " + ", ".join(queryset._order_by)

        return sql, tuple(params)

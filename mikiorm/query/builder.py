"""Query builder for SQL AST and translation."""

from __future__ import annotations

import logging
from typing import Any

from mikiorm.backends.base.dialect import get_safe_builder
from mikiorm.conf.settings import settings

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Builds SQL strings from QuerySet definitions with safe identifier quoting."""

    def __init__(self, model: type[Any]) -> None:
        self.model = model
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        self.builder = get_safe_builder(engine)

    def build(self, queryset: Any, connection: Any = None) -> tuple[str, tuple[Any, ...]]:
        """Build a safe SELECT query from a QuerySet."""
        table = self.model._meta.table_name or self.model.__name__.lower() + "s"
        quoted_table = self.builder.quote_table(table)

        # Build SELECT with DISTINCT
        select_clause = "SELECT DISTINCT" if queryset._distinct else "SELECT"
        sql = f"{select_clause} * FROM {quoted_table}"
        params: list[Any] = []

        # Build WHERE clause from filters and excludes
        where, where_params = queryset._build_where_clause()
        if where:
            sql += where
            params.extend(where_params)

        # Build GROUP BY clause (with annotations)
        group_by_clause = ""
        if queryset._annotations:
            # Get non-aggregated fields for GROUP BY
            all_fields = list(self.model._meta.fields.keys())
            group_by_fields = [f for f in all_fields if f not in queryset._defer_fields]
            
            if queryset._only_fields:
                group_by_fields = [f for f in group_by_fields if f in queryset._only_fields]
            
            if group_by_fields:
                quoted_fields = [self.builder.quote_column(f) for f in group_by_fields]
                group_by_clause = f" GROUP BY {', '.join(quoted_fields)}"
                sql += group_by_clause

        # Build HAVING clause (filter on aggregations)
        if queryset._having_conditions and queryset._annotations:
            having_conditions = []
            having_params = []
            
            for cond_type, cond_data in queryset._having_conditions:
                if cond_type == "AND":
                    for key, value in cond_data.items():
                        field_name, operator = self.builder.parse_lookup(key)
                        condition, cond_params = self.builder.build_condition(field_name, operator, value)
                        having_conditions.append(condition)
                        having_params.extend(cond_params)
            
            if having_conditions:
                sql += " HAVING " + " AND ".join(having_conditions)
                params.extend(having_params)

        # Build ORDER BY clause
        if queryset._order_by:
            order_clause = self.builder.build_order_by(queryset._order_by)
            if order_clause:
                sql += " " + order_clause

        # Build LIMIT and OFFSET
        if queryset._limit is not None:
            sql += f" LIMIT {queryset._limit}"
        if queryset._offset is not None:
            sql += f" OFFSET {queryset._offset}"

        logger.debug(f"Built query: {sql} with params: {params}")
        return sql, tuple(params)

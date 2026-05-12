"""Query builder for SQL AST and translation."""

from __future__ import annotations

import logging
from typing import Any

from .safe_builder import get_safe_builder
from .. import settings

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
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = self.builder.quote_table(table)
        
        sql = f"SELECT * FROM {quoted_table}"
        params: list[Any] = []

        # Build WHERE clause from filters and excludes
        where, where_params = queryset._build_where_clause()
        if where:
            sql += where
            params.extend(where_params)

        # Build ORDER BY clause
        if queryset._order_by:
            order_clause = self.builder.build_order_by(queryset._order_by)
            if order_clause:
                sql += " " + order_clause

        logger.debug(f"Built query: {sql} with params: {params}")
        return sql, tuple(params)

"""QuerySet implementation with lazy evaluation and query composition."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from myorm.managers.base import Manager

from ..settings import settings
from ..connections.base import get_param_placeholder
from ..models.base import Model, ObjectDoesNotExist, MultipleObjectsReturned
from ..query.builder import QueryBuilder
from ..query.safe_builder import get_safe_builder

logger = logging.getLogger(__name__)


class QuerySet:
    """A lazy query container for model queries."""

    def __init__(self, model: type[Model]) -> None:
        self.model = model
        self._filters: list[Any] = []
        self._excludes: list[Any] = []
        self._order_by: list[str] = []
        self._selected_related: list[str] = []
        self._prefetch_related: list[str] = []

    def _get_connection(self) -> Any:
        from ..settings import connection_manager

        return connection_manager.get_connection()

    def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
        self._filters.append(("AND", kwargs))
        return self

    def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
        self._excludes.append(("AND", kwargs))
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

    def _build_where_clause(self, connection: Any = None) -> tuple[str, list[Any]]:
        """Build WHERE clause with safe identifier quoting and parameterization."""
        conn = connection or self._get_connection()
        # Get engine from settings to select the right dialect
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        conditions: list[str] = []
        params: list[Any] = []

        # Process include filters
        for _, kwargs in self._filters:
            for key, value in kwargs.items():
                field_name, operator = builder.parse_lookup(key)
                condition, cond_params = builder.build_condition(
                    field_name, operator, value
                )
                conditions.append(condition)
                params.extend(cond_params)

        # Process exclude filters (NOT (...))
        for _, kwargs in self._excludes:
            for key, value in kwargs.items():
                field_name, operator = builder.parse_lookup(key)
                condition, cond_params = builder.build_condition(
                    field_name, operator, value
                )
                # Negate the condition
                negated = f"NOT ({condition})"
                conditions.append(negated)
                params.extend(cond_params)

        if conditions:
            return " WHERE " + " AND ".join(conditions), params
        return "", []

    def _build_sql(self) -> tuple[str, list[Any]]:
        builder = QueryBuilder(self.model)
        return builder.build(self)

    def _row_to_model(self, row: Any) -> Model:
        field_names = list(self.model._meta.fields.keys())
        if isinstance(row, dict):
            kwargs = dict(row)
        else:
            kwargs = {}
            for i, val in enumerate(row):
                if i < len(field_names):
                    kwargs[field_names[i]] = val
        return self.model(**kwargs)

    def all(self, connection: Any = None) -> list[Model]:
        conn = connection or self._get_connection()
        sql, qparams = self._build_sql()
        rows = conn.fetchall(sql, qparams)
        return [self._row_to_model(row) for row in rows]

    def first(self, connection: Any = None) -> Model | None:
        results = self.order_by("id").all(connection)
        return results[0] if results else None

    def last(self, connection: Any = None) -> Model | None:
        results = self.order_by("-id").all(connection)
        return results[0] if results else None

    def count(self, connection: Any = None) -> int:
        conn = connection or self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()
        
        sql = f"SELECT COUNT(*) FROM {quoted_table}{where}"
        row = conn.fetchone(sql, params)
        return row[0] if row else 0

    def exists(self, connection: Any = None) -> bool:
        return self.count(connection) > 0

    def get(self, connection: Any = None, **kwargs: Any) -> Model:
        qs = self.filter(**kwargs)
        results = qs.all(connection)
        if len(results) == 0:
            logger.warning(
                f"{self.model.__name__} matching query does not exist. kwargs: {kwargs}"
            )
            raise ObjectDoesNotExist(
                f"{self.model.__name__} matching query does not exist. "
                f"kwargs: {kwargs}"
            )
        if len(results) > 1:
            logger.warning(
                f"get() returned more than one {self.model.__name__} "
                f"({len(results)} results) for kwargs: {kwargs}"
            )
            raise MultipleObjectsReturned(
                f"get() returned more than one {self.model.__name__} -- "
                f"it returned {len(results)}!"
            )
        return results[0]

    def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        connection: Any = None,
        **kwargs: Any,
    ) -> tuple[Model, bool]:
        defaults = defaults or {}
        try:
            obj = self.get(connection=connection, **kwargs)
            logger.debug(f"Found existing {self.model.__name__}: {kwargs}")
            return obj, False
        except ObjectDoesNotExist:
            logger.debug(f"Creating new {self.model.__name__}: {kwargs}")
            create_kwargs = {**kwargs, **defaults}
            obj = Manager(self.model).create(**create_kwargs)
            return obj, True
        except MultipleObjectsReturned:
            logger.error(
                f"get_or_create: Multiple {self.model.__name__} objects found for {kwargs}"
            )
            raise

    def update_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        connection: Any = None,
        **kwargs: Any,
    ) -> tuple[Model, bool]:
        defaults = defaults or {}
        try:
            obj = self.get(connection=connection, **kwargs)
            if defaults:
                logger.debug(f"Updating {self.model.__name__}: {defaults}")
                for key, value in defaults.items():
                    setattr(obj, key, value)
                obj.save()
            return obj, False
        except ObjectDoesNotExist:
            logger.debug(f"Creating new {self.model.__name__}: {kwargs}")
            create_kwargs = {**kwargs, **defaults}
            obj = Manager(self.model).create(**create_kwargs)
            return obj, True
        except MultipleObjectsReturned:
            logger.error(
                f"update_or_create: Multiple {self.model.__name__} objects found for {kwargs}"
            )
            raise


    def create(self, connection: Any = None, **kwargs: Any) -> Model:
        obj = Manager(self.model).create(**kwargs)
        return obj

    def delete(self, connection: Any = None) -> int:
        """Delete all models matching this QuerySet safely."""
        conn = connection or self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()
        
        sql = f"DELETE FROM {quoted_table}{where}"
        logger.debug(f"Executing DELETE: {sql} with params: {params}")
        
        cursor = conn.execute(sql, params)
        conn.commit()
        rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
        logger.info(f"Deleted {rowcount} {self.model.__name__} rows")
        return rowcount

    def update(self, connection: Any = None, **values: Any) -> int:
        """Update all models matching this QuerySet with safe identifier quoting."""
        if not values:
            return 0
        
        conn = connection or self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, where_params = self._build_where_clause()
        
        # Build SET clause with safe identifier quoting
        set_parts = []
        set_params = []
        for key, val in values.items():
            quoted_col = builder.quote_column(key)
            ph = builder.param_placeholder
            set_parts.append(f"{quoted_col} = {ph}")
            set_params.append(val)
        
        # Combine SET params with WHERE params
        all_params = set_params + where_params
        
        sql = f"UPDATE {quoted_table} SET {', '.join(set_parts)}{where}"
        logger.debug(f"Executing UPDATE: {sql} with params: {all_params}")
        
        cursor = conn.execute(sql, all_params)
        conn.commit()
        rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
        logger.info(f"Updated {rowcount} {self.model.__name__} rows with {values}")
        return rowcount

    def values(self, *fields: str) -> list[dict[str, Any]]:
        conn = self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        
        if fields:
            quoted_cols = [builder.quote_column(f) for f in fields]
            cols = ", ".join(quoted_cols)
        else:
            cols = "*"
        
        where, params = self._build_where_clause()
        sql = f"SELECT {cols} FROM {quoted_table}{where}"
        rows = conn.fetchall(sql, params)
        
        result: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append({k: row[k] for k in fields if k in row})
            else:
                result.append(dict(zip(fields, row)))
        return result

    def values_list(self, *fields: str) -> list[tuple[Any, ...]]:
        conn = self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        
        if fields:
            quoted_cols = [builder.quote_column(f) for f in fields]
            cols = ", ".join(quoted_cols)
        else:
            cols = "*"
        
        where, params = self._build_where_clause()
        sql = f"SELECT {cols} FROM {quoted_table}{where}"
        rows = conn.fetchall(sql, params)
        
        result: list[tuple[Any, ...]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append(tuple(row.get(f) for f in fields))
            else:
                result.append(tuple(row))
        return result

    def __iter__(self) -> Iterable[Model]:
        return iter(self.all())

    def __repr__(self) -> str:
        return f"<QuerySet [{self.count()}]>"

    def __bool__(self) -> bool:
        return self.exists()

    def __len__(self) -> int:
        return self.count()
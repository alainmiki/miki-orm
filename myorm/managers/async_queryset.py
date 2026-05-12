"""Asynchronous QuerySet for async database operations."""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..models.base import Model, ObjectDoesNotExist, MultipleObjectsReturned
from ..query.builder import QueryBuilder
from ..query.safe_builder import get_safe_builder
from .. import settings


class AsyncQuerySet:
    """A lazy async query container for model queries."""

    def __init__(self, model: type[Model], connection: Any = None) -> None:
        self.model = model
        self._connection = connection
        self._filters: list[Any] = []
        self._excludes: list[Any] = []
        self._order_by: list[str] = []
        self._selected_related: list[str] = []
        self._prefetch_related: list[str] = []

    async def _get_connection(self) -> Any:
        """Get the active connection: use explicitly provided, or fetch from manager."""
        if self._connection is not None:
            return self._connection
        from ..settings import async_connection_manager
        return await async_connection_manager.get_connection()

    async def all(self, connection: Any = None) -> list[Model]:
        conn = connection or await self._get_connection()
        sql, qparams = self._build_sql()
        rows = await conn.fetchall(sql, qparams)
        return [self._row_to_model(row) for row in rows]

    async def first(self, connection: Any = None) -> Model | None:
        results = await self.order_by("id").all(connection)
        return results[0] if results else None

    async def last(self, connection: Any = None) -> Model | None:
        results = await self.order_by("-id").all(connection)
        return results[0] if results else None

    async def count(self, connection: Any = None) -> int:
        conn = connection or await self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()
         
        sql = f"SELECT COUNT(*) FROM {quoted_table}{where}"
        row = await conn.fetchone(sql, params)
        return row[0] if row else 0

    async def exists(self, connection: Any = None) -> bool:
        return (await self.count(connection)) > 0

    async def get(self, connection: Any = None, **kwargs: Any) -> Model:
        qs = self.filter(**kwargs)
        results = await qs.all(connection)
        if len(results) == 0:
            raise ObjectDoesNotExist(
                f"{self.model.__name__} matching query does not exist. kwargs: {kwargs}"
            )
        if len(results) > 1:
            raise MultipleObjectsReturned(
                f"get() returned more than one {self.model.__name__} -- "
                f"it returned {len(results)}!"
            )
        return results[0]

    async def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        connection: Any = None,
        **kwargs: Any,
    ) -> tuple[Model, bool]:
        from ..managers.base import Manager
        defaults = defaults or {}
        try:
            obj = await self.get(connection=connection, **kwargs)
            return obj, False
        except ObjectDoesNotExist:
            create_kwargs = {**kwargs, **defaults}
            # Need async create; stubbed.
            raise NotImplementedError("Async get_or_create not yet implemented")
        except MultipleObjectsReturned:
            raise

    async def create(self, connection: Any = None, **kwargs: Any) -> Model:
        obj = self.model(**kwargs)
        await obj.async_save(connection=connection)
        return obj

    async def delete(self, connection: Any = None) -> int:
        conn = connection or await self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()

        sql = f"DELETE FROM {quoted_table}{where}"
        cursor = await conn.execute(sql, params)
        rowcount = getattr(cursor, "rowcount", 0)
        return rowcount

    async def update(self, connection: Any = None, **values: Any) -> int:
        from ..settings import async_connection_manager
        conn = connection or await async_connection_manager.get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)
        where, where_params = self._build_where_clause()

        set_parts = []
        set_params = []
        for key, val in values.items():
            quoted_col = builder.quote_column(key)
            ph = builder.param_placeholder
            set_parts.append(f"{quoted_col} = {ph}")
            set_params.append(val)

        all_params = set_params + where_params
        sql = f"UPDATE {quoted_table} SET {', '.join(set_parts)}{where}"
        cursor = await conn.execute(sql, all_params)
        rowcount = getattr(cursor, "rowcount", 0)
        return rowcount

    async def values(self, *fields: str, connection: Any = None) -> list[dict[str, Any]]:
        conn = connection or await self._get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)

        if fields:
            quoted_cols = [builder.quote_column(f) for f in fields]
            cols = ", ".join(quoted_cols)
        else:
            cols = "*"

        where, params = self._build_where_clause()
        sql = f"SELECT {cols} FROM {quoted_table}{where}"
        rows = await conn.fetchall(sql, params)

        result: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append({k: row[k] for k in fields if k in row})
            else:
                result.append(dict(zip(fields, row)))
        return result

    async def values_list(self, *fields: str, connection: Any = None) -> list[tuple[Any, ...]]:
        conn = connection or await self._get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = self.model._meta.table_name or self.model.__name__.lower()
        quoted_table = builder.quote_table(table)

        if fields:
            quoted_cols = [builder.quote_column(f) for f in fields]
            cols = ", ".join(quoted_cols)
        else:
            cols = "*"

        where, params = self._build_where_clause()
        sql = f"SELECT {cols} FROM {quoted_table}{where}"
        rows = await conn.fetchall(sql, params)

        result: list[tuple[Any, ...]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append(tuple(row.get(f) for f in fields))
            else:
                result.append(tuple(row))
        return result

    def filter(self, *args: Any, **kwargs: Any) -> "AsyncQuerySet":
        self._filters.append(("AND", kwargs))
        return self

    def exclude(self, *args: Any, **kwargs: Any) -> "AsyncQuerySet":
        self._excludes.append(("AND", kwargs))
        return self

    def order_by(self, *fields: str) -> "AsyncQuerySet":
        self._order_by.extend(fields)
        return self

    def select_related(self, *related: str) -> "AsyncQuerySet":
        self._selected_related.extend(related)
        return self

    def prefetch_related(self, *related: str) -> "AsyncQuerySet":
        self._prefetch_related.extend(related)
        return self

    def _build_where_clause(self) -> tuple[str, list[Any]]:
        """Build WHERE clause with safe identifier quoting."""
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        conditions: list[str] = []
        params: list[Any] = []

        for _, kwargs in self._filters:
            for key, value in kwargs.items():
                field_name, operator = builder.parse_lookup(key)
                condition, cond_params = builder.build_condition(field_name, operator, value)
                conditions.append(condition)
                params.extend(cond_params)

        for _, kwargs in self._excludes:
            for key, value in kwargs.items():
                field_name, operator = builder.parse_lookup(key)
                condition, cond_params = builder.build_condition(field_name, operator, value)
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

    async def __aiter__(self) -> AsyncIterator[Model]:
        items = await self.all()
        for item in items:
            yield item

    def __repr__(self) -> str:
        return f"<AsyncQuerySet [{self.model.__name__}]>"

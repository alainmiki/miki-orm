"""QuerySet implementation with lazy evaluation and query composition."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from mikiorm.managers.base import Manager

from ..conf.settings import settings
from ..models.base import Model, ObjectDoesNotExist, MultipleObjectsReturned
from ..models.relationships import ForeignKey
from ..query import QueryBuilder
from ..backends.base.dialect import get_safe_builder

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
        self._offset: int | None = None
        self._limit: int | None = None
        self._distinct: bool = False
        self._annotations: dict[str, Any] = {}
        self._group_by: list[str] = []
        self._only_fields: set[str] | None = None
        self._defer_fields: set[str] = set()
        self._having_conditions: list[Any] = []
        self._set_operation: tuple[str, "QuerySet"] | None = None

    def _get_connection(self) -> Any:
        from ..conf.settings import connection_manager

        return connection_manager.get_connection()

    def _get_table_name(self) -> str:
        return self.model._meta.table_name or self.model.__name__.lower() + "s"

    def _clone(self) -> "QuerySet":
        """Create an independent copy of this QuerySet for proper method chaining."""
        clone = QuerySet(self.model)
        clone._filters = self._filters.copy()
        clone._excludes = self._excludes.copy()
        clone._order_by = self._order_by.copy()
        clone._selected_related = self._selected_related.copy()
        clone._prefetch_related = self._prefetch_related.copy()
        clone._offset = self._offset
        clone._limit = self._limit
        clone._distinct = self._distinct
        clone._annotations = self._annotations.copy()
        clone._group_by = self._group_by.copy()
        clone._only_fields = self._only_fields.copy() if self._only_fields else None
        clone._defer_fields = self._defer_fields.copy()
        clone._having_conditions = self._having_conditions.copy()
        clone._set_operation = self._set_operation
        return clone

    def _resolve_lookup(self, field_name: str, value: Any) -> tuple[str, Any]:
        if field_name == "pk":
            field_name = next(
                (
                    name
                    for name, fld in self.model._meta.fields.items()
                    if fld.primary_key
                ),
                "id",
            )

        field_obj = self.model._meta.fields.get(field_name)
        if isinstance(field_obj, ForeignKey):
            if isinstance(value, (list, tuple, set)):
                value = [getattr(v, "pk", v) for v in value]
            elif hasattr(value, "pk"):
                value = value.pk

        return field_name, value

    def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
        """Filter by Q objects or keyword arguments."""
        from ..query.expressions import Q
        clone = self._clone()
        
        # Handle Q objects in *args
        for arg in args:
            if isinstance(arg, Q):
                clone._filters.append(("Q", arg))
            else:
                raise TypeError(f"filter() takes Q objects or keyword arguments, not {type(arg)}")
        
        # Handle keyword arguments
        if kwargs:
            clone._filters.append(("AND", kwargs))
        
        return clone

    def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
        """Exclude by Q objects or keyword arguments."""
        from ..query.expressions import Q
        clone = self._clone()
        
        # Handle Q objects in *args
        for arg in args:
            if isinstance(arg, Q):
                clone._excludes.append(("Q", arg))
            else:
                raise TypeError(f"exclude() takes Q objects or keyword arguments, not {type(arg)}")
        
        # Handle keyword arguments
        if kwargs:
            clone._excludes.append(("AND", kwargs))
        
        return clone

    def order_by(self, *fields: str) -> "QuerySet":
        clone = self._clone()
        clone._order_by.extend(fields)
        return clone

    def select_related(self, *related: str) -> "QuerySet":
        clone = self._clone()
        clone._selected_related.extend(related)
        return clone

    def prefetch_related(self, *related: str) -> "QuerySet":
        clone = self._clone()
        clone._prefetch_related.extend(related)
        return clone

    def distinct(self, *fields: str) -> "QuerySet":
        """Remove duplicate rows from results."""
        clone = self._clone()
        clone._distinct = True
        return clone

    def none(self) -> "QuerySet":
        """Return an empty QuerySet."""
        clone = self._clone()
        clone._filters.append(("AND", {"pk__in": []}))
        return clone

    def annotate(self, **annotations: Any) -> "QuerySet":
        """Add computed fields via aggregation."""
        from ..query.aggregates import Aggregate
        
        clone = self._clone()
        for alias, aggregate in annotations.items():
            if not isinstance(aggregate, Aggregate):
                raise TypeError(f"annotate() expects Aggregate objects, got {type(aggregate)}")
            clone._annotations[alias] = aggregate
        return clone

    def aggregate(self, **aggregates: Any) -> dict[str, Any]:
        """Return aggregation result as dictionary (terminal operation)."""
        from ..query.aggregates import Aggregate
        from ..backends.base.dialect import get_safe_builder
        
        if not aggregates:
            return {}
        
        conn = self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)
        
        table = self._get_table_name()
        quoted_table = builder.quote_table(table)
        where, where_params = self._build_where_clause()
        
        # Build aggregate select list
        select_parts = []
        for alias, aggregate in aggregates.items():
            if not isinstance(aggregate, Aggregate):
                raise TypeError(f"aggregate() expects Aggregate objects, got {type(aggregate)}")
            
            field_name = aggregate.field_name
            if field_name != "*":
                field_name = builder.quote_column(field_name)
            
            agg_sql = aggregate.to_sql(field_name)
            select_parts.append(f"{agg_sql} AS {alias}")
        
        sql = f"SELECT {', '.join(select_parts)} FROM {quoted_table}{where}"
        row = conn.fetchone(sql, where_params)
        
        if hasattr(conn, 'close'):
            conn.close()
        
        if not row:
            return {alias: None for alias in aggregates.keys()}
        
        # Convert row to dict
        if isinstance(row, dict):
            return row
        else:
            return dict(zip(aggregates.keys(), row))

    def only(self, *fields: str) -> "QuerySet":
        """Select only specified fields (deferred loading)."""
        clone = self._clone()
        clone._only_fields = set(fields) if fields else None
        clone._defer_fields = set()  # Clear any deferred fields
        return clone

    def defer(self, *fields: str) -> "QuerySet":
        """Exclude specified fields from selection (deferred loading)."""
        clone = self._clone()
        clone._defer_fields.update(fields)
        # If only_fields was set, we need to remove the deferred fields
        if clone._only_fields:
            clone._only_fields -= set(fields)
        return clone

    def __getitem__(self, key: slice | int) -> "QuerySet" | Model | None:
        """Support QuerySet slicing: qs[10:20] or qs[0]."""
        if isinstance(key, slice):
            clone = self._clone()
            start = key.start or 0
            if key.stop is not None:
                clone._offset = start
                clone._limit = key.stop - start
            else:
                clone._offset = start
                clone._limit = None
            return clone
        elif isinstance(key, int):
            if key < 0:
                raise ValueError("Negative indexing is not supported")
            results = self[key : key + 1].all()
            return results[0] if results else None
        else:
            raise TypeError("QuerySet indices must be slices or integers")

    def _build_where_clause(self, connection: Any = None) -> tuple[str, list[Any]]:
        """Build WHERE clause with safe identifier quoting and parameterization."""
        from ..query.expressions import Q, F
        
        # Get engine from settings to select the right dialect
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        conditions: list[str] = []
        params: list[Any] = []

        # Helper to build Q object conditions recursively
        def build_q_condition(q_obj: Q) -> tuple[str, list[Any]]:
            """Build SQL for a Q object."""
            q_conditions = []
            q_params = []
            
            for child in q_obj.children:
                if isinstance(child, Q):
                    # Nested Q object
                    child_sql, child_params = build_q_condition(child)
                    if child_sql:
                        q_conditions.append(f"({child_sql})")
                        q_params.extend(child_params)
                else:
                    # (field_name, value) tuple
                    key, value = child
                    field_name, operator = builder.parse_lookup(key)
                    field_name, value = self._resolve_lookup(field_name, value)
                    condition, cond_params = builder.build_condition(
                        field_name, operator, value
                    )
                    q_conditions.append(condition)
                    q_params.extend(cond_params)
            
            if not q_conditions:
                return "", []
            
            connector = f" {q_obj.connector} "
            q_sql = connector.join(q_conditions)
            
            if q_obj.negated:
                q_sql = f"NOT ({q_sql})"
            
            return q_sql, q_params

        # Process include filters
        for filter_type, filter_data in self._filters:
            if filter_type == "Q":
                q_sql, q_params = build_q_condition(filter_data)
                if q_sql:
                    conditions.append(q_sql)
                    params.extend(q_params)
            elif filter_type == "AND":
                # Regular keyword argument filters
                for key, value in filter_data.items():
                    field_name, operator = builder.parse_lookup(key)
                    field_name, value = self._resolve_lookup(field_name, value)
                    condition, cond_params = builder.build_condition(
                        field_name, operator, value
                    )
                    conditions.append(condition)
                    params.extend(cond_params)

        # Process exclude filters (NOT (...))
        for filter_type, filter_data in self._excludes:
            if filter_type == "Q":
                q_sql, q_params = build_q_condition(filter_data)
                if q_sql:
                    conditions.append(f"NOT ({q_sql})")
                    params.extend(q_params)
            elif filter_type == "AND":
                # Regular keyword argument filters
                for key, value in filter_data.items():
                    field_name, operator = builder.parse_lookup(key)
                    field_name, value = self._resolve_lookup(field_name, value)
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
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        safe_builder = get_safe_builder(engine)
        builder = QueryBuilder(self.model, safe_builder)
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
        if connection is None and hasattr(conn, 'close'):
            conn.close()
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

        table = self._get_table_name()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()

        sql = f"SELECT COUNT(*) FROM {quoted_table}{where}"
        row = conn.fetchone(sql, params)
        if connection is None and hasattr(conn, 'close'):
            conn.close()
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

    def bulk_create(self, objs: list[Model], batch_size: int = 1000) -> list[Model]:
        """Create multiple models in bulk."""
        for obj in objs:
            obj.save()
        return objs

    def delete(self, connection: Any = None) -> int:
        """Delete all models matching this QuerySet safely."""
        conn = connection or self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self._get_table_name()
        quoted_table = builder.quote_table(table)
        where, params = self._build_where_clause()

        sql = f"DELETE FROM {quoted_table}{where}"
        logger.debug(f"Executing DELETE: {sql} with params: {params}")

        cursor = conn.execute(sql, params)
        conn.commit()
        rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
        logger.info(f"Deleted {rowcount} {self.model.__name__} rows")
        if connection is None and hasattr(conn, 'close'):
            conn.close()
        return rowcount

    def update(self, connection: Any = None, **values: Any) -> int:
        """Update all models matching this QuerySet with safe identifier quoting and F expression support."""
        from ..query.expressions import F
        
        if not values:
            return 0

        conn = connection or self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self._get_table_name()
        quoted_table = builder.quote_table(table)
        where, where_params = self._build_where_clause()

        # Build SET clause with safe identifier quoting and F expression support
        set_parts = []
        set_params = []
        for key, val in values.items():
            quoted_col = builder.quote_column(key)
            
            if isinstance(val, F):
                # F expression: use field reference directly without parameterization
                set_parts.append(f"{quoted_col} = {val.name}")
            else:
                # Regular value: parameterize
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
        if hasattr(conn, 'close'):
            conn.close()
        return rowcount

    def values(self, *fields: str) -> list[dict[str, Any]]:
        conn = self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self._get_table_name()
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
        if hasattr(conn, 'close'):
            conn.close()
        return result

    def values_list(
        self, *fields: str, flat: bool = False
    ) -> list[tuple[Any, ...] | Any]:
        conn = self._get_connection()
        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        builder = get_safe_builder(engine)

        table = self._get_table_name()
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
            if flat:
                if len(fields) != 1:
                    raise ValueError("flat=True requires exactly one field")
                if isinstance(row, dict):
                    result.append(row.get(fields[0]))
                else:
                    result.append(row[0])
            else:
                if isinstance(row, dict):
                    result.append(tuple(row.get(f) for f in fields))
                else:
                    result.append(tuple(row))
        if hasattr(conn, 'close'):
            conn.close()
        return result

    def in_bulk(self, id_list: list[Any] | None = None, *, field_name: str = "pk") -> dict[Any, Model]:
        """Return a dictionary mapping field_name values to model instances.
        
        Usage:
            Author.objects.in_bulk([1, 2, 3]) -> {1: Author(...), 2: Author(...), 3: Author(...)}
            Author.objects.in_bulk([1, 2], field_name='id')
        """
        if id_list is None:
            id_list = []
        
        # Get by primary key or specified field
        if field_name == "pk":
            field_name = next(
                (
                    name
                    for name, fld in self.model._meta.fields.items()
                    if fld.primary_key
                ),
                "id",
            )
        
        if id_list:
            filtered = self.filter(**{f"{field_name}__in": id_list})
        else:
            filtered = self
        
        results = filtered.all()
        bulk_dict = {}
        for obj in results:
            key = getattr(obj, field_name)
            bulk_dict[key] = obj
        
        return bulk_dict

    def union(self, *querysets: "QuerySet", all: bool = False) -> "QuerySet":
        """Return union of this QuerySet with other QuerySets.
        
        Usage:
            Author.objects.filter(age__gte=25).union(Author.objects.filter(status="active"))
        """
        clone = self._clone()
        for qs in querysets:
            if not isinstance(qs, QuerySet) or qs.model != self.model:
                raise TypeError("union() requires QuerySets of the same model")
        
        if querysets:
            clone._set_operation = ("UNION" if not all else "UNION ALL", querysets[0])
            if len(querysets) > 1:
                # Chain multiple unions
                result = clone
                for qs in querysets[1:]:
                    result = result.union(qs, all=all)
                return result
        
        return clone

    def intersection(self, *querysets: "QuerySet") -> "QuerySet":
        """Return intersection of this QuerySet with other QuerySets.
        
        Usage:
            Author.objects.filter(age__gte=25).intersection(Author.objects.filter(status="active"))
        """
        clone = self._clone()
        for qs in querysets:
            if not isinstance(qs, QuerySet) or qs.model != self.model:
                raise TypeError("intersection() requires QuerySets of the same model")
        
        if querysets:
            clone._set_operation = ("INTERSECT", querysets[0])
            if len(querysets) > 1:
                result = clone
                for qs in querysets[1:]:
                    result = result.intersection(qs)
                return result
        
        return clone

    def difference(self, *querysets: "QuerySet") -> "QuerySet":
        """Return difference of this QuerySet with other QuerySets.
        
        Usage:
            Author.objects.filter(age__gte=25).difference(Author.objects.filter(status="inactive"))
        """
        clone = self._clone()
        for qs in querysets:
            if not isinstance(qs, QuerySet) or qs.model != self.model:
                raise TypeError("difference() requires QuerySets of the same model")
        
        if querysets:
            clone._set_operation = ("EXCEPT", querysets[0])
            if len(querysets) > 1:
                result = clone
                for qs in querysets[1:]:
                    result = result.difference(qs)
                return result
        
        return clone

    def having(self, *args: Any, **kwargs: Any) -> "QuerySet":
        """Filter on aggregated values (must be used with annotate()).
        
        Usage:
            Product.objects.annotate(total_sales=Sum("sales")).having(total_sales__gte=1000)
        """
        if not self._annotations:
            raise ValueError("having() requires annotate() to be called first")
        
        from ..query.expressions import Q
        clone = self._clone()
        
        for arg in args:
            if isinstance(arg, Q):
                clone._having_conditions.append(("Q", arg))
            else:
                raise TypeError(f"having() takes Q objects or keyword arguments, not {type(arg)}")
        
        if kwargs:
            clone._having_conditions.append(("AND", kwargs))
        
        return clone

    def __iter__(self) -> Iterable[Model]:
        return iter(self.all())

    def __repr__(self) -> str:
        return f"<QuerySet [{self.count()}]>"

    def __bool__(self) -> bool:
        return self.exists()

    def __len__(self) -> int:
        return self.count()

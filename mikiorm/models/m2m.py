"""Many-to-Many relationship management.

Provides forward manager (add/remove/clear/all) and reverse descriptor.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, List

if TYPE_CHECKING:
    from .base import Model

from ..query.safe_builder import get_safe_builder
from ..conf.settings import settings


def _get_through_table(instance, field_name: str, field) -> str:
    """Compute through table name for a ManyToManyField."""
    if field.through:
        return field.through
    source_table = instance._meta.table_name or instance.__class__.__name__.lower() + "s"
    return f"{source_table}_{field_name}"


# ---------------------------------------------------------------------------
# Forward manager: used on the owning side (the model where field is defined)
# ---------------------------------------------------------------------------

class ManyToManyManager:
    """Manager for forward ManyToMany relations."""

    def __init__(self, instance, field) -> None:
        self.instance = instance
        self.field = field
        self._target_model = None

    @property
    def target_model(self):
        if self._target_model is None:
            from .base import Model
            to = self.field.to
            if isinstance(to, str):
                from .registry import ModelRegistry
                resolved = ModelRegistry.get_model(to)
                if resolved is None:
                    raise LookupError(f"Model '{to}' not found in registry")
                self._target_model = resolved
            else:
                self._target_model = to
        return self._target_model

    def _get_connection(self) -> Any:
        from ..conf.settings import connection_manager
        return connection_manager.get_connection()

    def _ensure_through_table(self) -> None:
        conn = self._get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.instance, self.field.name, self.field)
        quoted_table = builder.quote_table(through)
        source_col = builder.quote_column("source_id")
        target_col = builder.quote_column("target_id")
        sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
    {source_col} INTEGER NOT NULL,
    {target_col} INTEGER NOT NULL,
    PRIMARY KEY ({source_col}, {target_col})
)"""
        try:
            conn.execute(sql, ())
            conn.commit()
        except Exception:
            pass

    # -----------------------------------------------------------
    # Synchronous API
    # -----------------------------------------------------------

    def add(self, *objs: Model) -> None:
        if not objs:
            return
        self._ensure_through_table()
        conn = self._get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Source instance must be saved before adding relations")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        ph = builder.param_placeholder
        engine = settings.databases.get("default").engine
        for obj in objs:
            if obj.pk is None:
                raise ValueError("Target instance must be saved before linking")
            if engine == "sqlite":
                sql = f"INSERT OR IGNORE INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            elif engine == "postgresql":
                sql = f"INSERT INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph}) ON CONFLICT DO NOTHING"
            elif engine == "mysql":
                sql = f"INSERT IGNORE INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            else:
                sql = f"INSERT INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            try:
                conn.execute(sql, (src_pk, obj.pk))
            except Exception:
                pass
        conn.commit()

    def remove(self, obj) -> None:
        self._ensure_through_table()
        conn = self._get_connection()
        src_pk = self.instance.pk
        tgt_pk = obj.pk
        if src_pk is None or tgt_pk is None:
            raise ValueError("Instances must be saved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        ph = builder.param_placeholder
        sql = f"DELETE FROM {table} WHERE {src_col} = {ph} AND {tgt_col} = {ph}"
        conn.execute(sql, (src_pk, tgt_pk))
        conn.commit()

    def clear(self) -> None:
        self._ensure_through_table()
        conn = self._get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Instance must be saved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        ph = builder.param_placeholder
        sql = f"DELETE FROM {table} WHERE {src_col} = {ph}"
        conn.execute(sql, (src_pk,))
        conn.commit()

    def all(self) -> List:
        self._ensure_through_table()
        conn = self._get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Instance must be saved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        target_table = self.target_model._meta.table_name or self.target_model.__name__.lower() + "s"
        quoted_target = builder.quote_table(target_table)
        target_pk_col = builder.quote_column("id")
        ph = builder.param_placeholder
        sql = f"""
            SELECT t.* FROM {quoted_target} t
            JOIN {table} m2m ON t.{target_pk_col} = m2m.{tgt_col}
            WHERE m2m.{src_col} = {ph}
        """
        cursor = conn.execute(sql, (src_pk,))
        rows = cursor.fetchall()
        field_names = list(self.target_model._meta.fields.keys())
        result = []
        for row in rows:
            if isinstance(row, dict):
                kwargs = {n: row.get(n) for n in field_names if n in row}
            else:
                kwargs = {}
                for i, val in enumerate(row):
                    if i < len(field_names):
                        kwargs[field_names[i]] = val
            result.append(self.target_model(**kwargs))
        return result

    def count(self) -> int:
        return len(self.all())

    def __len__(self) -> int:
        return self.count()

    def __iter__(self):
        return iter(self.all())

    # -----------------------------------------------------------
    # Async API
    # -----------------------------------------------------------

    async def async_add(self, *objs) -> None:
        if not objs:
            return
        await self._async_ensure_through_table()
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Unsaved instance")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        ph = builder.param_placeholder
        engine = settings.databases.get("default").engine
        for obj in objs:
            if obj.pk is None:
                raise ValueError("Unsaved target")
            if engine == "sqlite":
                sql = f"INSERT OR IGNORE INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            elif engine == "postgresql":
                sql = f"INSERT INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph}) ON CONFLICT DO NOTHING"
            elif engine == "mysql":
                sql = f"INSERT IGNORE INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            else:
                sql = f"INSERT INTO {table} ({src_col}, {tgt_col}) VALUES ({ph}, {ph})"
            try:
                await conn.execute(sql, (src_pk, obj.pk))
            except Exception:
                pass
        await conn.commit()

    async def async_remove(self, obj) -> None:
        await self._async_ensure_through_table()
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        src_pk = self.instance.pk
        tgt_pk = obj.pk
        if src_pk is None or tgt_pk is None:
            raise ValueError("Unsaved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        ph = builder.param_placeholder
        sql = f"DELETE FROM {table} WHERE {src_col} = {ph} AND {tgt_col} = {ph}"
        await conn.execute(sql, (src_pk, tgt_pk))
        await conn.commit()

    async def async_clear(self) -> None:
        await self._async_ensure_through_table()
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Unsaved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        ph = builder.param_placeholder
        sql = f"DELETE FROM {table} WHERE {src_col} = {ph}"
        await conn.execute(sql, (src_pk,))
        await conn.commit()

    async def async_all(self) -> List:
        await self._async_ensure_through_table()
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        src_pk = self.instance.pk
        if src_pk is None:
            raise ValueError("Unsaved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        table = builder.quote_table(_get_through_table(self.instance, self.field.name, self.field))
        src_col = builder.quote_column("source_id")
        tgt_col = builder.quote_column("target_id")
        target_table = self.target_model._meta.table_name or self.target_model.__name__.lower() + "s"
        quoted_target = builder.quote_table(target_table)
        target_pk_col = builder.quote_column("id")
        ph = builder.param_placeholder
        sql = f"""
            SELECT t.* FROM {quoted_target} t
            JOIN {table} m ON t.{target_pk_col} = m.{tgt_col}
            WHERE m.{src_col} = {ph}
        """
        cursor = await conn.execute(sql, (src_pk,))
        rows = await cursor.fetchall()
        field_names = list(self.target_model._meta.fields.keys())
        result = []
        for row in rows:
            if isinstance(row, dict):
                kwargs = {n: row.get(n) for n in field_names if n in row}
            else:
                kwargs = {}
                for i, val in enumerate(row):
                    if i < len(field_names):
                        kwargs[field_names[i]] = val
            result.append(self.target_model(**kwargs))
        return result

    async def _async_ensure_through_table(self) -> None:
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.instance, self.field.name, self.field)
        quoted_table = builder.quote_table(through)
        source_col = builder.quote_column("source_id")
        target_col = builder.quote_column("target_id")
        sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
    {source_col} INTEGER NOT NULL,
    {target_col} INTEGER NOT NULL,
    PRIMARY KEY ({source_col}, {target_col})
)"""
        try:
            await conn.execute(sql, ())
            await conn.commit()
        except Exception:
            pass

    # Aliases to match Django API
    create = add

    def set(self, objs: List, clear: bool = False) -> None:
        if clear:
            self.clear()
        self.add(*objs)

    async def async_set(self, objs: List, clear: bool = False) -> None:
        if clear:
            await self.async_clear()
        await self.async_add(*objs)


# ---------------------------------------------------------------------------
# Reverse manager: used on the related_name side
# ---------------------------------------------------------------------------

class ReverseManyToManyManager:
    """Manager for reverse side of ManyToMany (via related_name)."""

    def __init__(self, instance, field, source_model) -> None:
        self.instance = instance
        self.field = field
        self.source_model = source_model
        self._target_model = None

    @property
    def target_model(self):
        if self._target_model is None:
            from .base import Model
            to = self.field.to
            if isinstance(to, str):
                from .registry import ModelRegistry
                resolved = ModelRegistry.get_model(to)
                if resolved is None:
                    raise LookupError(f"Model '{to}' not found in registry")
                self._target_model = resolved
            else:
                self._target_model = to
        return self._target_model

    def _get_connection(self) -> Any:
        from ..conf.settings import connection_manager
        return connection_manager.get_connection()

    def _ensure_through_table(self) -> None:
        conn = self._get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.source_model, self.field.name, self.field)
        quoted_table = builder.quote_table(through)
        source_col = builder.quote_column("source_id")
        target_col = builder.quote_column("target_id")
        sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
    {source_col} INTEGER NOT NULL,
    {target_col} INTEGER NOT NULL,
    PRIMARY KEY ({source_col}, {target_col})
)"""
        try:
            conn.execute(sql, ())
            conn.commit()
        except Exception:
            pass

    def all(self) -> List:
        self._ensure_through_table()
        conn = self._get_connection()
        tgt_pk = self.instance.pk
        if tgt_pk is None:
            raise ValueError("Instance must be saved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.source_model, self.field.name, self.field)
        table = builder.quote_table(through)
        target_col = builder.quote_column("target_id")
        source_col = builder.quote_column("source_id")
        source_table = self.source_model._meta.table_name or self.source_model.__name__.lower() + "s"
        quoted_source = builder.quote_table(source_table)
        source_pk_col = builder.quote_column("id")
        ph = builder.param_placeholder
        sql = f"""
            SELECT s.* FROM {quoted_source} s
            JOIN {table} m ON s.{source_pk_col} = m.{source_col}
            WHERE m.{target_col} = {ph}
        """
        cursor = conn.execute(sql, (tgt_pk,))
        rows = cursor.fetchall()
        field_names = list(self.source_model._meta.fields.keys())
        result = []
        for row in rows:
            if isinstance(row, dict):
                kwargs = {n: row.get(n) for n in field_names if n in row}
            else:
                kwargs = {}
                for i, val in enumerate(row):
                    if i < len(field_names):
                        kwargs[field_names[i]] = val
            result.append(self.source_model(**kwargs))
        return result

    def count(self) -> int:
        return len(self.all())

    def __len__(self) -> int:
        return self.count()

    def __iter__(self):
        return iter(self.all())

    async def async_all(self) -> List:
        await self._async_ensure_through_table()
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        tgt_pk = self.instance.pk
        if tgt_pk is None:
            raise ValueError("Unsaved")
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.source_model, self.field.name, self.field)
        table = builder.quote_table(through)
        target_col = builder.quote_column("target_id")
        source_col = builder.quote_column("source_id")
        source_table = self.source_model._meta.table_name or self.source_model.__name__.lower() + "s"
        quoted_source = builder.quote_table(source_table)
        source_pk_col = builder.quote_column("id")
        ph = builder.param_placeholder
        sql = f"""
            SELECT s.* FROM {quoted_source} s
            JOIN {table} m ON s.{source_pk_col} = m.{source_col}
            WHERE m.{target_col} = {ph}
        """
        cursor = await conn.execute(sql, (tgt_pk,))
        rows = await cursor.fetchall()
        field_names = list(self.source_model._meta.fields.keys())
        result = []
        for row in rows:
            if isinstance(row, dict):
                kwargs = {n: row.get(n) for n in field_names if n in row}
            else:
                kwargs = {}
                for i, val in enumerate(row):
                    if i < len(field_names):
                        kwargs[field_names[i]] = val
            result.append(self.source_model(**kwargs))
        return result

    async def _async_ensure_through_table(self) -> None:
        from ..conf.settings import async_connection_manager
        conn = await async_connection_manager.get_connection()
        builder = get_safe_builder(settings.databases.get("default").engine)
        through = _get_through_table(self.source_model, self.field.name, self.field)
        quoted_table = builder.quote_table(through)
        source_col = builder.quote_column("source_id")
        target_col = builder.quote_column("target_id")
        sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
    {source_col} INTEGER NOT NULL,
    {target_col} INTEGER NOT NULL,
    PRIMARY KEY ({source_col}, {target_col})
)"""
        try:
            await conn.execute(sql, ())
            await conn.commit()
        except Exception:
            pass
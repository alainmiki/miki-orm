"""Async SQLite adapter using aiosqlite."""

from __future__ import annotations

import aiosqlite
from typing import Any, Dict, Iterable, Tuple

from mikiorm.backends.base import BaseAsyncAdapter, BaseAsyncConnection, AsyncConnectionPool


class AsyncSQLiteConnection(BaseAsyncConnection):
    """Async SQLite connection wrapper with secure parameterized queries."""

    @property
    def param_placeholder(self) -> str:
        return "?"

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        cursor = await self._conn.execute(sql, params or ())
        return cursor

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        cursor = await self._conn.execute(sql, params or ())
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        cursor = await self._conn.execute(sql, params or ())
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.execute("BEGIN")

    async def close(self) -> None:
        await self._conn.close()

    async def enable_foreign_keys(self) -> None:
        """Enable foreign key constraints."""
        await self._conn.execute("PRAGMA foreign_keys = ON")

    async def get_database_version(self) -> str:
        """Return SQLite version string."""
        cursor = await self._conn.execute("SELECT sqlite_version()")
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else "unknown"


class AsyncSQLiteAdapter(BaseAsyncAdapter):
    """Async SQLite adapter for creating connections and pools."""

    async def connect(self, config: Dict[str, Any]) -> AsyncSQLiteConnection:
        database = config.get("NAME", ":memory:")
        timeout = config.get("timeout", 30.0)
        
        conn = await aiosqlite.connect(
            database,
            timeout=timeout,
        )
        
        # Enable foreign keys for data integrity
        await conn.execute("PRAGMA foreign_keys = ON")
        
        return AsyncSQLiteConnection(conn)

    async def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> AsyncConnectionPool:
        pool_config = pool_config or {}
        return AsyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )
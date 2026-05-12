"""Async SQLite adapter using aiosqlite."""

from __future__ import annotations

import aiosqlite
from typing import Any, Dict, Iterable, Tuple

from .base import BaseAsyncAdapter, BaseAsyncConnection


class AsyncSQLiteConnection(BaseAsyncConnection):
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
        return rows

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        cursor = await self._conn.execute(sql, params or ())
        return await cursor.fetchone()

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.execute("BEGIN")

    async def close(self) -> None:
        await self._conn.close()


class AsyncSQLiteAdapter(BaseAsyncAdapter):
    async def connect(self, config: Dict[str, Any]) -> AsyncSQLiteConnection:
        database = config.get("NAME", ":memory:")
        conn = await aiosqlite.connect(database)
        return AsyncSQLiteConnection(conn)

    async def create_pool(self, config: Dict[str, Any]) -> AsyncSQLiteConnection:
        # aiosqlite doesn't pool; return direct connection
        return await self.connect(config)

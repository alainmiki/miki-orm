"""Async MySQL adapter using aiomysql."""

import aiomysql
from typing import Any, List, Tuple, Optional, Dict, Iterable

from .base import BaseAsyncAdapter, BaseAsyncConnection


class AsyncMySQLConnection(BaseAsyncConnection):
    """Wrapper around an aiomysql connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    @property
    def param_placeholder(self) -> str:
        return "%s"

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        cursor = await self._conn.cursor()
        await cursor.execute(sql, params or ())
        return cursor

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        cursor = await self._conn.cursor()
        await cursor.execute(sql, params or ())
        rows = await cursor.fetchall()
        return rows

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        cursor = await self._conn.cursor()
        await cursor.execute(sql, params or ())
        return await cursor.fetchone()

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.begin()

    async def close(self) -> None:
        if self._conn:
            self._conn.close()


class AsyncMySQLAdapter(BaseAsyncAdapter):
    """Async MySQL database adapter using aiomysql."""

    async def connect(self, config: Dict[str, Any]) -> AsyncMySQLConnection:
        """Create and return an async MySQL connection."""
        conn = await aiomysql.connect(
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 3306)),
            user=config.get("USER"),
            password=config.get("PASSWORD", ""),
            db=config.get("NAME"),
            autocommit=True,
            **config.get("OPTIONS", {})
        )
        return AsyncMySQLConnection(conn)

    async def create_pool(self, config: Dict[str, Any]) -> AsyncMySQLConnection:
        # For simplicity, return direct connection without pooling
        return await self.connect(config)

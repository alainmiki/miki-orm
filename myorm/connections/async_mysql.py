"""Async MySQL adapter using aiomysql."""

import ssl
import aiomysql
from typing import Any, List, Tuple, Optional, Dict, Iterable

from .base import BaseAsyncAdapter, BaseAsyncConnection, AsyncConnectionPool


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

    def _build_ssl_context(self, ssl_config: Any) -> Any:
        if not ssl_config:
            return None
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    async def connect(self, config: Dict[str, Any]) -> AsyncMySQLConnection:
        """Create and return an async MySQL connection."""
        ssl_context = self._build_ssl_context(config.get("SSL", {}))
        conn = await aiomysql.connect(
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 3306)),
            user=config.get("USER"),
            password=config.get("PASSWORD", ""),
            db=config.get("NAME"),
            autocommit=True,
            ssl=ssl_context,
            **config.get("OPTIONS", {}),
        )
        return AsyncMySQLConnection(conn)

    async def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> AsyncConnectionPool:
        pool_config = pool_config or {}
        return AsyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )

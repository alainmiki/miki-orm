"""Async MySQL adapter using aiomysql."""

from __future__ import annotations

import ssl
from typing import Any, Dict, Iterable, List, Tuple, Optional

import aiomysql

from mikiorm.backends.base import BaseAsyncAdapter, BaseAsyncConnection, AsyncConnectionPool


class AsyncMySQLConnection(BaseAsyncConnection):
    """Async MySQL connection wrapper with secure parameterized queries."""

    @property
    def param_placeholder(self) -> str:
        return "%s"

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        cursor = await self._conn.cursor(aiomysql.DictCursor)
        await cursor.execute(sql, params or ())
        return cursor

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        cursor = await self._conn.cursor(aiomysql.DictCursor)
        await cursor.execute(sql, params or ())
        rows = await cursor.fetchall()
        await cursor.close()
        return [tuple(row.values()) for row in rows]

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Tuple[Any, ...]]:
        cursor = await self._conn.cursor(aiomysql.DictCursor)
        await cursor.execute(sql, params or ())
        row = await cursor.fetchone()
        await cursor.close()
        return tuple(row.values()) if row else None

    async def fetchmany(self, sql: str, params: Iterable[Any] | None = None, size: int = 100) -> List[Tuple[Any, ...]]:
        cursor = await self._conn.cursor(aiomysql.DictCursor)
        await cursor.execute(sql, params or ())
        rows = await cursor.fetchmany(size)
        await cursor.close()
        return [tuple(row.values()) for row in rows]

    async def executemany(self, sql: str, params_list: List[Tuple]) -> None:
        """Execute multiple rows efficiently."""
        async with self._conn.cursor() as cursor:
            await cursor.executemany(sql, params_list)

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.begin()

    async def close(self) -> None:
        if self._conn:
            self._conn.close()

    async def set_sql_mode(self) -> None:
        """Set strict SQL mode."""
        await self._conn.execute("SET sql_mode = 'STRICT_TRANS_TABLES'")


class AsyncMySQLAdapter(BaseAsyncAdapter):
    """Async MySQL adapter for creating connections and pools."""

    def _build_ssl_context(self, ssl_config: Any) -> Any:
        """Build SSL context from configuration."""
        if not ssl_config:
            return None
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    async def connect(self, config: Dict[str, Any]) -> AsyncMySQLConnection:
        ssl_context = self._build_ssl_context(config.get("SSL", {}))
        
        conn = await aiomysql.connect(
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 3306)),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            db=config.get("NAME"),
            charset="utf8mb4",
            autocommit=False,
            ssl=ssl_context,
            connect_timeout=config.get("OPTIONS", {}).get("connect_timeout", 10),
        )
        
        # Set strict SQL mode
        await conn.execute("SET sql_mode = 'STRICT_TRANS_TABLES'")
        
        return AsyncMySQLConnection(conn)

    async def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> AsyncConnectionPool:
        pool_config = pool_config or {}
        return AsyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 20),
            timeout=pool_config.get("timeout", 30),
        )

    async def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'`{name}`'
"""Async PostgreSQL adapter using asyncpg."""

from __future__ import annotations

import asyncio
import ssl
import asyncpg
from typing import Any, Dict, Iterable, Tuple

from .base import BaseAsyncAdapter, BaseAsyncConnection, AsyncConnectionPool


def _replace_placeholders(sql: str, param_count: int) -> str:
    """Convert pyformat %s placeholders to asyncpg $n style."""
    if param_count == 0:
        return sql
    # Replace each %s in order with $1, $2, ...
    parts = sql.split('%s')
    if len(parts) <= 1:
        return sql
    # Rebuild with $n placeholders
    result = parts[0]
    for i in range(1, len(parts)):
        result += f'${i}' + parts[i]
    return result


class AsyncPostgresConnection(BaseAsyncConnection):
    @property
    def param_placeholder(self) -> str:
        # Represent as pyformat %s for compatibility with query builder
        return "%s"

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        # Convert %s -> $n for asyncpg
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        return await self._conn.execute(sql, *params_list)

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        rows = await self._conn.fetch(sql, *params_list)
        # asyncpg returns Record objects; convert to tuples for consistency
        return [tuple(row.values()) for row in rows]

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        row = await self._conn.fetchrow(sql, *params_list)
        if row:
            return tuple(row.values())
        return None

    async def commit(self) -> None:
        await self._conn.execute("COMMIT")

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.execute("BEGIN")

    async def close(self) -> None:
        await self._conn.close()


class AsyncPostgresAdapter(BaseAsyncAdapter):
    def _build_ssl_context(self, ssl_config: Any) -> Any:
        if not ssl_config:
            return None
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    async def connect(self, config: Dict[str, Any]) -> AsyncPostgresConnection:
        ssl_context = self._build_ssl_context(config.get("SSL", {}))
        conn = await asyncpg.connect(
            database=config.get("NAME"),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 5432)),
            ssl=ssl_context,
        )
        return AsyncPostgresConnection(conn)

    async def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> AsyncConnectionPool:
        pool_config = pool_config or {}
        return AsyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )

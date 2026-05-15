"""Async PostgreSQL adapter using asyncpg."""

from __future__ import annotations

import ssl
import asyncpg
from typing import Any, Dict, Iterable, List, Tuple, Optional

from mikiorm.backends.base import BaseAsyncAdapter, BaseAsyncConnection, AsyncConnectionPool


def _replace_placeholders(sql: str, param_count: int) -> str:
    """Convert pyformat %s placeholders to asyncpg $n style.
    
    Args:
        sql: SQL string with %s placeholders
        param_count: Number of parameters to determine replacement
        
    Returns:
        SQL string with $1, $2, ... placeholders
    """
    if param_count == 0:
        return sql
    parts = sql.split('%s')
    if len(parts) <= 1:
        return sql
    result = parts[0]
    for i in range(1, len(parts)):
        result += f'${i}' + parts[i]
    return result


class AsyncPostgresConnection(BaseAsyncConnection):
    """Async PostgreSQL connection wrapper with secure parameterized queries."""

    @property
    def param_placeholder(self) -> str:
        return "%s"  # Returns pyformat for compatibility with query builder

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        return await self._conn.execute(sql, *params_list)

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        rows = await self._conn.fetch(sql, *params_list)
        return [tuple(row.values()) for row in rows]

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Tuple[Any, ...]]:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        row = await self._conn.fetchrow(sql, *params_list)
        return tuple(row.values()) if row else None

    async def fetchmany(self, sql: str, params: Iterable[Any] | None = None, size: int = 100) -> List[Tuple[Any, ...]]:
        params_list = list(params) if params else []
        sql = _replace_placeholders(sql, len(params_list))
        rows = await self._conn.fetch(sql, *params_list)
        return [tuple(row.values()) for row in rows[:size]]

    async def executemany(self, sql: str, params_list: List[Tuple]) -> None:
        """Execute many rows efficiently."""
        sql_converted = _replace_placeholders(sql, len(params_list[0]) if params_list else 0)
        await self._conn.executemany(sql_converted, params_list)

    async def commit(self) -> None:
        await self._conn.execute("COMMIT")

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def begin(self) -> None:
        await self._conn.execute("BEGIN")

    async def close(self) -> None:
        await self._conn.close()

    async def set_timezone(self, tz: str = 'UTC') -> None:
        """Set session timezone."""
        await self._conn.execute(f"SET TIME ZONE '{tz}'")


class AsyncPostgresAdapter(BaseAsyncAdapter):
    """Async PostgreSQL adapter for creating connections and pools."""

    def _build_ssl_context(self, ssl_config: Any) -> Any:
        """Build SSL context from configuration."""
        if not ssl_config:
            return False
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
            connect_timeout=config.get("OPTIONS", {}).get("connect_timeout", 10),
            command_timeout=config.get("OPTIONS", {}).get("command_timeout", 30),
        )
        
        # Set timezone to UTC
        await conn.execute("SET TIME ZONE 'UTC'")
        
        return AsyncPostgresConnection(conn)

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
        return f'"{name}"'
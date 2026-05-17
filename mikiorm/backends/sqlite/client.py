"""SQLite database client and adapter."""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence, Type

from mikiorm.backends.base.adapter import (
    BaseAdapter,
    BaseAsyncAdapter,
    BaseAsyncConnection,
    BaseConnection,
)
from mikiorm.backends.base.base import BaseDatabaseWrapper, DatabaseSettings
from mikiorm.backends.base.pool import (
    AsyncConnectionPool,
    PooledAsyncConnection,
    PooledConnection,
    SyncConnectionPool,
)
from mikiorm.backends.sqlite.introspection import SQLiteIntrospection
from mikiorm.backends.sqlite.schema import SQLiteSchemaEditor


class SQLiteConnection(BaseConnection):
    """Wrapper for sqlite3.Connection."""

    param_placeholder = "?"

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._connection.row_factory = sqlite3.Row  # Return rows as dict-like objects

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return self._connection.execute(sql, params)

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = self._connection.execute(sql, params)
        row = cursor.fetchone()
        return tuple(row) if row else None

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Any]:
        cursor = self._connection.execute(sql, params)
        rows = cursor.fetchall()
        return [tuple(row) for row in rows]

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def is_valid(self) -> bool:
        """Check if the connection is still valid."""
        try:
            self._connection.execute("SELECT 1")
            return True
        except Exception:
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SQLiteAdapter(BaseAdapter):
    """Adapter for synchronous SQLite connections."""

    connection_class: Type[BaseConnection] = SQLiteConnection

    def connect(self, config: dict[str, Any]) -> BaseConnection:
        conn = sqlite3.connect(config.get("NAME", ":memory:"))
        conn.row_factory = sqlite3.Row
        return self.connection_class(conn)

    def release(self, connection: PooledConnection) -> None:
        connection.close()


class SQLiteAsyncConnection(BaseAsyncConnection):
    """Placeholder for async SQLite connection (requires aiosqlite)."""

    def __init__(self, connection: Any):  # Expects aiosqlite.Connection
        self._connection = connection

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return await self._connection.execute(sql, params)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = await self._connection.execute(sql, params)
        row = await cursor.fetchone()
        return tuple(row) if row else None

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Any]:
        cursor = await self._connection.execute(sql, params)
        rows = await cursor.fetchall()
        return [tuple(row) for row in rows]

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()

    async def close(self) -> None:
        await self._connection.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class SQLiteAsyncAdapter(BaseAsyncAdapter):
    """Adapter for asynchronous SQLite connections using aiosqlite."""

    connection_class: Type[BaseAsyncConnection] = SQLiteAsyncConnection

    async def connect(self, config: dict[str, Any]) -> BaseAsyncConnection:
        try:
            import aiosqlite
        except ImportError:
            raise ImportError(
                "The 'aiosqlite' library is required for async SQLite support."
                "Install it with 'pip install aiosqlite'."
            )
        conn = await aiosqlite.connect(config.get("NAME", ":memory:"))
        conn.row_factory = sqlite3.Row
        return self.connection_class(conn)

    async def release(self, connection: PooledAsyncConnection) -> None:
        await connection.close()


class DatabaseWrapper(BaseDatabaseWrapper):
    """SQLite database wrapper."""

    vendor = "sqlite"
    display_name = "SQLite"
    adapter_cls = SQLiteAdapter
    async_adapter_cls = SQLiteAsyncAdapter
    introspection_cls = SQLiteIntrospection
    schema_editor_cls = SQLiteSchemaEditor
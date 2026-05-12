"""Connection adapters package."""

from .base import (
    BaseConnection,
    BaseAdapter,
    BaseAsyncConnection,
    BaseAsyncAdapter,
)
from .mysql import MySQLAdapter, MySQLConnection
from .postgres import PostgresAdapter, PostgresConnection
from .sqlite import SQLiteAdapter, SQLiteConnection

try:
    from .async_sqlite import AsyncSQLiteAdapter, AsyncSQLiteConnection
    from .async_postgres import AsyncPostgresAdapter, AsyncPostgresConnection
    from .async_mysql import AsyncMySQLAdapter, AsyncMySQLConnection
    _async_available = True
except ImportError:
    _async_available = False

__all__ = [
    "BaseConnection",
    "BaseAdapter",
    "BaseAsyncConnection",
    "BaseAsyncAdapter",
    "MySQLAdapter",
    "MySQLConnection",
    "PostgresAdapter",
    "PostgresConnection",
    "SQLiteAdapter",
    "SQLiteConnection",
    "AsyncSQLiteAdapter",
    "AsyncSQLiteConnection",
    "AsyncPostgresAdapter",
    "AsyncPostgresConnection",
    "AsyncMySQLAdapter",
    "AsyncMySQLConnection",
]

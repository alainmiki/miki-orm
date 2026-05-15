"""Backend package - adapter implementations per engine.

Public re-exports follow the PRD/structure shape:

    from mikiorm.backends import SQLite, Postgres, MySQL
    from mikiorm.backends import BaseAdapter, BaseConnection

Concrete adapter classes are imported lazily through helper accessors so a
missing driver (psycopg2, pymysql, asyncpg, aiosqlite) does not crash the
top-level import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import (
    AsyncConnectionPool,
    BaseAdapter,
    BaseAsyncAdapter,
    BaseAsyncConnection,
    BaseConnection,
    BaseDatabaseWrapper,
    DatabaseSettings,
    Dialect,
    PooledAsyncConnection,
    PooledConnection,
    SafeBuilder,
    SchemaEditor,
    SyncConnectionPool,
    field_to_sql_type,
    get_dialect_from_engine,
    get_param_placeholder,
    get_safe_builder,
)


def _lazy(import_path: str, attr: str):
    """Build an attribute proxy that imports on first access."""

    class _Lazy:
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            module = __import__(import_path, fromlist=[attr])
            target = getattr(module, attr)
            globals()[attr] = target
            return target(*args, **kwargs)

        def __getattr__(self, name: str) -> Any:
            module = __import__(import_path, fromlist=[attr])
            target = getattr(module, attr)
            globals()[attr] = target
            return getattr(target, name)

    return _Lazy()


if TYPE_CHECKING:  # pragma: no cover - imports only used for type hints
    from .mysql.async_mysql import AsyncMySQLAdapter as AsyncMySQL
    from .mysql.base import MySQLAdapter as MySQL
    from .postgresql.async_postgresql import AsyncPostgresAdapter as AsyncPostgres
    from .postgresql.base import PostgresAdapter as Postgres
    from .sqlite.async_sqlite import AsyncSQLiteAdapter as AsyncSQLite
    from .sqlite.base import SQLiteAdapter as SQLite


# Friendly aliases - lazy so unused drivers don't pull in their packages.
SQLite = _lazy("mikiorm.backends.sqlite.base", "SQLiteAdapter")
AsyncSQLite = _lazy("mikiorm.backends.sqlite.async_sqlite", "AsyncSQLiteAdapter")
Postgres = _lazy("mikiorm.backends.postgresql.base", "PostgresAdapter")
AsyncPostgres = _lazy(
    "mikiorm.backends.postgresql.async_postgresql", "AsyncPostgresAdapter"
)
MySQL = _lazy("mikiorm.backends.mysql.base", "MySQLAdapter")
AsyncMySQL = _lazy("mikiorm.backends.mysql.async_mysql", "AsyncMySQLAdapter")


__all__ = [
    # base interfaces
    "BaseAdapter",
    "BaseAsyncAdapter",
    "BaseConnection",
    "BaseAsyncConnection",
    "BaseDatabaseWrapper",
    "DatabaseSettings",
    # pooling
    "AsyncConnectionPool",
    "SyncConnectionPool",
    "PooledConnection",
    "PooledAsyncConnection",
    # dialect / sql
    "Dialect",
    "SafeBuilder",
    "SchemaEditor",
    "field_to_sql_type",
    "get_dialect_from_engine",
    "get_param_placeholder",
    "get_safe_builder",
    # concrete adapters
    "SQLite",
    "AsyncSQLite",
    "Postgres",
    "AsyncPostgres",
    "MySQL",
    "AsyncMySQL",
]

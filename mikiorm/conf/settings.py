"""Universal database configuration and connection management.

Public surface:

* :class:`DatabaseConfig` - typed view of one DATABASES entry.
* :class:`Settings` - global container (DATABASES, INSTALLED_APPS, ...).
* :data:`settings` - the singleton; populated by :func:`configure`.
* :func:`configure` - one-shot entry point used by application code.
* :class:`ConnectionManager` / :class:`AsyncConnectionManager` - lazily
  build and reuse a single pool per alias, returning checked-out
  connections via context managers.

The actual driver glue lives under :mod:`mikiorm.backends.{sqlite,postgresql,mysql}`.
This module deliberately stays driver-agnostic so a new backend can be added
by registering its adapter class.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

from ..backends.base import (
    AsyncConnectionPool,
    BaseAdapter,
    BaseAsyncAdapter,
    PooledAsyncConnection,
    PooledConnection,
    SyncConnectionPool,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------
# Lazy imports avoid pulling psycopg2 / asyncpg / pymysql until they are
# actually needed.  Adapter factories return *classes* so registration is
# cheap and import errors surface only when the user actually requests
# that engine.

_SYNC_ADAPTERS: Dict[str, Callable[[], type[BaseAdapter]]] = {}
_ASYNC_ADAPTERS: Dict[str, Callable[[], type[BaseAsyncAdapter]]] = {}


def register_sync_adapter(engine: str, factory: Callable[[], type[BaseAdapter]]) -> None:
    """Register a sync adapter factory for an engine name."""
    _SYNC_ADAPTERS[engine] = factory


def register_async_adapter(
    engine: str, factory: Callable[[], type[BaseAsyncAdapter]]
) -> None:
    """Register an async adapter factory for an engine name."""
    _ASYNC_ADAPTERS[engine] = factory


def _sqlite_sync() -> type[BaseAdapter]:
    from ..backends.sqlite.base import SQLiteAdapter

    return SQLiteAdapter


def _sqlite_async() -> type[BaseAsyncAdapter]:
    from ..backends.sqlite.async_sqlite import AsyncSQLiteAdapter

    return AsyncSQLiteAdapter


def _postgres_sync() -> type[BaseAdapter]:
    from ..backends.postgresql.base import PostgresAdapter

    return PostgresAdapter


def _postgres_async() -> type[BaseAsyncAdapter]:
    from ..backends.postgresql.async_postgresql import AsyncPostgresAdapter

    return AsyncPostgresAdapter


def _mysql_sync() -> type[BaseAdapter]:
    from ..backends.mysql.base import MySQLAdapter

    return MySQLAdapter


def _mysql_async() -> type[BaseAsyncAdapter]:
    from ..backends.mysql.async_mysql import AsyncMySQLAdapter

    return AsyncMySQLAdapter


# Register the built-in engines.
for _name, _sync, _async in (
    ("sqlite", _sqlite_sync, _sqlite_async),
    ("postgresql", _postgres_sync, _postgres_async),
    ("postgres", _postgres_sync, _postgres_async),  # alias
    ("mysql", _mysql_sync, _mysql_async),
):
    register_sync_adapter(_name, _sync)
    register_async_adapter(_name, _async)


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------


class DatabaseConfig:
    """Typed view of one entry in ``settings.DATABASES``."""

    __slots__ = (
        "engine",
        "name",
        "user",
        "password",
        "host",
        "port",
        "options",
        "ssl",
        "pool",
        "secrets",
    )

    def __init__(self, config: Dict[str, Any]) -> None:
        self.engine = str(config.get("ENGINE", "sqlite"))
        self.name = config.get("NAME", ":memory:")
        self.user = config.get("USER")
        self.password = config.get("PASSWORD")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT")
        self.options = dict(config.get("OPTIONS", {}) or {})
        self.ssl = config.get("SSL") or {}
        self.pool = dict(config.get("POOL", {}) or {})
        self.secrets = dict(config.get("SECRETS", {}) or {})

    # ------------------------------------------------------------------
    # Adapter construction
    # ------------------------------------------------------------------
    def get_sync_adapter(self) -> BaseAdapter:
        factory = _SYNC_ADAPTERS.get(self.engine)
        if factory is None:
            raise ValueError(
                f"Unsupported engine: {self.engine!r}. "
                f"Known: {sorted(_SYNC_ADAPTERS)}"
            )
        return factory()()

    def get_async_adapter(self) -> BaseAsyncAdapter:
        factory = _ASYNC_ADAPTERS.get(self.engine)
        if factory is None:
            raise ValueError(
                f"Unsupported async engine: {self.engine!r}. "
                f"Known: {sorted(_ASYNC_ADAPTERS)}"
            )
        return factory()()

    # Legacy alias kept for older call sites.
    def get_adapter(self) -> BaseAdapter:
        return self.get_sync_adapter()

    # ------------------------------------------------------------------
    # Connection options + secret resolution
    # ------------------------------------------------------------------
    def get_connection_config(self) -> Dict[str, Any]:
        """Build the kwargs dict each adapter consumes."""
        config: Dict[str, Any] = {
            "NAME": self.name,
            "USER": self.user,
            "PASSWORD": self.password,
            "HOST": self.host,
            "PORT": self.port,
            "OPTIONS": dict(self.options),
        }
        # Pull any environment-backed secrets in.  Each entry maps a config
        # key (NAME/USER/PASSWORD/...) to an environment variable name.
        for key, env_var in self.secrets.items():
            env_val = os.getenv(env_var)
            if env_val is not None:
                config[key] = env_val
        if self.ssl:
            config["SSL"] = self.ssl
        return config

    def get_pool_config(self) -> Dict[str, Any]:
        return {
            "min_size": int(self.pool.get("min_size", 1)),
            "max_size": int(self.pool.get("max_size", 5)),
            "timeout": float(self.pool.get("timeout", 30)),
            "max_lifetime": float(self.pool.get("max_lifetime", 0)),
            "max_uses": int(self.pool.get("max_uses", 0)),
            "pre_ping": bool(self.pool.get("pre_ping", False)),
        }


# ---------------------------------------------------------------------------
# Connection managers
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Lazily build one :class:`SyncConnectionPool` per alias and hand out
    pooled connections.

    The default behaviour is *acquire on demand, release on close*.  Callers
    that want explicit lifetime control should use :meth:`connection` as a
    context manager.
    """

    def __init__(self) -> None:
        self._pools: Dict[str, SyncConnectionPool] = {}
        self._lock = threading.Lock()

    def get_pool(self, db_alias: str = "default") -> SyncConnectionPool:
        if db_alias not in self._pools:
            with self._lock:
                if db_alias not in self._pools:
                    db_config = settings.get_database(db_alias)
                    adapter = db_config.get_sync_adapter()
                    self._pools[db_alias] = adapter.create_pool(
                        db_config.get_connection_config(),
                        db_config.get_pool_config(),
                    )
        return self._pools[db_alias]

    def get_connection(self, db_alias: str = "default") -> PooledConnection:
        """Borrow a pooled connection.  Caller must release/close it."""
        return self.get_pool(db_alias).acquire()

    @contextmanager
    def connection(self, db_alias: str = "default") -> Iterator[PooledConnection]:
        conn = self.get_connection(db_alias)
        try:
            yield conn
        finally:
            conn.close()

    def validate_connection(self, db_alias: str = "default") -> bool:
        try:
            with self.connection(db_alias) as conn:
                return bool(conn.fetchone("SELECT 1", ()))
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("validate_connection(%s) failed: %s", db_alias, exc)
            return False

    def close_all(self) -> None:
        for pool in list(self._pools.values()):
            try:
                pool.close()
            except Exception:
                pass
        self._pools.clear()


class AsyncConnectionManager:
    """Async counterpart of :class:`ConnectionManager`."""

    def __init__(self) -> None:
        self._pools: Dict[str, AsyncConnectionPool] = {}
        self._lock_factory = None  # asyncio.Lock created lazily per loop

    async def get_pool(self, db_alias: str = "default") -> AsyncConnectionPool:
        if db_alias not in self._pools:
            db_config = settings.get_database(db_alias)
            adapter = db_config.get_async_adapter()
            self._pools[db_alias] = await adapter.create_pool(
                db_config.get_connection_config(),
                db_config.get_pool_config(),
            )
        return self._pools[db_alias]

    async def get_connection(self, db_alias: str = "default") -> PooledAsyncConnection:
        pool = await self.get_pool(db_alias)
        return await pool.acquire()

    async def validate_connection(self, db_alias: str = "default") -> bool:
        try:
            conn = await self.get_connection(db_alias)
        except Exception:
            return False
        try:
            return bool(await conn.fetchone("SELECT 1", ()))
        except Exception:
            return False
        finally:
            try:
                await conn.close()
            except Exception:
                pass

    async def close_all(self) -> None:
        for pool in list(self._pools.values()):
            try:
                await pool.close()
            except Exception:
                pass
        self._pools.clear()


# ---------------------------------------------------------------------------
# Settings container
# ---------------------------------------------------------------------------


class Settings:
    """Global container for ORM settings (Django-style ``DATABASES`` etc.)."""

    def __init__(self) -> None:
        self.databases: Dict[str, DatabaseConfig] = {}
        self.default_database: str = "default"
        self.installed_apps: list[str] = []
        self.migration_path: str = "migrations"
        self.logging: Dict[str, Any] = {}

    def configure_databases(self, databases: Dict[str, Dict[str, Any]]) -> None:
        for alias, config in databases.items():
            self.databases[alias] = DatabaseConfig(config)

    def install_app(self, app_name: str) -> None:
        if app_name in self.installed_apps:
            return
        importlib.import_module(app_name)
        self.installed_apps.append(app_name)
        # Pull in the conventional ``app.models`` module if present so model
        # classes register themselves with the ORM registry.
        try:
            importlib.import_module(f"{app_name}.models")
        except ModuleNotFoundError:
            pass

    def get_database(self, name: Optional[str] = None) -> DatabaseConfig:
        alias = name or self.default_database
        if alias not in self.databases:
            raise ValueError(
                f"Database alias {alias!r} is not configured. "
                "Call mikiorm.configure(...) first."
            )
        return self.databases[alias]


# Singletons -----------------------------------------------------------------
settings = Settings()
connection_manager = ConnectionManager()
async_connection_manager = AsyncConnectionManager()


def configure(
    databases: Dict[str, Dict[str, Any]] | None = None,
    *,
    installed_apps: Optional[list[str]] = None,
    migration_path: Optional[str] = None,
    default_database: Optional[str] = None,
    logging_config: Optional[Dict[str, Any]] = None,
) -> None:
    """One-shot configuration entry point used by application code.

    Example::

        from mikiorm import configure
        configure({
            "default": {"ENGINE": "sqlite", "NAME": "app.db"},
        }, migration_path="db/migrations")
    """
    if databases is not None:
        # Reset existing pools so the new config takes effect.
        connection_manager.close_all()
        # AsyncConnectionManager pools cannot be closed synchronously; they
        # will be closed by the user via close_all() if needed.
        async_connection_manager._pools.clear()
        settings.databases.clear()
        settings.configure_databases(databases)
    if default_database is not None:
        settings.default_database = default_database
    if migration_path is not None:
        settings.migration_path = migration_path
    if logging_config is not None:
        settings.logging.update(logging_config)
    if installed_apps:
        for app in installed_apps:
            settings.install_app(app)


__all__ = [
    "AsyncConnectionManager",
    "ConnectionManager",
    "DatabaseConfig",
    "Settings",
    "async_connection_manager",
    "configure",
    "connection_manager",
    "register_async_adapter",
    "register_sync_adapter",
    "settings",
]

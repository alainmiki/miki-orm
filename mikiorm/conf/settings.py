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
import time
import asyncio
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


def _oracle_sync() -> type[BaseAdapter]:
    from ..backends.oracle.base import OracleAdapter

    return OracleAdapter


# Register the built-in engines.
for _name, _sync, _async in (
    ("sqlite", _sqlite_sync, _sqlite_async),
    ("postgresql", _postgres_sync, _postgres_async),
    ("postgres", _postgres_sync, _postgres_async),  # alias
    ("mysql", _mysql_sync, _mysql_async),
    ("oracle", _oracle_sync, None),
):
    register_sync_adapter(_name, _sync)
    if _async:
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
            "max_retries": int(self.pool.get("max_retries", 3)),
            "retry_delay": float(self.pool.get("retry_delay", 0.5)),
            "cb_threshold": int(self.pool.get("cb_threshold", 5)),
            "cb_timeout": float(self.pool.get("cb_timeout", 60.0)),
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
                    pool_config = db_config.get_pool_config()
                    
                    logger.debug("Initializing sync connection pool for %s", db_alias)
                    self._pools[db_alias] = adapter.create_pool(
                        db_config.get_connection_config(),
                        pool_config,
                    )
        return self._pools[db_alias]

    def get_connection(self, db_alias: str = "default") -> PooledConnection:
        """Borrow a pooled connection.  Caller must release/close it."""
        db_config = settings.get_database(db_alias)
        pool_config = db_config.get_pool_config()
        max_retries = pool_config["max_retries"]
        retry_delay = pool_config["retry_delay"]

        for attempt in range(max_retries + 1):
            try:
                return self.get_pool(db_alias).acquire()
            except TimeoutError:
                if attempt >= max_retries:
                    logger.error("Failed to acquire connection from pool %s after %d retries", db_alias, max_retries)
                    raise
                
                wait = retry_delay * (2 ** attempt)
                logger.warning(
                    "Connection pool %s exhausted. Retrying in %.2fs (attempt %d/%d)",
                    db_alias, wait, attempt + 1, max_retries
                )
                time.sleep(wait)

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
                return conn.is_valid()
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


class CircuitBreaker:
    """Simple circuit breaker to handle database downtime."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.monotonic()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def can_execute(self) -> bool:
        if self.state == "OPEN":
            if (time.monotonic() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True


class AsyncConnectionContext:
    """Async context manager for acquiring and releasing pooled connections."""

    def __init__(self, manager: AsyncConnectionManager, db_alias: str) -> None:
        self.manager = manager
        self.db_alias = db_alias
        self.conn: Optional[PooledAsyncConnection] = None

    async def __aenter__(self) -> PooledAsyncConnection:
        self.conn = await self.manager.get_connection(self.db_alias)
        return self.conn

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.conn:
            try:
                await self.conn.close()
            except Exception:
                pass


class AsyncConnectionManager:
    """Async counterpart of :class:`ConnectionManager`."""

    def __init__(self) -> None:
        self._pools: Dict[str, AsyncConnectionPool] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def _get_circuit_breaker(self, db_alias: str) -> CircuitBreaker:
        if db_alias not in self._circuit_breakers:
            db_config = settings.get_database(db_alias)
            pool_config = db_config.get_pool_config()
            self._circuit_breakers[db_alias] = CircuitBreaker(
                failure_threshold=pool_config["cb_threshold"],
                recovery_timeout=pool_config["cb_timeout"]
            )
        return self._circuit_breakers[db_alias]

    def _get_lock(self) -> asyncio.Lock:
        """Lazy-init the lock to ensure it is created in the correct event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_pool(self, db_alias: str = "default") -> AsyncConnectionPool:
        if db_alias not in self._pools:
            async with self._get_lock():
                # Double-check pattern to avoid redundant pool creation
                if db_alias not in self._pools:
                    db_config = settings.get_database(db_alias)
                    try:
                        adapter = db_config.get_async_adapter()
                    except ValueError as e:
                        raise RuntimeError(f"Async operations not supported for engine {db_config.engine}: {e}")
                        
                    self._pools[db_alias] = await adapter.create_pool(
                        db_config.get_connection_config(),
                        db_config.get_pool_config(),
                    )
        return self._pools[db_alias]

    async def get_connection(self, db_alias: str = "default") -> PooledAsyncConnection:
        """Borrow a pooled connection with exponential backoff and retry (async)."""
        cb = self._get_circuit_breaker(db_alias)
        if not cb.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN for database {db_alias}")

        db_config = settings.get_database(db_alias)
        pool_config = db_config.get_pool_config()
        max_retries = pool_config["max_retries"]
        retry_delay = pool_config["retry_delay"]

        for attempt in range(max_retries + 1):
            try:
                pool = await self.get_pool(db_alias)
                conn = await pool.acquire()
                cb.record_success()
                return conn
            except asyncio.TimeoutError:
                if attempt >= max_retries:
                    cb.record_failure()
                    logger.error("Async: Failed to acquire connection from pool %s after %d retries", db_alias, max_retries)
                    raise

                wait = retry_delay * (2 ** attempt)
                logger.warning(
                    "Async: Connection pool %s exhausted. Retrying in %.2fs (attempt %d/%d)",
                    db_alias, wait, attempt + 1, max_retries
                )
                await asyncio.sleep(wait)
            except Exception:
                cb.record_failure()
                raise

    @contextmanager
    def connection(self, db_alias: str = "default"):
        """
        This is a legacy helper. For async usage, prefer the manual 
        acquire/release pattern or implement an async context manager.
        """
        raise RuntimeError("Use 'async with connection_manager.async_connection()' for async logic.")

    def async_connection(self, db_alias: str = "default") -> AsyncConnectionContext:
        """Borrow a pooled connection via async context manager."""
        return AsyncConnectionContext(self, db_alias)

    async def validate_connection(self, db_alias: str = "default") -> bool:
        try:
            async with self.async_connection(db_alias) as conn:
                return await conn.is_valid(timeout=5.0)
        except Exception:
            return False

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

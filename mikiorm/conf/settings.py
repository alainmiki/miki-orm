"""Universal database configuration and connection management.

Public surface:

* :class:`DatabaseConfig` - typed view of one DATABASES entry.
* :class:`AppConfig`       - metadata for one INSTALLED_APPS entry.
* :class:`Settings`        - global container (DATABASES, INSTALLED_APPS, ...).
* :data:`settings`         - the singleton; populated by :func:`configure`.
* :func:`configure`        - one-shot entry point used by application code.
* :func:`configure_from_module` - load settings from a Python module (Django-style).
* :func:`generate_settings_template` - produce a ready-to-edit settings.py scaffold.
* :class:`ConnectionManager` / :class:`AsyncConnectionManager` - lazily
  build and reuse a single pool per alias, returning checked-out
  connections via context managers.

The actual driver glue lives under :mod:`mikiorm.backends.{sqlite,postgresql,mysql}`.
This module deliberately stays driver-agnostic so a new backend can be added
by registering its adapter class.
"""

from __future__ import annotations

import importlib
import keyword
import logging
import os
import sys
import time
import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

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
# Security: Reserved Python keywords (app names must not clash)
# ---------------------------------------------------------------------------
_RESERVED_KEYWORDS: frozenset = frozenset(
    {
        "false",
        "none",
        "true",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
    }
)

# ---------------------------------------------------------------------------
# Security: disallowed top-level packages for settings-import safety
# ---------------------------------------------------------------------------
_DISALLOWED_MODULE_PREFIXES: Tuple[str, ...] = (
    "os",
    "sys",
    "subprocess",
    "importlib",
    "shutil",
    "code",
    "builtins",
    "posix",
    "nt",
    "io",
    "socket",
)

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
# AppConfig metadata — mirrors a single INSTALLED_APPS entry
# ---------------------------------------------------------------------------


class AppConfig:
    """Metadata for one entry in ``settings.INSTALLED_APPS``.

    Attributes:
        name: Dotted Python path to the app package (e.g. ``"users"``).
        path: Absolute filesystem path to the app directory.
              Resolved from *name* when not supplied explicitly.
        label: Short label used in migration table names and model
               namespacing.  Defaults to the last path component of *name*.
    """

    __slots__ = ("name", "path", "label")

    def __init__(
        self,
        name: str,
        path: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        _validate_app_name(name)
        self.name = name
        self.path = str(Path(path).resolve()) if path else _resolve_app_path(name)
        self.label = label or name.split(".")[-1]
        _validate_app_label(self.label)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"AppConfig(name={self.name!r}, path={self.path!r}, "
            f"label={self.label!r})"
        )


# ---------------------------------------------------------------------------
# Security validators
# ---------------------------------------------------------------------------


def _validate_app_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a safe Python identifier or module path."""
    if not name or not isinstance(name, str):
        raise ValueError("App name must be a non-empty string")

    for part in name.split("."):
        if not part.isidentifier():
            raise ValueError(
                f"Invalid app name {name!r}: segment {part!r} must be a valid Python identifier"
            )
        if part.lower() in _RESERVED_KEYWORDS:
            raise ValueError(
                f"Invalid app name {name!r}: segment {part!r} conflicts with a Python keyword"
            )


def _validate_app_label(label: str) -> None:
    """Raise ``ValueError`` if the app label is not a safe identifier."""
    if not label or not isinstance(label, str):
        raise ValueError("App label must be a non-empty string")
    if not label.isidentifier():
        raise ValueError(
            f"Invalid app label {label!r}: must be a valid Python identifier"
        )
    if label.lower() in _RESERVED_KEYWORDS:
        raise ValueError(
            f"Invalid app label {label!r}: conflicts with a Python keyword"
        )


def _validate_app_path(path: str, app_name: str) -> None:
    """Raise ``ValueError`` if *path* resolves outside the project root."""
    resolved = Path(path).resolve()
    cwd = Path.cwd().resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError:
        # Allow when an explicit allowlist env-var is set.
        allowed_root = os.getenv("MIKIORM_ALLOWED_PROJECT_ROOT", "").strip()
        if allowed_root:
            try:
                resolved.relative_to(Path(allowed_root).resolve())
                return
            except ValueError:
                pass
        raise ValueError(
            f"App path for {app_name!r} ({resolved}) is outside the current "
            "working directory.  Set MIKIORM_ALLOWED_PROJECT_ROOT to allow it."
        )


def _validate_module_path(module_path: str) -> None:
    """Raise ``ValueError`` if *module_path* resolves to a disallowed module."""
    if not module_path or not module_path.strip():
        raise ValueError("module_path must be a non-empty string")
    top_pkg = module_path.split(".")[0]
    if top_pkg.lower() in _DISALLOWED_MODULE_PREFIXES:
        raise ValueError(
            f"Refusing to load {module_path!r}: top-level package "
            f"{top_pkg!r} is disallowed for settings modules"
        )
    if module_path in ("__main__", "builtins", "builtins"):
        raise ValueError(f"Refusing to load {module_path!r}: reserved module name")


def _resolve_app_path(name: str) -> str:
    """Resolve an app *name* to a filesystem directory path.

    Walks entries in ``sys.path`` and the current working directory looking
    for a matching ``<name>/__init__.py`` package marker.  Falls back to the
    CWD so the caller never raises for a missing path.

    Args:
        name: Dotted app name (e.g. ``"users"`` or ``"myproj.apps.users"``).

    Returns:
        Resolved absolute path string.
    """
    candidates: List[str] = []
    # sys.path first (virtualenv / site-packages entries)
    for entry in sys.path:
        pkg_dir = Path(entry) / name.replace(".", os.sep)
        if (pkg_dir / "__init__.py").exists():
            return str(pkg_dir.resolve())
        candidates.append(str(Path(entry) / name))

    # CWD and its explicit sub-path variant
    cwd = Path.cwd()
    direct = cwd / name.replace(".", os.sep)
    if (direct / "__init__.py").exists() or direct.is_dir():
        return str(direct.resolve())
    if (cwd / name).is_dir():
        return str((cwd / name).resolve())

    # Absolute / already-correct path as last resort
    p = Path(name)
    if p.is_dir():
        return str(p.resolve())

    # Final fallback: close to CWD so downstream code can still attempt
    return str((cwd / name.split(".")[-1]).resolve())


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
                if db_alias not in self._pools:
                    db_config = settings.get_database(db_alias)
                    try:
                        adapter = db_config.get_async_adapter()
                    except ValueError as e:
                        raise RuntimeError(
                            f"Async operations not supported for engine "
                            f"{db_config.engine}: {e}"
                        )

                    self._pools[db_alias] = await adapter.create_pool(
                        db_config.get_connection_config(),
                        db_config.get_pool_config(),
                    )
        return self._pools[db_alias]

    async def get_connection(self, db_alias: str = "default") -> PooledAsyncConnection:
        """Borrow a pooled connection with exponential backoff and retry."""
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
                    logger.error(
                        "Async: Failed to acquire connection from pool %s "
                        "after %d retries",
                        db_alias,
                        max_retries,
                    )
                    raise

                wait = retry_delay * (2 ** attempt)
                logger.warning(
                    "Async: Connection pool %s exhausted. "
                    "Retrying in %.2fs (attempt %d/%d)",
                    db_alias,
                    wait,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(wait)
            except Exception:
                cb.record_failure()
                raise

    @contextmanager
    def connection(self, db_alias: str = "default"):
        """
        This is a legacy helper. For async usage, prefer the
        async_connection() context manager.
        """
        raise RuntimeError(
            "Use 'async with connection_manager.async_connection()' " "for async logic."
        )

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
    """Global container for ORM settings (Django-style DATABASES / INSTALLED_APPS)."""

    def __init__(self) -> None:
        self.databases: Dict[str, DatabaseConfig] = {}
        self.default_database: str = "default"
        self.migration_path: str = "migrations"
        self.model_paths: List[str] = []

        # ── Django-style ────────────────────────────────────────────
        self.installed_apps: List["AppConfig"] = []
        self.secret_key: str = ""
        self.debug: bool = False
        self.allowed_hosts: List[str] = []
        self.use_tz: bool = True

        # ── Logging ─────────────────────────────────────────────────
        self.logging: Dict[str, Any] = {}

    def configure_databases(self, databases: Dict[str, Dict[str, Any]]) -> None:
        for alias, config in databases.items():
            self.databases[alias] = DatabaseConfig(config)

    def configure_installed_apps(self, apps: list) -> None:
        """Validate and store INSTALLED_APPS entries.

        Args:
            apps: A list of ``str`` app names or :class:`AppConfig` instances.

        Raises:
            TypeError:       An entry is neither ``str`` nor :class:`AppConfig`.
            ValueError:      An app name fails validation or its path is unsafe.
        """
        validated: List[AppConfig] = []
        for entry in apps:
            if isinstance(entry, str):
                cfg = AppConfig(name=entry)
            elif isinstance(entry, AppConfig):
                cfg = entry
            else:
                raise TypeError(
                    "INSTALLED_APPS entries must be str or AppConfig, "
                    f"got {type(entry)!r}"
                )

            _validate_app_name(cfg.name)
            _validate_app_label(cfg.label)
            if cfg.path:
                cfg.path = str(Path(cfg.path).resolve())
                _validate_app_path(cfg.path, cfg.name)

            validated.append(cfg)

        self.installed_apps = validated

        # Auto-register with the central AppRegistry so that
        # MigrationEngine and other consumers see the same apps.
        try:
            from ..models.register import get_default_registry

            reg = get_default_registry()
            for cfg in validated:
                if cfg.path and not reg.get_app(cfg.label):
                    reg.register_app(cfg.label, cfg.path)
        except Exception as exc:
            logger.warning("Could not auto-register INSTALLED_APPS entries: %s", exc)

    def get_installed_apps(self) -> List[AppConfig]:
        """Return the list of configured installed apps."""
        return list(self.installed_apps)

    def append_app(self, app: "AppConfig") -> None:
        """Register an additional app at runtime."""
        _validate_app_name(app.name)
        _validate_app_label(app.label)
        if app.path:
            app.path = str(Path(app.path).resolve())
            _validate_app_path(app.path, app.name)
        self.installed_apps.append(app)
        try:
            from ..models.register import get_default_registry

            reg = get_default_registry()
            if app.path and not reg.get_app(app.label):
                reg.register_app(app.label, app.path)
        except Exception as exc:
            logger.warning("Could not append app %r to registry: %s", app.label, exc)

    def get_database(self, name: Optional[str] = None) -> DatabaseConfig:
        alias = name or self.default_database
        if alias not in self.databases:
            raise ValueError(
                f"Database alias {alias!r} is not configured. "
                "Call mikiorm.configure(...) first."
            )
        return self.databases[alias]


# ---------------------------------------------------------------------------
# Singleton instances
# ---------------------------------------------------------------------------
settings = Settings()
connection_manager = ConnectionManager()
async_connection_manager = AsyncConnectionManager()


# ---------------------------------------------------------------------------
# Public API: configure(), configure_from_module(), generate_settings_template()
# ---------------------------------------------------------------------------


def configure(
    databases: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    migration_path: Optional[str] = None,
    default_database: Optional[str] = None,
    model_paths: Optional[List[str]] = None,
    installed_apps: Optional[list] = None,
    logging_config: Optional[Dict[str, Any]] = None,
) -> None:
    """One-shot configuration entry point used by application code.

    All parameters are optional keyword-only (except ``databases``) so that
    Django-style modules can call::

        from mikiorm import configure
        configure(DATABASES, installed_apps=INSTALLED_APPS)

    Example::

        configure({
            "default": {"ENGINE": "sqlite", "NAME": "app.db"},
        }, migration_path="db/migrations")
    """
    if databases is not None:
        connection_manager.close_all()
        async_connection_manager._pools.clear()
        settings.databases.clear()
        settings.configure_databases(databases)
    if default_database is not None:
        settings.default_database = default_database
    if migration_path is not None:
        settings.migration_path = migration_path
    if model_paths is not None:
        settings.model_paths = model_paths
    if installed_apps is not None:
        settings.configure_installed_apps(installed_apps)
    if logging_config is not None:
        settings.logging.update(logging_config)


def configure_from_module(module_path: str) -> None:
    """Load settings from a Python module (Django style).

    Reads ``DATABASES``, ``DEFAULT_DATABASE``, ``MIGRATION_PATH``,
    ``MODEL_PATHS``, and ``INSTALLED_APPS`` from the named module and
    passes them to :func:`configure`.

    Security: ``module_path`` must refer to an application-level module;
    stdlib and system packages are explicitly blocked.

    Args:
        module_path: Dotted Python path, e.g. ``"myproject.settings"``.

    Raises:
        ValueError: If the module resolves to a disallowed package.
        ImportError: If the module cannot be found.
    """
    _validate_module_path(module_path)
    mod = importlib.import_module(module_path)
    configure(
        databases=getattr(mod, "DATABASES", None),
        default_database=getattr(mod, "DEFAULT_DATABASE", "default"),
        migration_path=getattr(mod, "MIGRATION_PATH", "migrations"),
        model_paths=getattr(mod, "MODEL_PATHS", None),
        installed_apps=getattr(mod, "INSTALLED_APPS", []),
        logging_config=getattr(mod, "LOGGING", None),
    )


def generate_settings_template(
    project_name: str = "myproject",
    *,
    include_generated_by: bool = True,
) -> str:
    """Return a ready-to-edit ``settings.py`` scaffold string.

    Called by the ``startproject`` CLI command to write the initial
    settings file.  The generated file uses clear, commented sections so
    that users know exactly where to fill in each configuration.

    Args:
        project_name:     Used for the package-header comment only.
        include_generated_by: Prepend a ``# Generated by miki-orm`` header.

    Returns:
        A complete ``settings.py`` file content string.
    """
    header = (
        f'"""Settings for {project_name!s}."""\n\n'
        if project_name
        else '"""Project settings."""\n\n'
    )

    generated_tag = (
        (
            "# Generated by miki-orm startproject. "
            "Edit this file to configure your project.\n\n"
        )
        if include_generated_by
        else ""
    )

    return f'''\
"""
{project_name} settings — configure your miki-orm application here.
"""

from pathlib import Path

from mikiorm import configure

# ─── Filesystem ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent  # project root


# ─── Database (SQLite example) ─────────────────────────────────────────────
# DATABASES = {{
#     "default": {{
#         "ENGINE": "sqlite",
#         "NAME":   BASE_DIR / "db.sqlite3",
#     }},
# }}
# DEFAULT_DATABASE = "default"


# ─── Installed apps ────────────────────────────────────────────────────────
# INSTALLED_APPS: list[str] = [
#     # "users",
#     # "products",
# ]


# ─── Migrations & model discovery ─────────────────────────────────────────
# MIGRATION_PATH = "migrations"
# MODEL_PATHS: list[str] = []


# ─── Runtime ───────────────────────────────────────────────────────────────
# SECRET_KEY  = "change-me"
# DEBUG       = False
# ALLOWED_HOSTS: list[str] = []
# USE_TZ      = True


def configure_project() -> None:
    """Configure the ORM from this settings module.

    Call this once at application startup so that database connections,
    app registration, and model discovery are all wired up.
    """
    configure(
        databases=DATABASES,
        default_database=DEFAULT_DATABASE,
        migration_path=MIGRATION_PATH,
        model_paths=MODEL_PATHS,
        installed_apps=INSTALLED_APPS,
    )
'''


__all__ = [
    "AppConfig",
    "AsyncConnectionManager",
    "ConnectionManager",
    "DatabaseConfig",
    "Settings",
    "async_connection_manager",
    "configure",
    "configure_from_module",
    "connection_manager",
    "generate_settings_template",
    "register_async_adapter",
    "register_sync_adapter",
    "settings",
]

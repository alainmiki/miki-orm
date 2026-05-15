"""High-level database wrapper following Django's per-alias backend pattern.

A :class:`BaseDatabaseWrapper` owns the connection/pool, schema editor, and
metadata for one configured database alias.  Backends extend it with their
adapter and dialect.

This file is intentionally thin: the heavy lifting lives in
``adapter.py`` (interfaces), ``pool.py`` (pooling), and ``dialect.py``
(SQL building).  Importing those here keeps a stable public path
``mikiorm.backends.base``.
"""

from __future__ import annotations

from typing import Any, Dict

from .adapter import (
    BaseAdapter,
    BaseAsyncAdapter,
    BaseAsyncConnection,
    BaseConnection,
    get_param_placeholder,
)
from .dialect import Dialect, SafeBuilder, get_safe_builder
from .pool import (
    AsyncConnectionPool,
    PooledAsyncConnection,
    PooledConnection,
    SyncConnectionPool,
)


class DatabaseSettings:
    """Thin convenience wrapper around a settings dict for a single alias."""

    def __init__(self, settings_dict: Dict[str, Any]) -> None:
        self._settings = settings_dict

    def __getitem__(self, key: str) -> Any:
        return self._settings.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    @property
    def engine(self) -> str:
        return self._settings.get("ENGINE", "sqlite")

    @property
    def name(self) -> str:
        return self._settings.get("NAME", ":memory:")


def get_dialect_from_engine(engine: str) -> Dialect:
    """Map an engine name to its :class:`Dialect` enum value."""
    mapping = {
        "sqlite": Dialect.SQLITE,
        "postgresql": Dialect.POSTGRESQL,
        "postgres": Dialect.POSTGRESQL,
        "mysql": Dialect.MYSQL,
        "oracle": Dialect.ORACLE,
    }
    return mapping.get(engine.lower(), Dialect.SQLITE)


class BaseDatabaseWrapper:
    """Per-alias database wrapper - holds adapter, pool, dialect, and config.

    This is the high-level handle the ORM keeps for each entry in
    ``settings.DATABASES``.  Subclasses set ``vendor``, ``display_name``,
    and point ``adapter_cls`` / ``async_adapter_cls`` at concrete adapter
    classes.
    """

    vendor: str = "unknown"
    display_name: str = "Unknown"
    adapter_cls: type[BaseAdapter] | None = None
    async_adapter_cls: type[BaseAsyncAdapter] | None = None

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.settings_dict = DatabaseSettings(config)

    def get_connection_params(self) -> Dict[str, Any]:
        """Return the connection-arg subset of the settings dict."""
        return {
            "NAME": self.config.get("NAME", ":memory:"),
            "USER": self.config.get("USER"),
            "PASSWORD": self.config.get("PASSWORD"),
            "HOST": self.config.get("HOST", "localhost"),
            "PORT": self.config.get("PORT"),
            **self.config.get("OPTIONS", {}),
        }

    def get_dialect(self) -> Dialect:
        return get_dialect_from_engine(self.settings_dict.engine)


__all__ = [
    # high-level wrapper
    "BaseDatabaseWrapper",
    "DatabaseSettings",
    "get_dialect_from_engine",
    # connection / adapter
    "BaseConnection",
    "BaseAsyncConnection",
    "BaseAdapter",
    "BaseAsyncAdapter",
    "get_param_placeholder",
    # pool
    "SyncConnectionPool",
    "AsyncConnectionPool",
    "PooledConnection",
    "PooledAsyncConnection",
    # dialect
    "Dialect",
    "SafeBuilder",
    "get_safe_builder",
]

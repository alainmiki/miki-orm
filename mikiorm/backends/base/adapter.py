"""Abstract adapter and connection interfaces shared by every backend.

A *connection* wraps a single driver-level handle.  An *adapter* knows how to
spin up new connections (and pools of them) from a config dictionary.

Concrete subclasses live under ``mikiorm.backends.{sqlite,postgresql,mysql,...}``.
"""

from __future__ import annotations
import asyncio

from abc import ABC, abstractmethod
from typing import Any, Iterable

from .pool import (
    AsyncConnectionPool,
    SyncConnectionPool,
)


class BaseConnection(ABC):
    """Abstract base for a single synchronous database connection.

    The ORM only talks to connections through this surface; concrete adapters
    are free to wrap any driver they like as long as the contract holds.
    """

    #: Placeholder style for this dialect (``?`` for SQLite, ``%s`` elsewhere).
    param_placeholder: str = "?"

    #: The SQL query used for minimal liveness checking.
    validation_query: str = "SELECT 1"

    @abstractmethod
    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        """Execute a parameterised SQL statement and return a cursor."""

    @abstractmethod
    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        """Execute and return every row."""

    @abstractmethod
    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
        """Execute and return at most one row, or None."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""

    @abstractmethod
    def rollback(self) -> None:
        """Roll back the current transaction."""

    @abstractmethod
    def close(self) -> None:
        """Close the underlying driver connection."""

    def begin(self) -> None:
        """Begin an explicit transaction (overridden if the driver requires it)."""

    def is_valid(self) -> bool:
        """Cheap liveness probe used by pool validation."""
        try:
            return bool(self.fetchone(self.validation_query, ()))
        except Exception:
            return False


class BaseAdapter(ABC):
    """Abstract synchronous adapter: builds connections and pools from config."""

    @abstractmethod
    def connect(self, config: dict[str, Any]) -> BaseConnection:
        """Create and return a fresh ``BaseConnection``."""

    def create_pool(
        self, config: dict[str, Any], pool_config: dict[str, Any] | None = None
    ) -> SyncConnectionPool:
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=int(pool_config.get("min_size", 1)),
            max_size=int(pool_config.get("max_size", 5)),
            timeout=float(pool_config.get("timeout", 30)),
            max_lifetime=float(pool_config.get("max_lifetime", 0)),
            max_uses=int(pool_config.get("max_uses", 0)),
            pre_ping=bool(pool_config.get("pre_ping", False)),
        )

    def quote_name(self, name: str) -> str:  # pragma: no cover - simple default
        return f'"{name}"'


class BaseAsyncConnection(ABC):
    """Abstract base for an asynchronous single connection."""

    param_placeholder: str = "?"

    #: The SQL query used for minimal liveness checking.
    validation_query: str = "SELECT 1"

    @abstractmethod
    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any: ...

    @abstractmethod
    async def fetchall(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[tuple[Any, ...]]: ...

    @abstractmethod
    async def fetchone(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> tuple[Any, ...] | None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def begin(self) -> None:
        """Begin an explicit transaction (overridden if the driver requires it)."""

    async def is_valid(self, timeout: float = 5.0) -> bool:
        """Cheap async liveness probe with a timeout to prevent hanging."""
        try:
            result = await asyncio.wait_for(
                self.fetchone(self.validation_query, ()),
                timeout=timeout
            )
            return bool(result)
        except Exception:
            return False


class BaseAsyncAdapter(ABC):
    """Abstract asynchronous adapter."""

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> BaseAsyncConnection: ...

    async def create_pool(
        self, config: dict[str, Any], pool_config: dict[str, Any] | None = None
    ) -> AsyncConnectionPool:
        pool_config = pool_config or {}
        pool = AsyncConnectionPool(
            self,
            config,
            min_size=int(pool_config.get("min_size", 1)),
            max_size=int(pool_config.get("max_size", 5)),
            timeout=float(pool_config.get("timeout", 30)),
            max_lifetime=float(pool_config.get("max_lifetime", 0)),
            max_uses=int(pool_config.get("max_uses", 0)),
            pre_ping=bool(pool_config.get("pre_ping", False)),
        )
        await pool.startup()
        return pool


def get_param_placeholder(engine: str) -> str:
    """Return the placeholder string for the given engine."""
    if engine in ("postgresql", "postgres", "mysql"):
        return "%s"
    return "?"


__all__ = [
    "BaseAdapter",
    "BaseAsyncAdapter",
    "BaseConnection",
    "BaseAsyncConnection",
    "get_param_placeholder",
]

"""Abstract connection interfaces and adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Tuple

def get_param_placeholder() -> str:
    """Return the appropriate SQL parameter placeholder for the configured database."""
    from .. import settings

    db_config = settings.get_database("default")
    if db_config.engine == "postgresql" or db_config.engine == "mysql":
        return "%s"
    return "?"


# ---------------------------------------------------------------------------
# Synchronous interfaces
# ---------------------------------------------------------------------------

class BaseConnection(ABC):
    """Base interface for a database connection."""

    @property
    @abstractmethod
    def param_placeholder(self) -> str:
        """Return the parameter placeholder style for this database backend."""

    @abstractmethod
    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        raise NotImplementedError

    @abstractmethod
    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError


class BaseAdapter(ABC):
    """Abstract adapter for connection factories and pools."""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> BaseConnection:
        pass

    @abstractmethod
    def create_pool(self, config: Dict[str, Any]) -> Any:
        pass


# ---------------------------------------------------------------------------
# Asynchronous interfaces
# ---------------------------------------------------------------------------

class BaseAsyncConnection(ABC):
    """Base interface for an async database connection."""

    @property
    @abstractmethod
    def param_placeholder(self) -> str:
        """Return the parameter placeholder style for this database backend."""

    @abstractmethod
    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        raise NotImplementedError

    @abstractmethod
    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


class BaseAsyncAdapter(ABC):
    """Abstract async adapter for connection factories and pools."""

    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> BaseAsyncConnection:
        pass

    @abstractmethod
    async def create_pool(self, config: Dict[str, Any]) -> BaseAsyncConnection:
        pass


    @abstractmethod
    def create_pool(self, config: Dict[str, Any]) -> Any:
        pass

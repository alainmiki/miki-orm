"""Abstract connection interfaces and adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Tuple
# from settings import configure

def get_param_placeholder() -> str:
    """Return the appropriate SQL parameter placeholder for the configured database."""
    from .. import settings

    db_config = settings.get_database("default")
    if db_config.engine == "postgresql" or db_config.engine == "mysql":
        return "%s"
    return "?"


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
    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        raise NotImplementedError

    @abstractmethod
    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
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

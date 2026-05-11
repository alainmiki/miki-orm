"""Abstract connection interfaces and adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Tuple


class BaseConnection(ABC):
    """Base interface for a database connection."""

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
        raise NotImplementedError

    @abstractmethod
    def create_pool(self, config: Dict[str, Any]) -> Any:
        raise NotImplementedError

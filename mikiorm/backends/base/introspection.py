"""Base classes for database introspection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mikiorm.backends.base.adapter import BaseConnection


class BaseIntrospection(ABC):
    """Base class for database introspection."""

    def __init__(self, connection: BaseConnection):
        self.connection = connection

    @abstractmethod
    def get_tables(self) -> list[str]:
        """Returns a list of table names in the database."""
        raise NotImplementedError

    @abstractmethod
    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        """Returns a list of column dictionaries for the given table."""
        raise NotImplementedError

    @abstractmethod
    def get_indexes(self, table_name: str) -> list[dict[str, Any]]:
        """Returns a list of index dictionaries for the given table."""
        raise NotImplementedError
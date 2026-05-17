"""SQL builder with safe identifier quoting and placeholder normalization."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SafeBuilder(ABC):
    """Abstract base class for safe SQL builders."""

    @abstractmethod
    def quote_name(self, name: str) -> str:
        """Quotes a database identifier (e.g., column or index name)."""
        raise NotImplementedError

    @abstractmethod
    def quote_table(self, name: str) -> str:
        """Quotes a table name."""
        raise NotImplementedError

    @abstractmethod
    def get_placeholder(self, index: int | None = None) -> str:
        """Returns the appropriate parameter placeholder for the dialect."""
        raise NotImplementedError

    def quote_column(self, name: str) -> str:
        """Quotes a column name."""
        return self.quote_name(name)

    def quote_identifier(self, name: str) -> str:
        """Quotes a generic identifier."""
        return self.quote_name(name)


class SQLiteBuilder(SafeBuilder):
    """SQLite-specific SQL builder."""
    dialect = "sqlite"

    def quote_name(self, name: str) -> str:
        return f'"{name}"'

    def quote_table(self, name: str) -> str:
        return f'"{name}"'

    @property
    def param_placeholder(self) -> str:
        return "?"

    def get_placeholder(self, index: int | None = None) -> str:
        return "?"


class PostgresBuilder(SafeBuilder):
    """PostgreSQL-specific SQL builder."""
    dialect = "postgresql"

    def quote_name(self, name: str) -> str:
        return f'"{name}"'

    def quote_table(self, name: str) -> str:
        return f'"{name}"'

    @property
    def param_placeholder(self) -> str:
        return "%s"

    def get_placeholder(self, index: int | None = None) -> str:
        return f"${index}" if index is not None else "$1"


class MySQLBuilder(SafeBuilder):
    """MySQL-specific SQL builder."""
    dialect = "mysql"

    def quote_name(self, name: str) -> str:
        return f"`{name}`"

    def quote_table(self, name: str) -> str:
        return f"`{name}`"

    @property
    def param_placeholder(self) -> str:
        return "%s"

    def get_placeholder(self, index: int | None = None) -> str:
        return "%s"


class OracleBuilder(SafeBuilder):
    """Oracle-specific SQL builder."""
    dialect = "oracle"

    def quote_name(self, name: str) -> str:
        return f'"{name.upper()}"'

    def quote_table(self, name: str) -> str:
        return f'"{name.upper()}"'

    @property
    def param_placeholder(self) -> str:
        return ":1"

    def get_placeholder(self, index: int | None = None) -> str:
        return f":{index}" if index is not None else ":1"


def get_safe_builder(engine: str) -> SafeBuilder:
    """Returns a SafeBuilder instance for the given engine."""
    if engine == "sqlite":
        return SQLiteBuilder()
    elif engine in ("postgresql", "postgres"):
        return PostgresBuilder()
    elif engine == "mysql":
        return MySQLBuilder()
    elif engine == "oracle":
        return OracleBuilder()
    raise ValueError(f"Unsupported database engine: {engine}")
"""Safe SQL builder with identifier quoting and dialect support."""

from __future__ import annotations

from typing import Any
from enum import Enum


class Dialect(Enum):
    """Supported SQL dialects."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


class SafeBuilder:
    """Safe SQL builder that quotes identifiers and uses parameterized queries only."""

    def __init__(self, dialect: Dialect = Dialect.SQLITE) -> None:
        self.dialect = dialect

    @property
    def param_placeholder(self) -> str:
        """Return the parameter placeholder for the current dialect."""
        if self.dialect == Dialect.POSTGRESQL:
            return "%s"
        elif self.dialect == Dialect.MYSQL:
            return "%s"
        return "?"

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier (table, column, etc.) for the current dialect."""
        if self.dialect == Dialect.POSTGRESQL:
            return f'"{name}"'
        elif self.dialect == Dialect.MYSQL:
            return f"`{name}`"
        return f"`{name}`"  # SQLite uses backticks

    def quote_table(self, table: str) -> str:
        """Quote a table name."""
        return self.quote_identifier(table)

    def quote_column(self, column: str) -> str:
        """Quote a column name."""
        return self.quote_identifier(column)

    def parse_lookup(self, key: str) -> tuple[str, str]:
        """Parse a Django-style lookup like 'field__gt' into (field, operator).
        
        Returns:
            (field_name, operator_type) where operator_type is one of:
            'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'contains',
            'icontains', 'startswith', 'endswith', 'isnull'
        """
        if "__" not in key:
            return key, "eq"

        parts = key.split("__")
        field_name = "__".join(parts[:-1])  # Handle nested lookups
        lookup_type = parts[-1]

        lookup_map = {
            "gt": "gt",
            "gte": "gte",
            "lt": "lt",
            "lte": "lte",
            "exact": "eq",
            "iexact": "iexact",
            "contains": "contains",
            "icontains": "icontains",
            "startswith": "startswith",
            "istartswith": "istartswith",
            "endswith": "endswith",
            "iendswith": "iendswith",
            "in": "in",
            "isnull": "isnull",
            "range": "range",
        }

        operator = lookup_map.get(lookup_type, "eq")
        return field_name, operator

    def build_condition(self, field: str, operator: str, value: Any) -> tuple[str, list[Any]]:
        """Build a safe WHERE condition clause.
        
        Returns:
            (sql_fragment, params) where sql_fragment is a partial WHERE clause
            and params is a list of values to be parameterized.
        """
        quoted_field = self.quote_column(field)
        ph = self.param_placeholder

        if operator == "eq":
            if value is None:
                return f"{quoted_field} IS NULL", []
            return f"{quoted_field} = {ph}", [value]

        elif operator == "ne":
            if value is None:
                return f"{quoted_field} IS NOT NULL", []
            return f"{quoted_field} != {ph}", [value]

        elif operator == "gt":
            return f"{quoted_field} > {ph}", [value]

        elif operator == "gte":
            return f"{quoted_field} >= {ph}", [value]

        elif operator == "lt":
            return f"{quoted_field} < {ph}", [value]

        elif operator == "lte":
            return f"{quoted_field} <= {ph}", [value]

        elif operator == "in":
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"'in' lookup requires a list/tuple, got {type(value)}")
            if not value:
                return "FALSE", []  # Empty IN returns no results
            placeholders = ", ".join([ph] * len(value))
            return f"{quoted_field} IN ({placeholders})", list(value)

        elif operator == "contains":
            return f"{quoted_field} LIKE {ph}", [f"%{value}%"]

        elif operator == "icontains":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"%{value}%"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"%{value}%"]

        elif operator == "startswith":
            return f"{quoted_field} LIKE {ph}", [f"{value}%"]

        elif operator == "istartswith":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"{value}%"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"{value}%"]

        elif operator == "endswith":
            return f"{quoted_field} LIKE {ph}", [f"%{value}"]

        elif operator == "iendswith":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"%{value}"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"%{value}"]

        elif operator == "isnull":
            if value:
                return f"{quoted_field} IS NULL", []
            return f"{quoted_field} IS NOT NULL", []

        elif operator == "range":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"'range' lookup requires a 2-tuple, got {value}")
            return f"{quoted_field} BETWEEN {ph} AND {ph}", list(value)

        else:
            # Fallback to equality
            return f"{quoted_field} = {ph}", [value]

    def build_order_by(self, fields: list[str]) -> str:
        """Build an ORDER BY clause from field names. Handles '-' prefix for DESC."""
        order_parts = []
        for field in fields:
            if field.startswith("-"):
                order_parts.append(f"{self.quote_column(field[1:])} DESC")
            else:
                order_parts.append(f"{self.quote_column(field)} ASC")
        return "ORDER BY " + ", ".join(order_parts) if order_parts else ""


def get_safe_builder(engine: str) -> SafeBuilder:
    """Get a SafeBuilder for the given database engine."""
    if engine == "postgresql":
        return SafeBuilder(Dialect.POSTGRESQL)
    elif engine == "mysql":
        return SafeBuilder(Dialect.MYSQL)
    return SafeBuilder(Dialect.SQLITE)

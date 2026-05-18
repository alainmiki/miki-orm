"""Dialect-aware safe SQL building.

Every SQL fragment the ORM emits passes through here.  The builder:

* Quotes identifiers per dialect (``"col"`` for ANSI/Postgres/SQLite,
  `` `col` `` for MySQL).
* Picks the right placeholder for parameters (``?`` for SQLite,
  ``%s`` for psycopg2/pymysql; ``asyncpg`` rewrites to ``$n`` itself).
* Translates Django-style lookups (``field__icontains``) into safe WHERE
  fragments while keeping values fully parameterised.

User data is **never** concatenated into the SQL string.  Only quoted
identifiers (already restricted by Python attribute syntax in model
definitions) are inlined.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


# Identifiers must be word characters only.  This guards against header
# injection should a malicious caller pass a crafted field name in a lookup.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Dialect(Enum):
    """SQL dialect identifiers."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    ORACLE = "oracle"


_PLACEHOLDERS = {
    Dialect.SQLITE: "?",
    Dialect.POSTGRESQL: "%s",
    Dialect.MYSQL: "%s",
    Dialect.ORACLE: ":1",  # caller renumbers
}


_LOOKUPS = {
    "exact": "eq",
    "iexact": "iexact",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "in": "in",
    "contains": "contains",
    "icontains": "icontains",
    "startswith": "startswith",
    "istartswith": "istartswith",
    "endswith": "endswith",
    "iendswith": "iendswith",
    "isnull": "isnull",
    "range": "range",
    # Regex lookups
    "regex": "regex",
    "iregex": "iregex",
    # Date/Time lookups
    "year": "year",
    "month": "month",
    "day": "day",
    "week": "week",
    "quarter": "quarter",
    "hour": "hour",
    "minute": "minute",
    "second": "second",
    "date": "date",
}


def _validate_identifier(name: str) -> str:
    """Ensure *name* is a safe SQL identifier."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


class SafeBuilder:
    """Dialect-aware SQL builder with parameterised query generation."""

    def __init__(self, dialect: Dialect = Dialect.SQLITE) -> None:
        self.dialect = dialect

    # ------------------------------------------------------------------
    # Placeholders and identifiers
    # ------------------------------------------------------------------
    @property
    def param_placeholder(self) -> str:
        return _PLACEHOLDERS.get(self.dialect, "?")

    def quote_identifier(self, name: str) -> str:
        _validate_identifier(name)
        if self.dialect == Dialect.MYSQL:
            return f"`{name}`"
        return f'"{name}"'

    def quote_table(self, table: str) -> str:
        return self.quote_identifier(table)

    def quote_column(self, column: str) -> str:
        return self.quote_identifier(column)

    # ------------------------------------------------------------------
    # Lookup translation
    # ------------------------------------------------------------------
    def parse_lookup(self, key: str) -> tuple[str, str]:
        """Split ``field__op`` into ``(field, op)``.

        Returns ``(field, 'eq')`` if no double-underscore suffix is present.
        """
        if "__" not in key:
            return key, "eq"
        parts = key.split("__")
        last = parts[-1]
        if last in _LOOKUPS:
            field = "__".join(parts[:-1])
            return field, _LOOKUPS[last]
        return key, "eq"

    def build_condition(
        self, field: str, operator: str, value: Any
    ) -> tuple[str, list[Any]]:
        """Build a safe WHERE-fragment and the matching parameter list."""
        quoted_field = self.quote_column(field)
        ph = self.param_placeholder

        if operator == "eq":
            if value is None:
                return f"{quoted_field} IS NULL", []
            return f"{quoted_field} = {ph}", [value]
        if operator == "ne":
            if value is None:
                return f"{quoted_field} IS NOT NULL", []
            return f"{quoted_field} != {ph}", [value]
        if operator == "iexact":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [value]
            return f"LOWER({quoted_field}) = LOWER({ph})", [value]
        if operator == "gt":
            return f"{quoted_field} > {ph}", [value]
        if operator == "gte":
            return f"{quoted_field} >= {ph}", [value]
        if operator == "lt":
            return f"{quoted_field} < {ph}", [value]
        if operator == "lte":
            return f"{quoted_field} <= {ph}", [value]
        if operator == "in":
            if not isinstance(value, (list, tuple, set)):
                raise ValueError(
                    f"'in' lookup requires list/tuple/set, got {type(value).__name__}"
                )
            values = list(value)
            if not values:
                return "1 = 0", []  # always-false, no rows
            placeholders = ", ".join([ph] * len(values))
            return f"{quoted_field} IN ({placeholders})", values
        if operator == "contains":
            return f"{quoted_field} LIKE {ph}", [f"%{value}%"]
        if operator == "icontains":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"%{value}%"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"%{value}%"]
        if operator == "startswith":
            return f"{quoted_field} LIKE {ph}", [f"{value}%"]
        if operator == "istartswith":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"{value}%"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"{value}%"]
        if operator == "endswith":
            return f"{quoted_field} LIKE {ph}", [f"%{value}"]
        if operator == "iendswith":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ILIKE {ph}", [f"%{value}"]
            return f"LOWER({quoted_field}) LIKE LOWER({ph})", [f"%{value}"]
        if operator == "isnull":
            return (
                f"{quoted_field} IS NULL" if value else f"{quoted_field} IS NOT NULL"
            ), []
        if operator == "range":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"'range' lookup requires a 2-tuple, got {value!r}")
            return f"{quoted_field} BETWEEN {ph} AND {ph}", list(value)
        if operator == "regex":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ~ {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"{quoted_field} REGEXP {ph}", [value]
            else:
                # SQLite doesn't have native regex, fall back to LIKE
                raise NotImplementedError("REGEX lookups not supported on SQLite. Use contains/startswith instead.")
        if operator == "iregex":
            if self.dialect == Dialect.POSTGRESQL:
                return f"{quoted_field} ~* {ph}", [value]  # case-insensitive
            elif self.dialect == Dialect.MYSQL:
                return f"{quoted_field} REGEXP {ph}", [value]  # MySQL is case-insensitive by default
            else:
                raise NotImplementedError("IREGEX lookups not supported on SQLite.")
        # Date/time lookups
        if operator == "year":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(YEAR FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"YEAR({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%Y', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "month":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(MONTH FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"MONTH({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%m', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "day":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(DAY FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"DAY({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%d', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "week":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(WEEK FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"WEEK({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%W', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "quarter":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(QUARTER FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"QUARTER({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(((CAST(STRFTIME('%m', {quoted_field}) AS INTEGER) - 1) / 3) + 1 AS INTEGER) = {ph}", [value]
        if operator == "hour":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(HOUR FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"HOUR({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%H', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "minute":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(MINUTE FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"MINUTE({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%M', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "second":
            if self.dialect == Dialect.POSTGRESQL:
                return f"EXTRACT(SECOND FROM {quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"SECOND({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"CAST(STRFTIME('%S', {quoted_field}) AS INTEGER) = {ph}", [value]
        if operator == "date":
            if self.dialect == Dialect.POSTGRESQL:
                return f"DATE({quoted_field}) = {ph}", [value]
            elif self.dialect == Dialect.MYSQL:
                return f"DATE({quoted_field}) = {ph}", [value]
            else:  # SQLite
                return f"DATE({quoted_field}) = {ph}", [value]

        # Unknown operator falls back to equality so that callers get a
        # predictable result instead of a runtime crash.
        return f"{quoted_field} = {ph}", [value]

    def build_order_by(self, fields: list[str]) -> str:
        """Compile ``ORDER BY`` from a list of field names; ``-`` prefix = DESC."""
        if not fields:
            return ""
        parts: list[str] = []
        for field in fields:
            if not field:
                continue
            if field.startswith("-"):
                parts.append(f"{self.quote_column(field[1:])} DESC")
            else:
                parts.append(f"{self.quote_column(field)} ASC")
        return "ORDER BY " + ", ".join(parts) if parts else ""


def get_safe_builder(engine: str) -> SafeBuilder:
    """Return a ``SafeBuilder`` for the given engine name."""
    if engine == "postgresql":
        return SafeBuilder(Dialect.POSTGRESQL)
    if engine == "mysql":
        return SafeBuilder(Dialect.MYSQL)
    if engine == "oracle":
        return SafeBuilder(Dialect.ORACLE)
    return SafeBuilder(Dialect.SQLITE)


__all__ = ["Dialect", "SafeBuilder", "get_safe_builder"]

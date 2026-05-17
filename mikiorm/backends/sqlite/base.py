"""SQLite backend base classes following Django's backend pattern."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, Tuple

from ..base.base import BaseConnection


class SQLiteConnection(BaseConnection):
    """SQLite connection wrapper with secure parameterized queries."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cursor: sqlite3.Cursor | None = None

    @property
    def param_placeholder(self) -> str:
        return "?"

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        """Execute SQL with parameterized query - never string interpolation."""
        self._cursor = self._conn.execute(sql, params or ())
        return self._cursor

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
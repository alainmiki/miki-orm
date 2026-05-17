"""SQLite backend base classes following Django's backend pattern."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, Tuple

from ..base.adapter import BaseAdapter
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


class SQLiteAdapter(BaseAdapter):
    """SQLite adapter for creating connections and pools."""

    def connect(self, config: Dict[str, Any]) -> SQLiteConnection:
        """Establish a new SQLite connection based on configuration."""
        database = config.get("NAME", ":memory:")
        timeout = config.get("timeout", 30.0)
        detect_types = config.get("detect_types", sqlite3.PARSE_DECLTYPES)

        conn = sqlite3.connect(
            database,
            timeout=timeout,
            detect_types=detect_types,
            check_same_thread=False,
        )

        # Enable foreign keys for data integrity
        conn.execute("PRAGMA foreign_keys = ON")

        return SQLiteConnection(conn)

    def get_database_version(self, connection: SQLiteConnection) -> str:
        """Return SQLite version string."""
        cursor = connection.execute("SELECT sqlite_version()", ())
        version = cursor.fetchone()
        return version[0] if version else "unknown"

    def get_client_encoding(self, connection: SQLiteConnection) -> str:
        """SQLite always uses UTF-8."""
        return "UTF-8"
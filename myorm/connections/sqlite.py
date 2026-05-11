"""SQLite sync adapter implementation."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict

from .base import BaseAdapter, BaseConnection


class SQLiteConnection(BaseConnection):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params=None):
        return self._conn.execute(sql, params or ())

    def fetchall(self, sql: str, params=None):
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchall()

    def fetchone(self, sql: str, params=None):
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()


class SQLiteAdapter(BaseAdapter):
    def connect(self, config: Dict[str, Any]) -> SQLiteConnection:
        database = config.get("NAME", ":memory:")
        conn = sqlite3.connect(database, check_same_thread=False)
        return SQLiteConnection(conn)

    def create_pool(self, config: Dict[str, Any]) -> SQLiteConnection:
        # SQLite uses a lightweight connection wrapper for MVP.
        return self.connect(config)

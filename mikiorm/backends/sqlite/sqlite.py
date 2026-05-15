"""SQLite sync adapter implementation."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict

from .base import BaseAdapter, BaseConnection, SyncConnectionPool


class SQLiteConnection(BaseConnection):
    @property
    def param_placeholder(self) -> str:
        return "?"

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

    def close(self) -> None:
        self._conn.close()


class SQLiteAdapter(BaseAdapter):
    def connect(self, config: Dict[str, Any]) -> SQLiteConnection:
        database = config.get("NAME", ":memory:")
        conn = sqlite3.connect(database, check_same_thread=False)
        return SQLiteConnection(conn)

    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> SyncConnectionPool:
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )

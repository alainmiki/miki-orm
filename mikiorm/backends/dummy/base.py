"""Dummy database backend for testing - uses SQLite in-memory database."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Tuple, Optional

from ...connections.base import BaseAdapter, BaseConnection, SyncAdapter


class DummyConnection(BaseConnection):
    """SQLite in-memory connection for dummy backend."""

    @property
    def param_placeholder(self) -> str:
        return "?"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return self._conn.execute(sql, params or ())

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Tuple[Any, ...]]:
        cursor = self._conn.execute(sql, params or ())
        return cursor.fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class DummyAdapter(BaseAdapter):
    """Dummy adapter for testing - uses SQLite in-memory database."""

    def connect(self, config: Dict[str, Any]) -> DummyConnection:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        return DummyConnection(conn)

    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> SyncAdapter:
        from ...connections.base import SyncConnectionPool
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )


__all__ = ["DummyConnection", "DummyAdapter"]
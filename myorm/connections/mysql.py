"""MySQL sync adapter implementation."""

from __future__ import annotations

from typing import Any, Dict

import pymysql

from .base import BaseAdapter, BaseConnection


class MySQLConnection(BaseConnection):
    def __init__(self, conn: pymysql.connections.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params=None):
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def fetchall(self, sql: str, params=None):
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def fetchone(self, sql: str, params=None):
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()


class MySQLAdapter(BaseAdapter):
    def connect(self, config: Dict[str, Any]) -> MySQLConnection:
        conn = pymysql.connect(
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 3306)),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            db=config.get("NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        return MySQLConnection(conn)

    def create_pool(self, config: Dict[str, Any]) -> Any:
        return self.connect(config)

"""PostgreSQL sync adapter implementation."""

from __future__ import annotations

from typing import Any, Dict

import psycopg2

from .base import BaseAdapter, BaseConnection


class PostgresConnection(BaseConnection):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
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


class PostgresAdapter(BaseAdapter):
    def connect(self, config: Dict[str, Any]) -> PostgresConnection:
        conn = psycopg2.connect(
            dbname=config.get("NAME"),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            host=config.get("HOST", "localhost"),
            port=config.get("PORT", 5432),
            sslmode=config.get("OPTIONS", {}).get("sslmode", "prefer"),
        )
        return PostgresConnection(conn)

    def create_pool(self, config: Dict[str, Any]) -> Any:
        return self.connect(config)

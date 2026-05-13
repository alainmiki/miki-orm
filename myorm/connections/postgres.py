"""PostgreSQL sync adapter implementation."""

from __future__ import annotations

import ssl
from typing import Any, Dict

import psycopg2

from .base import BaseAdapter, BaseConnection, SyncConnectionPool


class PostgresConnection(BaseConnection):
    @property
    def param_placeholder(self) -> str:
        return "%s"

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

    def close(self) -> None:
        self._conn.close()


class PostgresAdapter(BaseAdapter):
    def _build_ssl_context(self, ssl_config: Any) -> Any:
        if not ssl_config:
            return None
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    def connect(self, config: Dict[str, Any]) -> PostgresConnection:
        ssl_config = config.get("SSL", {})
        conn = psycopg2.connect(
            dbname=config.get("NAME"),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            host=config.get("HOST", "localhost"),
            port=config.get("PORT", 5432),
            sslmode=config.get("OPTIONS", {}).get("sslmode", "prefer"),
            sslrootcert=ssl_config.get("CAFILE"),
            sslcert=ssl_config.get("CERTFILE"),
            sslkey=ssl_config.get("KEYFILE"),
        )
        return PostgresConnection(conn)

    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> SyncConnectionPool:
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 5),
            timeout=pool_config.get("timeout", 30),
        )

"""MySQL backend base classes following Django's backend pattern."""

from __future__ import annotations

import ssl
from typing import Any, Dict, Iterable, List, Tuple, Optional

import pymysql
from pymysql.cursors import DictCursor

from mikiorm.backends.base import BaseAdapter, BaseConnection, SyncConnectionPool


class MySQLConnection(BaseConnection):
    """MySQL connection wrapper with secure parameterized queries."""

    @property
    def param_placeholder(self) -> str:
        return "%s"

    def __init__(self, conn: pymysql.connections.Connection) -> None:
        self._conn = conn
        self._cursor: Optional[pymysql.cursors.Cursor] = None

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        """Execute SQL with parameterized query - never string interpolation."""
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        self._cursor = cursor
        return cursor

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor=DictCursor)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
        return [tuple(row.values()) for row in rows]

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor=DictCursor)
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
        cursor.close()
        return tuple(row.values()) if row else None

    def fetchmany(self, sql: str, params: Iterable[Any] | None = None, size: int = 100) -> List[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor=DictCursor)
        cursor.execute(sql, params or ())
        rows = cursor.fetchmany(size)
        cursor.close()
        return [tuple(row.values()) for row in rows]

    def executemany(self, sql: str, params_list: List[Tuple]) -> None:
        """Execute multiple rows efficiently."""
        cursor = self._conn.cursor()
        cursor.executemany(sql, params_list)
        cursor.close()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        if self._cursor is not None:
            self._cursor.close()
        self._conn.close()


class MySQLAdapter(BaseAdapter):
    """MySQL adapter for creating connections and pools."""

    def _build_ssl_context(self, ssl_config: Any) -> Any:
        """Build SSL context from configuration."""
        if not ssl_config:
            return None
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    def connect(self, config: Dict[str, Any]) -> MySQLConnection:
        ssl_context = self._build_ssl_context(config.get("SSL", {}))
        
        conn = pymysql.connect(
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 3306)),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            db=config.get("NAME"),
            charset="utf8mb4",
            cursorclass=DictCursor,
            ssl=ssl_context,
            autocommit=False,
            connect_timeout=config.get("OPTIONS", {}).get("connect_timeout", 10),
            read_timeout=config.get("OPTIONS", {}).get("read_timeout", 30),
            write_timeout=config.get("OPTIONS", {}).get("write_timeout", 30),
        )
        
        # Set SQL mode for strict data integrity
        with conn.cursor() as cursor:
            cursor.execute("SET sql_mode = 'STRICT_TRANS_TABLES'")
        
        return MySQLConnection(conn)

    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> SyncConnectionPool:
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 20),
            timeout=pool_config.get("timeout", 30),
        )

    def get_database_version(self, connection: MySQLConnection) -> Tuple[int, int, int]:
        """Return MySQL version as tuple."""
        cursor = connection.execute("SELECT VERSION()")
        version_str = cursor.fetchone()[0]
        # Parse version string like "8.0.33"
        parts = version_str.split("-")[0].split(".")
        return tuple(int(p) for p in parts[:3])

    def get_client_encoding(self, connection: MySQLConnection) -> str:
        cursor = connection.execute("SHOW VARIABLES LIKE 'character_set_connection'")
        row = cursor.fetchone()
        return row[1] if row else "utf8mb4"

    def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'`{name}`'
"""PostgreSQL backend base classes following Django's backend pattern."""

from __future__ import annotations

import psycopg2
import psycopg2.extras
from typing import Any, Dict, Iterable, List, Tuple, Optional

from mikiorm.backends.base import BaseAdapter, BaseConnection, SyncConnectionPool


class PostgresConnection(BaseConnection):
    """PostgreSQL connection wrapper with secure parameterized queries."""

    @property
    def param_placeholder(self) -> str:
        return "%s"

    def __init__(self, conn: psycopg2.extensions.connection, builder: Any = None) -> None:
        self._conn = conn
        self._cursor: Optional[psycopg2.extensions.cursor] = None
        self._builder = builder

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        """Execute SQL with parameterized query - never string interpolation."""
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        self._cursor = cursor
        return cursor

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
        return [tuple(row) for row in rows]

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
        cursor.close()
        return tuple(row) if row else None

    def fetchmany(self, sql: str, params: Iterable[Any] | None = None, size: int = 100) -> List[Tuple[Any, ...]]:
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql, params or ())
        rows = cursor.fetchmany(size)
        cursor.close()
        return [tuple(row) for row in rows]

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        if self._cursor is not None:
            self._cursor.close()
        self._conn.close()

    def execute_values(self, sql: str, data: List[Tuple]) -> None:
        """Execute multiple rows efficiently using execute_values."""
        from psycopg2.extras import execute_values as pg_execute_values
        with self._conn.cursor() as cursor:
            pg_execute_values(cursor, sql, data, template=None, page_size=100)

    def execute_batch(self, sql: str, data: List[Tuple]) -> None:
        """Execute multiple rows efficiently using execute_batch."""
        from psycopg2.extras import execute_batch as pg_execute_batch
        with self._conn.cursor() as cursor:
            pg_execute_batch(cursor, sql, data, page_size=100)


class PostgresAdapter(BaseAdapter):
    """PostgreSQL adapter for creating connections and pools."""

    def _build_ssl_context(self, ssl_config: Any) -> Any:
        """Build SSL context from configuration."""
        if not ssl_config:
            return None
        import ssl
        if isinstance(ssl_config, bool):
            return ssl.create_default_context()
        context = ssl.create_default_context(cafile=ssl_config.get("CAFILE"))
        if ssl_config.get("CERTFILE") and ssl_config.get("KEYFILE"):
            context.load_cert_chain(ssl_config.get("CERTFILE"), ssl_config.get("KEYFILE"))
        return context

    def connect(self, config: Dict[str, Any]) -> PostgresConnection:
        ssl_context = self._build_ssl_context(config.get("SSL", {}))
        
        conn = psycopg2.connect(
            dbname=config.get("NAME"),
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            host=config.get("HOST", "localhost"),
            port=int(config.get("PORT", 5432)),
            sslmode=config.get("OPTIONS", {}).get("sslmode", "prefer"),
            sslrootcert=config.get("OPTIONS", {}).get("sslrootcert"),
            sslcert=config.get("OPTIONS", {}).get("sslcert"),
            sslkey=config.get("OPTIONS", {}).get("sslkey"),
            ssl=ssl_context,
            cursor_factory=psycopg2.extras.DictCursor,
            # Connection pooling settings
            connect_timeout=config.get("OPTIONS", {}).get("connect_timeout", 10),
        )
        
        # Set timezone to UTC
        with conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
        
        return PostgresConnection(conn)

    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> SyncConnectionPool:
        pool_config = pool_config or {}
        return SyncConnectionPool(
            self,
            config,
            min_size=pool_config.get("min_size", 1),
            max_size=pool_config.get("max_size", 20),
            timeout=pool_config.get("timeout", 30),
        )

    def get_database_version(self, connection: PostgresConnection) -> Tuple[int, ...]:
        """Return PostgreSQL version as tuple."""
        cursor = connection.execute("SHOW server_version")
        version_str = cursor.fetchone()[0]
        parts = version_str.split(".")
        return tuple(int(p.split("-")[0]) for p in parts[:2])

    def get_client_encoding(self, connection: PostgresConnection) -> str:
        """Return client encoding."""
        cursor = connection.execute("SHOW client_encoding")
        return cursor.fetchone()[0] or "UTF8"

    def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'"{name}"'
"""Oracle backend base connection."""

from __future__ import annotations
from typing import Any, Iterable, Dict
from ..base.adapter import BaseConnection, BaseAdapter


class OracleAdapter(BaseAdapter):
    """Oracle synchronous adapter: builds connections from config."""

    def connect(self, config: Dict[str, Any]) -> OracleConnection:
        """Create and return a fresh ``OracleConnection``."""
        # Using python-oracledb (the modern successor to cx_Oracle)
        try:
            import oracledb
        except ImportError:
            raise ImportError(
                "The 'oracledb' library is required to use the Oracle backend. "
                "Install it with 'pip install oracledb'."
            )

        host = config.get("HOST", "localhost")
        port = config.get("PORT", 1521)
        name = config.get("NAME")
        dsn = f"{host}:{port}/{name}"

        conn = oracledb.connect(
            user=config.get("USER"),
            password=config.get("PASSWORD"),
            dsn=dsn,
            **config.get("OPTIONS", {}),
        )
        return OracleConnection(conn)

class OracleConnection(BaseConnection):
    """Oracle connection wrapper with secure parameterized queries."""
    
    #: Oracle requires FROM DUAL for simple constant selects
    validation_query: str = "SELECT 1 FROM DUAL"
    
    #: Oracle uses :1, :2 etc for positional parameters
    param_placeholder: str = ":1"

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        """Execute SQL with parameterized query."""
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor.fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor.fetchone()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
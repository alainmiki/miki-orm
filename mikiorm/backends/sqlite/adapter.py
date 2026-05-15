"""SQLite database adapter implementation."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict

from ..base.base import BaseAdapter
from .base import SQLiteConnection


class Adapter(BaseAdapter):
    """SQLite adapter for creating connections."""

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
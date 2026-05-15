"""SQLite database client and utilities."""

from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Any, Dict, List, Optional


class DatabaseClient:
    """Encapsulates database client operations for SQLite."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", ":memory:")

    def runshell(self) -> None:
        """Run the SQLite command-line shell."""
        import subprocess
        
        db_path = self.database if self.database != ":memory:" else "mikiorm.db"
        
        # Use sqlite3 command if available
        if shutil.which("sqlite3"):
            subprocess.run(["sqlite3", db_path], check=False)
        else:
            raise RuntimeError("sqlite3 command not found. Install SQLite CLI.")

    def create_database(self) -> None:
        """Create a new database if it doesn't exist."""
        if self.database != ":memory:":
            # SQLite creates the file automatically on connect
            conn = sqlite3.connect(self.database)
            conn.close()

    def destroy_database(self) -> None:
        """Destroy the database file."""
        if self.database != ":memory:" and os.path.exists(self.database):
            os.remove(self.database)

    def get_database_filename(self) -> str:
        """Return the database filename."""
        return self.database if self.database != ":memory:" else ":memory:"


def get_client(config: Dict[str, Any]) -> DatabaseClient:
    """Return a DatabaseClient instance for the given config."""
    return DatabaseClient(config)
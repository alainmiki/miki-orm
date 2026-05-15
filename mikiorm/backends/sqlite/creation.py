"""SQLite test database creation utilities."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional


class DatabaseCreation:
    """Handles test database creation for SQLite."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", ":memory:")

    def _get_test_database_name(self) -> str:
        """Generate a unique test database name."""
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        return path

    def create_test_db(self, verbosity: int = 1, autoclobber: bool = False, **kwargs: Any) -> str:
        """Create a test database and return its name."""
        test_database_name = self._get_test_database_name()
        
        # SQLite creates the file on connect
        import sqlite3
        conn = sqlite3.connect(test_database_name)
        conn.close()
        
        if verbosity >= 1:
            print(f"Creating test database: {test_database_name}")
        
        return test_database_name

    def destroy_test_db(self, test_database_name: str, verbosity: int = 1) -> None:
        """Destroy the test database."""
        if os.path.exists(test_database_name):
            os.remove(test_database_name)
            if verbosity >= 1:
                print(f"Destroying test database: {test_database_name}")

    def _clone_test_db(self, source_database_name: str, test_database_name: str, verbosity: int = 0) -> None:
        """Clone an existing database for testing. Not used for SQLite."""
        import shutil
        shutil.copy2(source_database_name, test_database_name)
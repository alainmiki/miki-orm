"""PostgreSQL test database creation utilities."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional


class DatabaseCreation:
    """Handles test database creation for PostgreSQL."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", "postgres")
        self.user = config.get("USER", "postgres")
        self.password = config.get("PASSWORD", "")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT", 5432)
        self.template = config.get("OPTIONS", {}).get("template", "template0")

    def _get_test_database_name(self) -> str:
        """Generate a unique test database name."""
        return f"test_{self.database}_{os.getpid()}"

    def _run_command(self, cmd: List[str]) -> None:
        """Run a PostgreSQL command."""
        import subprocess
        env = os.environ.copy()
        if self.password:
            env["PGPASSWORD"] = self.password
        subprocess.run(cmd, env=env, check=False)

    def create_test_db(self, verbosity: int = 1, autoclobber: bool = False, **kwargs: Any) -> str:
        """Create a test database and return its name."""
        test_database_name = self._get_test_database_name()
        
        cmd = [
            "createdb",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "--template", self.template,
            "-l", "en_US.UTF-8",
            test_database_name,
        ]
        
        try:
            self._run_command(cmd)
        except Exception:
            pass  # Database might already exist
        
        if verbosity >= 1:
            print(f"Creating test database: {test_database_name}")
        
        return test_database_name

    def destroy_test_db(self, test_database_name: str, verbosity: int = 1) -> None:
        """Destroy the test database."""
        cmd = [
            "dropdb",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "--if-exists",
            test_database_name,
        ]
        
        self._run_command(cmd)
        
        if verbosity >= 1:
            print(f"Destroying test database: {test_database_name}")

    def _clone_test_db(self, source_database_name: str, test_database_name: str, verbosity: int = 0) -> None:
        """Clone an existing database for testing using template."""
        cmd = [
            "createdb",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "--template", source_database_name,
            test_database_name,
        ]
        self._run_command(cmd)
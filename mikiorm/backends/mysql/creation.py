"""MySQL test database creation utilities."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class DatabaseCreation:
    """Handles test database creation for MySQL."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", "mysql")
        self.user = config.get("USER", "root")
        self.password = config.get("PASSWORD", "")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT", 3306)

    def _get_test_database_name(self) -> str:
        """Generate a unique test database name."""
        return f"test_{self.database}_{os.getpid()}"

    def _run_command(self, cmd: List[str]) -> None:
        """Run a MySQL command."""
        import subprocess
        env = os.environ.copy()
        if self.password:
            env["MYSQL_PWD"] = self.password
        subprocess.run(cmd, env=env, check=False)

    def create_test_db(self, verbosity: int = 1, autoclobber: bool = False, **kwargs: Any) -> str:
        """Create a test database and return its name."""
        test_database_name = self._get_test_database_name()
        
        cmd = [
            "mysqladmin",
            "-h", self.host,
            "-P", str(self.port),
            "-u", self.user,
            "create",
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
            "mysqladmin",
            "-h", self.host,
            "-P", str(self.port),
            "-u", self.user,
            "-f",
            "drop",
            test_database_name,
        ]
        
        self._run_command(cmd)
        
        if verbosity >= 1:
            print(f"Destroying test database: {test_database_name}")
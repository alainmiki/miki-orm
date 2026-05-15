"""MySQL database client and utilities."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional


class DatabaseClient:
    """Encapsulates database client operations for MySQL."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", "mysql")
        self.user = config.get("USER", "root")
        self.password = config.get("PASSWORD", "")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT", 3306)

    def runshell(self) -> None:
        """Run the mysql command-line shell."""
        env = os.environ.copy()
        if self.password:
            env["MYSQL_PWD"] = self.password
        
        cmd = [
            "mysql",
            "-h", self.host,
            "-P", str(self.port),
            "-u", self.user,
            self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=False)
        except FileNotFoundError:
            raise RuntimeError("mysql command not found. Install MySQL CLI.")

    def create_database(self) -> None:
        """Create a new database if it doesn't exist."""
        env = os.environ.copy()
        if self.password:
            env["MYSQL_PWD"] = self.password
        
        cmd = [
            "mysqladmin",
            "-h", self.host,
            "-P", str(self.port),
            "-u", self.user,
            "create",
            self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=True)
        except FileNotFoundError:
            raise RuntimeError("mysqladmin command not found. Install MySQL CLI.")
        except subprocess.CalledProcessError as e:
            if "database exists" not in str(e).lower():
                raise

    def destroy_database(self) -> None:
        """Destroy the database."""
        env = os.environ.copy()
        if self.password:
            env["MYSQL_PWD"] = self.password
        
        cmd = [
            "mysqladmin",
            "-h", self.host,
            "-P", str(self.port),
            "-u", self.user,
            "--force",
            "drop",
            self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=False)
        except FileNotFoundError:
            raise RuntimeError("mysqladmin command not found. Install MySQL CLI.")

    def get_database_filename(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.database}"


def get_client(config: Dict[str, Any]) -> DatabaseClient:
    """Return a DatabaseClient instance for the given config."""
    return DatabaseClient(config)
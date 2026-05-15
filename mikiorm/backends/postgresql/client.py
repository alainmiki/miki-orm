"""PostgreSQL database client and utilities."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional


class DatabaseClient:
    """Encapsulates database client operations for PostgreSQL."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.database = config.get("NAME", "postgres")
        self.user = config.get("USER", "postgres")
        self.password = config.get("PASSWORD", "")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT", 5432)

    def runshell(self) -> None:
        """Run the psql command-line shell."""
        env = os.environ.copy()
        if self.password:
            env["PGPASSWORD"] = self.password
        
        cmd = [
            "psql",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-d", self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=False)
        except FileNotFoundError:
            raise RuntimeError("psql command not found. Install PostgreSQL CLI.")

    def create_database(self) -> None:
        """Create a new database if it doesn't exist."""
        env = os.environ.copy()
        if self.password:
            env["PGPASSWORD"] = self.password
        
        cmd = [
            "createdb",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "--encoding=UTF8",
            "--lc-collate=en_US.UTF-8",
            "--lc-ctype=en_US.UTF-8",
            self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=True)
        except FileNotFoundError:
            raise RuntimeError("createdb command not found. Install PostgreSQL CLI.")
        except subprocess.CalledProcessError as e:
            if "already exists" not in str(e):
                raise

    def destroy_database(self) -> None:
        """Destroy the database."""
        env = os.environ.copy()
        if self.password:
            env["PGPASSWORD"] = self.password
        
        cmd = [
            "dropdb",
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "--if-exists",
            self.database,
        ]
        
        try:
            subprocess.run(cmd, env=env, check=False)
        except FileNotFoundError:
            raise RuntimeError("dropdb command not found. Install PostgreSQL CLI.")

    def get_database_filename(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.database}"


def get_client(config: Dict[str, Any]) -> DatabaseClient:
    """Return a DatabaseClient instance for the given config."""
    return DatabaseClient(config)
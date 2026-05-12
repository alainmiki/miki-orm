"""Universal database configuration and settings management."""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict

# Lazy imports to avoid circular dependencies
def _get_sync_adapters():
    from .connections import MySQLAdapter, PostgresAdapter, SQLiteAdapter
    return MySQLAdapter, PostgresAdapter, SQLiteAdapter

def _get_async_adapters():
    try:
        from .connections import AsyncMySQLAdapter, AsyncPostgresAdapter, AsyncSQLiteAdapter
        return AsyncMySQLAdapter, AsyncPostgresAdapter, AsyncSQLiteAdapter
    except ImportError:
        return None, None, None


class ConnectionManager:
    """Manages synchronous database connections."""

    def __init__(self) -> None:
        self._connections: Dict[str, Any] = {}

    def get_connection(self, db_alias: str = "default") -> Any:
        """Get or create a synchronous connection for the given alias."""
        if db_alias not in self._connections:
            db_config = settings.databases.get(db_alias)
            if not db_config:
                raise ValueError(f"No database configuration for alias '{db_alias}'")
            adapter = db_config.get_sync_adapter()
            config = db_config.get_connection_config()
            self._connections[db_alias] = adapter.connect(config)
        return self._connections[db_alias]

    def close_all(self) -> None:
        """Close all managed connections."""
        for conn in self._connections.values():
            if hasattr(conn, "close"):
                conn.close()
        self._connections.clear()


class AsyncConnectionManager:
    """Manages asynchronous database connections."""

    def __init__(self) -> None:
        self._connections: Dict[str, Any] = {}

    async def get_connection(self, db_alias: str = "default") -> Any:
        """Get or create an async connection for the given alias."""
        if db_alias not in self._connections:
            db_config = settings.databases.get(db_alias)
            if not db_config:
                raise ValueError(f"No database configuration for alias '{db_alias}'")
            adapter = db_config.get_async_adapter()
            config = db_config.get_connection_config()
            self._connections[db_alias] = await adapter.connect(config)
        return self._connections[db_alias]

    async def close_all(self) -> None:
        """Close all managed async connections."""
        for conn in self._connections.values():
            if hasattr(conn, "close"):
                await conn.close()
        self._connections.clear()


# Global managers
connection_manager = ConnectionManager()
async_connection_manager = AsyncConnectionManager()


class DatabaseConfig:
    """Configuration for a single database connection."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.engine = config.get("ENGINE", "sqlite")
        self.name = config.get("NAME", ":memory:")
        self.user = config.get("USER")
        self.password = config.get("PASSWORD")
        self.host = config.get("HOST", "localhost")
        self.port = config.get("PORT")
        self.options = config.get("OPTIONS", {})
        self.ssl = config.get("SSL", {})
        self.pool = config.get("POOL", {})
        self.secrets = config.get("SECRETS", {})

    def get_sync_adapter(self) -> BaseAdapter:
        """Return the appropriate synchronous adapter based on engine."""
        MySQLAdapter, PostgresAdapter, SQLiteAdapter = _get_sync_adapters()
        if self.engine == "sqlite":
            return SQLiteAdapter()
        elif self.engine == "postgresql":
            return PostgresAdapter()
        elif self.engine == "mysql":
            return MySQLAdapter()
        else:
            raise ValueError(f"Unsupported engine: {self.engine}")

    def get_async_adapter(self) -> BaseAsyncAdapter:
        """Return the appropriate asynchronous adapter based on engine."""
        AsyncMySQLAdapter, AsyncPostgresAdapter, AsyncSQLiteAdapter = _get_async_adapters()
        if AsyncSQLiteAdapter is None:
            raise ImportError("Async database adapters not available. Install async dependencies.")
        if self.engine == "sqlite":
            return AsyncSQLiteAdapter()
        elif self.engine == "postgresql":
            return AsyncPostgresAdapter()
        elif self.engine == "mysql":
            return AsyncMySQLAdapter()
        else:
            raise ValueError(f"Unsupported async engine: {self.engine}")

    def get_adapter(self) -> BaseAdapter:
        """Return the appropriate synchronous adapter (legacy)."""
        return self.get_sync_adapter()

    def get_connection_config(self) -> Dict[str, Any]:
        """Build connection config dict for adapter."""
        config = {
            "NAME": self.name,
            "USER": self.user,
            "PASSWORD": self.password,
            "HOST": self.host,
            "PORT": self.port,
            **self.options,
        }
        # Handle secrets if needed
        if self.secrets:
            for key, secret_key in self.secrets.items():
                config[key] = os.getenv(secret_key, config.get(key))
        return config


class Settings:
    """Global settings container, similar to Django settings."""

    def __init__(self) -> None:
        self.databases: Dict[str, DatabaseConfig] = {}
        self.default_database = "default"
        self.installed_apps: list[str] = []

    def configure_databases(self, databases: Dict[str, Dict[str, Any]]) -> None:
        """Configure databases from a dict like Django's DATABASES."""
        for alias, config in databases.items():
            self.databases[alias] = DatabaseConfig(config)

    def install_app(self, app_name: str) -> None:
        """Import and register an application module with models."""
        if app_name in self.installed_apps:
            return
        importlib.import_module(app_name)
        self.installed_apps.append(app_name)
        try:
            importlib.import_module(f"{app_name}.models")
        except ModuleNotFoundError:
            pass

    def get_database(self, name: str | None = None) -> DatabaseConfig:
        """Get database config by name."""
        name = name or self.default_database
        if name not in self.databases:
            raise ValueError(f"Database '{name}' not configured")
        return self.databases[name]


# Global settings instance
settings = Settings()


def configure(databases: Dict[str, Dict[str, Any]], **kwargs: Any) -> None:
    """Convenience function to configure global settings."""
    settings.configure_databases(databases)
    for key, value in kwargs.items():
        setattr(settings, key, value)

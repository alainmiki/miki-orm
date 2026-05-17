"""Compatibility shim for legacy settings imports.

This module exposes the configuration and connection manager API from
:mikiorm.conf.settings so internal code and examples that import
:mikiorm.settings continue to work.
"""

from .conf.settings import (
    AsyncConnectionManager,
    ConnectionManager,
    DatabaseConfig,
    Settings,
    async_connection_manager,
    configure,
    connection_manager,
    register_async_adapter,
    register_sync_adapter,
    settings,
)

__all__ = [
    "AsyncConnectionManager",
    "ConnectionManager",
    "DatabaseConfig",
    "Settings",
    "async_connection_manager",
    "configure",
    "connection_manager",
    "register_async_adapter",
    "register_sync_adapter",
    "settings",
]

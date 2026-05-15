"""Configuration package - exposes the canonical settings singleton.

Application code typically interacts with this module via the top-level
helpers ``mikiorm.configure`` and ``mikiorm.settings``.
"""

from .settings import (
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

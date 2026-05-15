"""MySQL backend module for mikiORM.

This module provides MySQL-specific database backend implementations
following Django's database backend architecture pattern.

Usage:
    from mikiorm.backends.mysql import MySQLAdapter, DatabaseOperations, DatabaseSchemaEditor
"""

from .base import MySQLAdapter, MySQLConnection
from .async_mysql import AsyncMySQLAdapter, AsyncMySQLConnection
from .client import DatabaseClient, get_client
from .creation import DatabaseCreation
from .introspection import DatabaseIntrospection
from .features import DatabaseFeatures
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

__all__ = [
    # Sync
    "MySQLAdapter",
    "MySQLConnection",
    # Async
    "AsyncMySQLAdapter",
    "AsyncMySQLConnection",
    # Utilities
    "DatabaseClient",
    "get_client",
    "DatabaseCreation",
    "DatabaseIntrospection",
    "DatabaseFeatures",
    "DatabaseOperations",
    "DatabaseSchemaEditor",
]
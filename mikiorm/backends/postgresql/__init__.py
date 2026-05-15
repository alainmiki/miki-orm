"""PostgreSQL backend module for mikiORM.

This module provides PostgreSQL-specific database backend implementations
following Django's database backend architecture pattern.

Usage:
    from mikiorm.backends.postgresql import PostgresAdapter, DatabaseOperations, DatabaseSchemaEditor
"""

from .base import PostgresAdapter, PostgresConnection
from .async_postgresql import AsyncPostgresAdapter, AsyncPostgresConnection
from .client import DatabaseClient, get_client
from .creation import DatabaseCreation
from .introspection import DatabaseIntrospection
from .features import DatabaseFeatures
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

__all__ = [
    # Sync
    "PostgresAdapter",
    "PostgresConnection",
    # Async
    "AsyncPostgresAdapter",
    "AsyncPostgresConnection",
    # Utilities
    "DatabaseClient",
    "get_client",
    "DatabaseCreation",
    "DatabaseIntrospection",
    "DatabaseFeatures",
    "DatabaseOperations",
    "DatabaseSchemaEditor",
]
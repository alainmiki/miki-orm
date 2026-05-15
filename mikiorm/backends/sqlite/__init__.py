"""SQLite backend module for mikiORM.

This module provides SQLite-specific database backend implementations
following Django's database backend architecture pattern.

Usage:
    from mikiorm.backends.sqlite import SQLiteDatabase, DatabaseOperations, DatabaseSchemaEditor
"""

from .base import SQLiteAdapter, SQLiteConnection
from .async_sqlite import AsyncSQLiteAdapter, AsyncSQLiteConnection
from .client import DatabaseClient, get_client
from .creation import DatabaseCreation
from .introspection import DatabaseIntrospection
from .features import DatabaseFeatures
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

__all__ = [
    # Sync
    "SQLiteAdapter",
    "SQLiteConnection",
    # Async
    "AsyncSQLiteAdapter",
    "AsyncSQLiteConnection",
    # Utilities
    "DatabaseClient",
    "get_client",
    "DatabaseCreation",
    "DatabaseIntrospection",
    "DatabaseFeatures",
    "DatabaseOperations",
    "DatabaseSchemaEditor",
]
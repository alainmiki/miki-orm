"""mikiORM Backends package.

This package provides database backend implementations following Django's
database backend architecture pattern.

Available backends:
    - sqlite: SQLite backend for development and embedded use
    - postgresql: PostgreSQL backend for production use
    - mysql: MySQL backend for production use
    - oracle: Oracle backend (requires cx_Oracle)
    - dummy: In-memory SQLite for testing

Usage:
    from mikiorm.backends.sqlite import SQLiteAdapter, DatabaseOperations
    from mikiorm.backends.postgresql import PostgresAdapter
    from mikiorm.backends.mysql import MySQLAdapter
"""

from .base.base import BaseDatabaseWrapper, DatabaseSettings, get_dialect_from_engine

__all__ = [
    "BaseDatabaseWrapper",
    "DatabaseSettings",
    "get_dialect_from_engine",
]
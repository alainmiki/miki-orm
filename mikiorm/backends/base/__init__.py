"""Backend base primitives: connection/adapter contracts, pools, and dialects.

Single source of truth - every concrete backend (sqlite, postgresql, mysql,
oracle, dummy) imports its base classes from here.
"""

from .adapter import (
    BaseAdapter,
    BaseAsyncAdapter,
    BaseAsyncConnection,
    BaseConnection,
    get_param_placeholder,
)
from .base import BaseDatabaseWrapper, DatabaseSettings, get_dialect_from_engine
from .dialect import Dialect, SafeBuilder, get_safe_builder
from .pool import (
    AsyncConnectionPool,
    PooledAsyncConnection,
    PooledConnection,
    SyncConnectionPool,
)
from .schema_editor import SchemaEditor, field_to_sql_type

__all__ = [
    "SchemaEditor",
    "field_to_sql_type",
    # adapter / connection
    "BaseAdapter",
    "BaseAsyncAdapter",
    "BaseConnection",
    "BaseAsyncConnection",
    "get_param_placeholder",
    # high-level wrapper
    "BaseDatabaseWrapper",
    "DatabaseSettings",
    "get_dialect_from_engine",
    # dialect / SQL building
    "Dialect",
    "SafeBuilder",
    "get_safe_builder",
    # pools
    "AsyncConnectionPool",
    "SyncConnectionPool",
    "PooledConnection",
    "PooledAsyncConnection",
]

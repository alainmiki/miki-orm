"""miki-orm package entry point."""

from .models.base import Model
from .models.relationships import (
    CASCADE,
    DO_NOTHING,
    PROTECT,
    SET,
    SET_DEFAULT,
    SET_NULL,
)
from .connections.base import BaseConnection
from .migrations.engine import MigrationEngine
from .managers.base import Manager
from .settings import configure

__all__ = [
    "Model",
    "BaseConnection",
    "MigrationEngine",
    "Manager",
    "configure",
    "CASCADE",
    "SET_NULL",
    "SET_DEFAULT",
    "PROTECT",
    "DO_NOTHING",
    "SET",
]

__version__ = "0.1.0"
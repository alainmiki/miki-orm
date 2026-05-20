# mikiorm/__init__.py
from .models import Model, register
from .managers import Manager as BaseManager
from .backends import Postgres,SQLite,MySQL
from .conf.settings import configure, configure_from_module, settings
from .migrations.engine import MigrationEngine
from .unit_of_work.transaction import atomic, async_atomic, get_current_transaction
from .query.expressions import Q, F

from . import models


def makemigrations(app_labels=None):
    """Generate migration operations for configured models."""
    engine = MigrationEngine()
    return engine.makemigrations(app_labels)


def migrate(connection=None, target=None):
    """Apply migrations to the configured database."""
    engine = MigrationEngine()
    return engine.migrate(connection=connection, target=target)


__all__ = [
    "Model",
    "register",
    "BaseManager",
    "Postgres",
    "SQLite",
    "MySQL",
    "configure",
    "configure_from_module",
    "settings",
    "MigrationEngine",
    "makemigrations",
    "migrate",
    "models",
    "atomic",
    "async_atomic",
    "get_current_transaction",
    "Q",
    "F",
]

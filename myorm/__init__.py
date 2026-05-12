"""miki-orm package entry point."""

import importlib

from . import models
from .models.base import Model, ObjectDoesNotExist, MultipleObjectsReturned
from .models.relationships import (
    CASCADE,
    DO_NOTHING,
    PROTECT,
    SET,
    SET_DEFAULT,
    SET_NULL,
)
from .managers.base import Manager
from .models.registry import ModelRegistry
from .settings import configure, settings
from .migrations.engine import MigrationEngine


def register_model(model: type[Model]) -> None:
    """Register a model with the ORM registry."""
    ModelRegistry.register_model(model)


def install_app(app_name: str) -> None:
    """Import and register an application package with models."""
    if app_name in settings.installed_apps:
        return
    importlib.import_module(app_name)
    settings.installed_apps.append(app_name)
    try:
        importlib.import_module(f"{app_name}.models")
    except ModuleNotFoundError:
        pass


def makemigrations(app_label: str | list[type[Model]] | None = None) -> list[object]:
    """Generate migrations for the registered models or an app label."""
    engine = MigrationEngine()
    return engine.makemigrations(app_label)


def migrate(target: str | None = None) -> None:
    """Apply pending migrations using the configured database."""
    engine = MigrationEngine()
    return engine.migrate(target=target)


__all__ = [
    "models",
    "Model",
    "ObjectDoesNotExist",
    "MultipleObjectsReturned",
    "Manager",
    "configure",
    "settings",
    "register_model",
    "install_app",
    "CASCADE",
    "SET_NULL",
    "SET_DEFAULT",
    "PROTECT",
    "DO_NOTHING",
    "SET",
]

__version__ = "0.1.0"
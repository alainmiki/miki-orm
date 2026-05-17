"""Base classes for database schema editing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Type, Optional

from mikiorm.models import (
    CASCADE,
    DO_NOTHING,
    PROTECT,
    # RESTRICT,
    SET_NULL,
)

if TYPE_CHECKING:
    from mikiorm.backends.base.adapter import BaseConnection
    from mikiorm.models.base import Model
    from mikiorm.models.fields import Field


class BaseSchemaEditor(ABC):
    """Base class for database schema editing operations.

    Subclasses should implement the abstract methods for the concrete
    database backends. The class also provides several helper methods
    commonly useful during schema generation.
    """

    def __init__(self, connection: "BaseConnection") -> None:
        self.connection = connection

    @abstractmethod
    def create_model(self, model: Type["Model"]) -> None:
        """Create the table for the given model."""

    @abstractmethod
    def add_field(self, model: Type["Model"], field: "Field") -> None:
        """Add a column to an existing table."""

    @abstractmethod
    def remove_field(self, model: Type["Model"], field: "Field") -> None:
        """Remove a column from an existing table."""

    @abstractmethod
    def alter_field(
        self, model: Type["Model"], old_field: "Field", new_field: "Field"
    ) -> None:
        """Alter an existing column to a new definition."""

    @abstractmethod
    def rename_field(self, model: Type["Model"], old_name: str, new_name: str) -> None:
        """Rename a column on the model's table."""

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Execute raw SQL using the underlying connection."""
        # Connection adapter is expected to expose an execute method
        if params is None:
            params = ()
        self.connection.execute(sql, params)

    def sql_on_delete(self, on_delete_action: str) -> str:
        """Return the SQL fragment for an ON DELETE clause based on the
        on_delete action defined on relation fields.
        """
        if on_delete_action == CASCADE:
            return "ON DELETE CASCADE"
        if on_delete_action == PROTECT:
            # PROTECT is not a SQL standard action; use RESTRICT where
            # appropriate or leave empty for backends that support triggers.
            return "ON DELETE RESTRICT"
        if on_delete_action == SET_NULL:
            return "ON DELETE SET NULL"
        if on_delete_action == RESTRICT:
            return "ON DELETE RESTRICT"
        if on_delete_action == DO_NOTHING:
            return "ON DELETE NO ACTION"
        return ""

    def add_index(self, model: Type["Model"], columns: list[str], name: Optional[str] = None) -> None:
        """Create an index for the given model and columns.

        Concrete backends may override to provide optimized implementations.
        """
        table = model._meta.table_name  # type: ignore[attr-defined]
        cols = ", ".join(columns)
        idx_name = name or f"idx_{table}_{'_'.join(columns)}"
        sql = f"CREATE INDEX {idx_name} ON {table} ({cols})"
        self.execute(sql)

    def remove_index(self, model: Type["Model"], name: str) -> None:
        """Remove an index by name."""
        table = model._meta.table_name  # type: ignore[attr-defined]
        sql = f"DROP INDEX {name}"
        # Some backends require table-qualified drop; backend adapters can
        # override this method if needed.
        self.execute(sql)

    def __enter__(self) -> "BaseSchemaEditor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Default implementation: no special cleanup. Subclasses may
        # implement transaction commit/rollback here.
        return None

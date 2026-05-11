"""Relationship field definitions like ForeignKey and ManyToMany.

Mirrors django.db.models.fields.related.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

from .fields import Field


def _do_nothing() -> None:
    """No-op on_delete handler (prevents deletion by raising in real Django)."""


def cascade() -> None:
    """Cascade deletion marker (conceptual; real enforcement is DB-level)."""


def set_null() -> None:
    """Set FK to NULL on deletion."""


def set_default() -> None:
    """Set FK to default value on deletion."""


def protect() -> None:
    """Prevent deletion of the referenced object."""


@dataclass
class ForeignKey(Field):
    """Many-to-one relationship.

    ``on_delete`` should be a callable (CASCADE, SET_NULL, PROTECT, etc.).
    In a minimal ORM the callable is stored for metadata purposes; real
    enforcement happens at the database or session level.
    """

    to: str = ""
    on_delete: Callable[[], None] = cascade
    related_name: str | None = None
    related_query_name: str | None = None
    to_field: str | None = None
    limit_choices_to: Any = None
    db_constraint: bool = True
    swappable: bool = True

    def python_value(self, value: Any) -> Any:
        """Return the raw value (typically the PK of the related object)."""
        return value

    def db_value(self, value: Any) -> Any:
        """Return the PK value for DB storage."""
        if value is None:
            return None if self.null else 0
        # If it's a Model instance, extract the PK
        if hasattr(value, "pk"):
            return value.pk
        return value

    def get_internal_type(self) -> str:
        return "ForeignKey"


@dataclass
class OneToOneField(ForeignKey):
    """One-to-one relationship.

    Inherits ForeignKey; the distinction is semantic (one-to-one vs many-to-one).
    """

    def get_internal_type(self) -> str:
        return "OneToOneField"


@dataclass
class ManyToManyField(Field):
    """Many-to-many relationship.

    Creates an intermediary table automatically unless ``through`` is set.
    ``symmetrical`` applies only when the relationship is self-referential.
    """

    to: str = ""
    related_name: str | None = None
    related_query_name: str | None = None
    limit_choices_to: Any = None
    symmetrical: bool = True
    through: str | None = None
    through_fields: tuple[str, str] | None = None
    db_constraint: bool = True
    db_table: str | None = None
    swappable: bool = True

    def python_value(self, value: Any) -> Any:
        """Return a manager-like object (placeholder in this lightweight ORM)."""
        return value

    def db_value(self, value: Any) -> Any:
        """ManyToMany fields are not stored on the model's table."""
        return None

    def get_internal_type(self) -> str:
        return "ManyToManyField"
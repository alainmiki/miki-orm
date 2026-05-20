"""Relationship field definitions like ForeignKey and ManyToMany.

Mirrors django.db.models.fields.related.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

from .fields import Field


# ---------------------------------------------------------------------------
# on_delete handlers
# ---------------------------------------------------------------------------
# Mirrors django.db.models.deletion.CASCADE, SET_NULL, PROTECT, etc.

def CASCADE() -> None:
    """Cascade deletion: delete the referencing object too.

    In a full ORM this triggers a recursive delete.  Here it serves as
    a marker; the actual deletion logic lives in the Session/UnitOfWork.
    """


def SET_NULL() -> None:
    """Set the FK to NULL on deletion of the referenced object.

    Requires the FK field to have ``null=True``.
    """


def SET_DEFAULT() -> None:
    """Set the FK to its default value on deletion of the referenced object.

    Requires the FK field to have a ``default`` defined.
    """


def PROTECT() -> None:
    """Prevent deletion of the referenced object.

    Raises ``ProtectedError`` at the session/unit-of-work level.
    """


def DO_NOTHING() -> None:
    """Take no action; rely on database integrity constraints.

    This may cause IntegrityError at the database level.
    """


def SET(value: Any) -> None:
    """Set the FK to *value* on deletion of the referenced object.

    *value* can be a concrete value or a callable that returns one.
    """


# ---------------------------------------------------------------------------
# Relationship fields
# ---------------------------------------------------------------------------

@dataclass
class ForeignKey(Field):
    """Many-to-one relationship.

    ``on_delete`` should be a callable (CASCADE, SET_NULL, PROTECT, etc.).
    In a minimal ORM the callable is stored for metadata purposes; real
    enforcement happens at the database or session level.
    """

    to: str = ""
    on_delete: Callable[[], None] = CASCADE
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
            if self.null:
                return None
            raise ValueError("This ForeignKey does not allow null values.")
        if hasattr(value, "pk"):
            return value.pk
        return value

    def validate(self, value: Any) -> Any:
        if value is None:
            return super().validate(value)
        if hasattr(value, "pk"):
            return getattr(value, "pk")
        return super().validate(value)

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

    def __get__(self, instance, owner):
        if instance is None:
            return self
        # Lazy import to avoid circular
        from .m2m import ManyToManyManager
        return ManyToManyManager(instance, self)

    def __set__(self, instance, value):
        raise AttributeError("Cannot assign to ManyToManyField directly; use manager methods like .add()/.clear()")

    def python_value(self, value: Any) -> Any:
        """Return a manager-like object."""
        return value

    def db_value(self, value: Any) -> Any:
        """ManyToMany fields are not stored on the model's table."""
        return None

    def get_internal_type(self) -> str:
        return "ManyToManyField"


class ReverseForeignKeyDescriptor:
    def __init__(self, field: ForeignKey, source_model: type[Any]) -> None:
        self.field = field
        self.source_model = source_model

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        return self.source_model.objects.filter(**{self.field.name: instance.pk})


class ReverseOneToOneDescriptor(ReverseForeignKeyDescriptor):
    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        from .base import ObjectDoesNotExist

        try:
            return self.source_model.objects.get(**{self.field.name: instance.pk})
        except ObjectDoesNotExist:
            return None


class ForwardForeignKeyDescriptor:
    """Descriptor for forward ForeignKey/OneToOne access.

    When accessed on an instance, returns the related model instance (or None).
    Accepts either an instance or a PK when assigned.
    """

    def __init__(self, field: ForeignKey) -> None:
        self.field = field

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        value = instance.__dict__.get(self.field.name)
        if value is None:
            return None
        if hasattr(value, "pk"):
            return value
        related_model = self._resolve_related_model()
        try:
            return related_model.objects.get(pk=value)
        except Exception:
            return None

    def __set__(self, instance: Any, value: Any) -> None:
        if value is None:
            instance.__dict__[self.field.name] = None
            return
        if hasattr(value, "pk"):
            instance.__dict__[self.field.name] = value.pk
        else:
            instance.__dict__[self.field.name] = value

    def _resolve_related_model(self) -> type[Any]:
        target = self.field.to
        if isinstance(target, str):
            from ..models.register import ModelRegistry

            model = ModelRegistry.get_model(target)
            if model is None:
                raise LookupError(f"Related model '{target}' not registered")
            return model
        return target

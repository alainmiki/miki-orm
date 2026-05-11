"""Tracks model instances for unit of work commit/rollback.

Handles on_delete semantics for ForeignKey relationships:
- CASCADE   : delete dependent objects
- SET_NULL  : set FK to None
- PROTECT   : raise if referenced object is in deleted set
- SET_DEFAULT: set FK to field default
- DO_NOTHING: no action (DB constraint may fail)
"""

from __future__ import annotations

from typing import Any


class UnitOfWorkTracker:
    def __init__(self) -> None:
        self.new: list[Any] = []
        self.dirty: list[Any] = []
        self.deleted: list[Any] = []

    def register_new(self, obj: Any) -> None:
        if obj not in self.new:
            self.new.append(obj)

    def register_dirty(self, obj: Any) -> None:
        if obj not in self.dirty and obj not in self.new:
            self.dirty.append(obj)

    def register_deleted(self, obj: Any) -> None:
        if obj not in self.deleted:
            self.deleted.append(obj)

    def cascade_deletes(self, obj: Any) -> list[Any]:
        """Return a list of objects to delete due to CASCADE on FKs."""
        to_delete: list[Any] = []
        # Walk all registered objects and find those with FKs pointing to obj
        for tracked in self.new + self.dirty:
            for field_name, field_obj in tracked._meta.fields.items():
                fk = getattr(tracked, field_name, None)
                if isinstance(field_obj, dict) and field_obj.get("on_delete") is not None:
                    # Check if this FK references the deleted object's PK
                    pk_field = getattr(obj, "pk", None)
                    if pk_field is not None and fk == pk_field:
                        to_delete.append(tracked)
        return to_delete

    def clear(self) -> None:
        self.new.clear()
        self.dirty.clear()
        self.deleted.clear()
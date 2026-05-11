"""Commit and rollback logic for unit of work.

Handles on_delete semantics for ForeignKey relationships during commit.
"""

from __future__ import annotations

from typing import Any

from ..models.relationships import DO_NOTHING, PROTECT, SET, SET_DEFAULT, SET_NULL


class CommitManager:
    def __init__(self, tracker: Any) -> None:
        self.tracker = tracker

    def _get_on_delete(self, field_obj: Any) -> callable:
        """Return the on_delete callable for a ForeignKey field."""
        on_delete = getattr(field_obj, "on_delete", None)
        if callable(on_delete):
            return on_delete
        return DO_NOTHING

    def _handle_on_delete(self, obj: Any, connection: Any) -> None:
        """Process on_delete actions for FKs pointing to *obj*."""
        obj_pk = getattr(obj, "pk", None)
        if obj_pk is None:
            return

        model_cls = type(obj)
        # Scan all tracked (non-deleted) objects for FK references to obj
        for tracked in self.tracker.new + self.tracker.dirty:
            if tracked is obj:
                continue
            for field_name, field_obj in tracked._meta.fields.items():
                # Check if this field looks like a ForeignKey
                if not hasattr(field_obj, "on_delete"):
                    continue
                fk_value = getattr(tracked, field_name, None)
                if fk_value == obj_pk:
                    on_delete = self._get_on_delete(field_obj)
                    if on_delete is DO_NOTHING or on_delete.__name__ == "DO_NOTHING":
                        # Rely on DB constraint — do nothing in ORM
                        continue
                    elif on_delete is PROTECT or on_delete.__name__ == "PROTECT":
                        raise RuntimeError(
                            f"Cannot delete {model_cls.__name__}(pk={obj_pk}): "
                            f"{type(tracked).__name__}.{field_name} has PROTECT"
                        )
                    elif on_delete is SET_NULL or on_delete.__name__ == "SET_NULL":
                        if field_obj.null:
                            setattr(tracked, field_name, None)
                            self.tracker.register_dirty(tracked)
                    elif on_delete is SET_DEFAULT or on_delete.__name__ == "SET_DEFAULT":
                        default = getattr(field_obj, "default", None)
                        setattr(tracked, field_name, default)
                        self.tracker.register_dirty(tracked)
                    elif on_delete is SET or on_delete.__name__ == "SET":
                        # SET requires a value argument — here we just no-op
                        pass
                    else:
                        # CASCADE (default) or any other callable: delete dependent
                        self.tracker.register_deleted(tracked)

    def commit(self, connection: Any) -> None:
        # First handle deletes with on_delete semantics
        for obj in list(self.tracker.deleted):
            self._handle_on_delete(obj, connection)

        for obj in self.tracker.new:
            obj.save(connection, force_insert=True)
        for obj in self.tracker.dirty:
            obj.save(connection)
        for obj in self.tracker.deleted:
            obj.delete(connection)
        connection.commit()
        self.tracker.clear()

    def rollback(self, connection: Any) -> None:
        connection.rollback()
        self.tracker.clear()
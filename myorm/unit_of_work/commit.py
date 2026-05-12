"""Commit and rollback logic for unit of work.

Handles on_delete semantics for ForeignKey relationships during commit.
"""

from __future__ import annotations

from typing import Any

from ..models.relationships import DO_NOTHING, PROTECT, SET, SET_DEFAULT, SET_NULL


class CommitManager:
    """Synchronous commit manager for unit of work."""
    
    def __init__(self, tracker: Any) -> None:
        self.tracker = tracker

    def _get_on_delete(self, field_obj: Any) -> callable:
        on_delete = getattr(field_obj, "on_delete", None)
        if callable(on_delete):
            return on_delete
        return DO_NOTHING

    def _handle_on_delete(self, obj: Any, connection: Any) -> None:
        """Process on_delete actions for FKs pointing to *obj*."""
        obj_pk = getattr(obj, "pk", None)
        if obj_pk is None:
            return

        # Scan all tracked objects for FK references to obj
        for tracked in self.tracker.new + self.tracker.dirty:
            if tracked is obj:
                continue
            for field_name, field_obj in tracked._meta.fields.items():
                if not hasattr(field_obj, "on_delete"):
                    continue
                fk_value = getattr(tracked, field_name, None)
                if fk_value == obj_pk:
                    on_delete = self._get_on_delete(field_obj)
                    if on_delete is DO_NOTHING or (callable(on_delete) and on_delete.__name__ == "DO_NOTHING"):
                        continue
                    elif on_delete is PROTECT or (callable(on_delete) and on_delete.__name__ == "PROTECT"):
                        raise RuntimeError(
                            f"Cannot delete {type(obj).__name__}(pk={obj_pk}): "
                            f"{type(tracked).__name__}.{field_name} has PROTECT"
                        )
                    elif on_delete is SET_NULL or (callable(on_delete) and on_delete.__name__ == "SET_NULL"):
                        if field_obj.null:
                            setattr(tracked, field_name, None)
                            self.tracker.register_dirty(tracked)
                    elif on_delete is SET_DEFAULT or (callable(on_delete) and on_delete.__name__ == "SET_DEFAULT"):
                        default = getattr(field_obj, "default", None)
                        setattr(tracked, field_name, default)
                        self.tracker.register_dirty(tracked)
                    elif on_delete is SET or (callable(on_delete) and on_delete.__name__ == "SET"):
                        # SET requires a value argument - handling left concrete
                        pass
                    else:
                        # CASCADE (default)
                        self.tracker.register_deleted(tracked)

    def commit(self, connection: Any) -> None:
        """Flush all tracked changes to the database within UOW."""
        # First handle on_delete semantics for marked deletions
        for obj in list(self.tracker.deleted):
            self._handle_on_delete(obj, connection)

        # Execute new inserts
        for obj in self.tracker.new:
            obj._execute_insert(connection)

        # Execute updates for dirty objects
        for obj in self.tracker.dirty:
            obj._execute_update(connection)

        # Execute deletes
        for obj in self.tracker.deleted:
            obj._execute_delete(connection)

        # Commit the transaction
        connection.commit()
        self.tracker.clear()

    def rollback(self, connection: Any) -> None:
        connection.rollback()
        self.tracker.clear()


class AsyncCommitManager:
    """Asynchronous commit manager for unit of work."""
    
    def __init__(self, tracker: Any) -> None:
        self.tracker = tracker

    def _get_on_delete(self, field_obj: Any) -> callable:
        on_delete = getattr(field_obj, "on_delete", None)
        if callable(on_delete):
            return on_delete
        return DO_NOTHING

    def _handle_on_delete(self, obj: Any, connection: Any) -> None:
        """Process on_delete actions for FKs pointing to *obj*."""
        obj_pk = getattr(obj, "pk", None)
        if obj_pk is None:
            return

        # Scan all tracked objects for FK references to obj
        for tracked in self.tracker.new + self.tracker.dirty:
            if tracked is obj:
                continue
            for field_name, field_obj in tracked._meta.fields.items():
                if not hasattr(field_obj, "on_delete"):
                    continue
                fk_value = getattr(tracked, field_name, None)
                if fk_value == obj_pk:
                    on_delete = self._get_on_delete(field_obj)
                    if on_delete is DO_NOTHING or (callable(on_delete) and on_delete.__name__ == "DO_NOTHING"):
                        continue
                    elif on_delete is PROTECT or (callable(on_delete) and on_delete.__name__ == "PROTECT"):
                        raise RuntimeError(
                            f"Cannot delete {type(obj).__name__}(pk={obj_pk}): "
                            f"{type(tracked).__name__}.{field_name} has PROTECT"
                        )
                    elif on_delete is SET_NULL or (callable(on_delete) and on_delete.__name__ == "SET_NULL"):
                        if field_obj.null:
                            setattr(tracked, field_name, None)
                            self.tracker.register_dirty(tracked)
                    elif on_delete is SET_DEFAULT or (callable(on_delete) and on_delete.__name__ == "SET_DEFAULT"):
                        default = getattr(field_obj, "default", None)
                        setattr(tracked, field_name, default)
                        self.tracker.register_dirty(tracked)
                    elif on_delete is SET or (callable(on_delete) and on_delete.__name__ == "SET"):
                        pass
                    else:
                        self.tracker.register_deleted(tracked)

    async def commit(self, connection: Any) -> None:
        """Async flush all tracked changes to the database within UOW."""
        for obj in list(self.tracker.deleted):
            self._handle_on_delete(obj, connection)

        for obj in self.tracker.new:
            await obj._async_execute_insert(connection)

        for obj in self.tracker.dirty:
            await obj._async_execute_update(connection)

        for obj in self.tracker.deleted:
            await obj._async_execute_delete(connection)

        await connection.commit()
        self.tracker.clear()

    async def rollback(self, connection: Any) -> None:
        await connection.rollback()
        self.tracker.clear()

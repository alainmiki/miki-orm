"""Tracks model instances for unit of work commit/rollback."""

from __future__ import annotations

from typing import Any


class UnitOfWorkTracker:
    def __init__(self) -> None:
        self.new: list[Any] = []
        self.dirty: list[Any] = []
        self.deleted: list[Any] = []

    def register_new(self, obj: Any) -> None:
        self.new.append(obj)

    def register_dirty(self, obj: Any) -> None:
        self.dirty.append(obj)

    def register_deleted(self, obj: Any) -> None:
        self.deleted.append(obj)

    def clear(self) -> None:
        self.new.clear()
        self.dirty.clear()
        self.deleted.clear()

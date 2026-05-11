"""Commit and rollback logic for unit of work."""

from __future__ import annotations

from typing import Any

from .tracker import UnitOfWorkTracker


class CommitManager:
    def __init__(self, tracker: UnitOfWorkTracker) -> None:
        self.tracker = tracker

    def commit(self, connection: Any) -> None:
        for obj in self.tracker.new:
            obj.save(connection)
        for obj in self.tracker.dirty:
            obj.save(connection)
        for obj in self.tracker.deleted:
            obj.delete(connection)
        connection.commit()
        self.tracker.clear()

    def rollback(self, connection: Any) -> None:
        connection.rollback()
        self.tracker.clear()

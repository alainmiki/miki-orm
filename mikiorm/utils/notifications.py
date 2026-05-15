"""Hook and event utilities for ORM lifecycle notifications."""

from __future__ import annotations

from typing import Any, Callable


class NotificationCenter:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = {}

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        self._listeners.setdefault(event_name, []).append(callback)

    def publish(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        for callback in self._listeners.get(event_name, []):
            callback(*args, **kwargs)

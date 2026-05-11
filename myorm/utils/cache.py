"""Cache helpers for query compilation and schema operations."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any


class LRUCache:
    def __init__(self, maxsize: int = 128, ttl: int | None = None) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: OrderedDict[str, tuple[Any, datetime | None]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        value = self._data.get(key)
        if not value:
            return None
        data, expires_at = value
        if expires_at and expires_at < datetime.utcnow():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return data

    def set(self, key: str, value: Any) -> None:
        expires_at = datetime.utcnow() + timedelta(seconds=self.ttl) if self.ttl else None
        self._data[key] = (value, expires_at)
        self._data.move_to_end(key)
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

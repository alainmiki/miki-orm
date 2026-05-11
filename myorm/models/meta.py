"""Meta options for model table names, indexes, and constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass
class MetaOptions:
    table_name: str | None = None
    indexes: list[Dict[str, Any]] = None
    constraints: list[Dict[str, Any]] = None
    ordering: list[str] = None
    abstract: bool = False
    managed: bool = True

    def __post_init__(self) -> None:
        self.indexes = self.indexes or []
        self.constraints = self.constraints or []
        self.ordering = self.ordering or []

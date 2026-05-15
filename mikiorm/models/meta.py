"""Meta options for model table names, indexes, and constraints.

Mirrors django.db.models.options.Options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class MetaOptions:
    table_name: str | None = None
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    ordering: List[str] = field(default_factory=list)
    abstract: bool = False
    managed: bool = True
    fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Safety: ensure no None values leaked in
        if self.indexes is None:
            self.indexes = []
        if self.constraints is None:
            self.constraints = []
        if self.ordering is None:
            self.ordering = []
        if self.fields is None:
            self.fields = {}
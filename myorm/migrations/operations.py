"""Migration operation definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MigrationOperation:
    operation_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.operation_type, "payload": self.payload}


@dataclass
class CreateTable(MigrationOperation):
    name: str
    columns: list[dict[str, Any]]

    def __init__(self, name: str, columns: list[dict[str, Any]]) -> None:
        super().__init__("create_table", {"name": name, "columns": columns})

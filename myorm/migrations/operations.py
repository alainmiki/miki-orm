"""Migration operation definitions.

These mirror django.db.migrations.operations for generating
and applying schema changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class AddField(MigrationOperation):
    """Add a field to an existing model."""

    model_name: str
    field: Any  # Field instance

    def __init__(self, model_name: str, field: Any) -> None:
        path, attr_name, args, kwargs = field.deconstruct()
        kwargs["name"] = attr_name
        payload = {
            "model_name": model_name,
            "field_type": path,
            "field_kwargs": kwargs,
        }
        super().__init__("add_field", payload)


@dataclass
class RemoveField(MigrationOperation):
    """Remove a field from a model."""

    model_name: str
    field_name: str

    def __init__(self, model_name: str, field_name: str) -> None:
        payload = {"model_name": model_name, "field_name": field_name}
        super().__init__("remove_field", payload)


@dataclass
class AlterField(MigrationOperation):
    """Alter an existing field's definition."""

    model_name: str
    field: Any  # New field instance

    def __init__(self, model_name: str, field: Any) -> None:
        path, attr_name, args, kwargs = field.deconstruct()
        kwargs["name"] = attr_name
        payload = {
            "model_name": model_name,
            "field_type": path,
            "field_kwargs": kwargs,
        }
        super().__init__("alter_field", payload)


@dataclass
class RenameField(MigrationOperation):
    """Rename a field on a model."""

    model_name: str
    old_name: str
    new_name: str

    def __init__(self, model_name: str, old_name: str, new_name: str) -> None:
        payload = {
            "model_name": model_name,
            "old_name": old_name,
            "new_name": new_name,
        }
        super().__init__("rename_field", payload)


@dataclass
class CreateIndex(MigrationOperation):
    """Create an index on a model's field(s)."""

    model_name: str
    index: dict[str, Any] = field(default_factory=dict)

    def __init__(self, model_name: str, index: dict[str, Any]) -> None:
        payload = {"model_name": model_name, "index": index}
        super().__init__("create_index", payload)


@dataclass
class AddIndex(MigrationOperation):
    """Add an index via Meta.indexes."""

    model_name: str
    index: dict[str, Any] = field(default_factory=dict)

    def __init__(self, model_name: str, index: dict[str, Any]) -> None:
        payload = {"model_name": model_name, "index": index}
        super().__init__("add_index", payload)


@dataclass
class RenameModel(MigrationOperation):
    """Rename a model."""

    old_name: str
    new_name: str

    def __init__(self, old_name: str, new_name: str) -> None:
        payload = {"old_name": old_name, "new_name": new_name}
        super().__init__("rename_model", payload)


@dataclass
class DeleteModel(MigrationOperation):
    """Delete a model entirely."""

    name: str

    def __init__(self, name: str) -> None:
        payload = {"name": name}
        super().__init__("delete_model", payload)


@dataclass
class AlterModelTable(MigrationOperation):
    """Change a model's db_table."""

    name: str
    table: str

    def __init__(self, name: str, table: str) -> None:
        payload = {"name": name, "table": table}
        super().__init__("alter_model_table", payload)
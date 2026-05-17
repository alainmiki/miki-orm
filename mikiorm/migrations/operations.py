"""Migration operation definitions.

These mirror django.db.migrations.operations for generating
and applying schema changes.
"""

from __future__ import annotations

from typing import Any


class MigrationOperation:
    operation_type: str
    payload: dict[str, Any]
    reverse_op: MigrationOperation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.operation_type, "payload": self.payload}


class CreateTable(MigrationOperation):
    """Create a new database table."""
    
    def __init__(self, name: str, columns: list[dict[str, Any]], 
                 reverse_op: "DeleteTable | None" = None) -> None:
        self.operation_type = "create_table"
        self.payload = {"name": name, "columns": columns}
        self.reverse_op = reverse_op or DeleteTable(name=name)


class DeleteTable(MigrationOperation):
    """Delete a database table - the reverse of CreateTable."""
    
    def __init__(self, name: str) -> None:
        self.operation_type = "delete_table"
        self.payload = {"name": name}


class AddField(MigrationOperation):
    """Add a field (column) to an existing model/table."""
    
    def __init__(self, model_name: str, field: Any) -> None:
        path, attr_name, args, kwargs = field.deconstruct()
        field_name = attr_name or field.name or ""
        self.field_name = field_name
        payload = {
            "model_name": model_name,
            "field_type": path,
            "field_name": field_name,
            "field_kwargs": kwargs,
            "field": field,  # Store the field object for schema editor
        }
        super().__init__()
        self.operation_type = "add_field"
        self.payload = payload
        # The reverse operation requires the field definition - store a copy
        self.reverse_op = RemoveField(model_name=model_name, field_name=field_name)


class RemoveField(MigrationOperation):
    """Remove a field (column) from a model/table."""
    
    def __init__(self, model_name: str, field_name: str) -> None:
        payload = {"model_name": model_name, "field_name": field_name}
        super().__init__()
        self.operation_type = "remove_field"
        self.payload = payload


# Compatibility alias for older naming
DropField = RemoveField


class AlterField(MigrationOperation):
    """Alter an existing field's definition."""
    
    def __init__(self, model_name: str, field: Any, old_field: Any | None = None) -> None:
        path, attr_name, args, kwargs = field.deconstruct()
        payload = {
            "model_name": model_name,
            "field_type": path,
            "field_name": attr_name,
            "field_kwargs": kwargs,
            "field": field,  # Store the field object for schema editor
        }
        if old_field:
            old_path, _, _, old_kwargs = old_field.deconstruct()
            payload.update({
                "old_field_type": old_path,
                "old_field_kwargs": old_kwargs,
                "old_field": old_field,
            })
        super().__init__()
        self.operation_type = "alter_field"
        self.payload = payload
        self.old_field = old_field
        # The reverse operation would restore old_field


class RenameField(MigrationOperation):
    """Rename a field on a model."""
    
    def __init__(self, model_name: str, old_name: str, new_name: str) -> None:
        payload = {
            "model_name": model_name,
            "old_name": old_name,
            "new_name": new_name,
        }
        super().__init__()
        self.operation_type = "rename_field"
        self.payload = payload
        self.reverse_op = RenameField(model_name=model_name, old_name=new_name, new_name=old_name)


class CreateIndex(MigrationOperation):
    """Create an index on a model's field(s)."""
    
    def __init__(self, model_name: str, index: dict[str, Any],
                 reverse_op: "DropIndex | None" = None) -> None:
        payload = {"model_name": model_name, "index": index}
        super().__init__()
        self.operation_type = "create_index"
        self.payload = payload
        self.reverse_op = reverse_op or DropIndex(
            model_name=model_name, 
            index_name=index.get("name", f"idx_{model_name}_{'_'.join(index.get('columns', []))}")
        )


class DropIndex(MigrationOperation):
    """Drop an index from a model."""
    
    def __init__(self, model_name: str, index_name: str) -> None:
        payload = {"model_name": model_name, "index_name": index_name}
        super().__init__()
        self.operation_type = "drop_index"
        self.payload = payload


class AddIndex(MigrationOperation):
    """Add an index via Meta.indexes - typically maps to CreateIndex."""
    
    def __init__(self, model_name: str, index: dict[str, Any]) -> None:
        payload = {"model_name": model_name, "index": index}
        super().__init__()
        self.operation_type = "add_index"
        self.payload = payload


class RenameModel(MigrationOperation):
    """Rename a model (table)."""
    
    def __init__(self, old_name: str, new_name: str) -> None:
        payload = {"old_name": old_name, "new_name": new_name}
        super().__init__()
        self.operation_type = "rename_model"
        self.payload = payload


class DeleteModel(MigrationOperation):
    """Delete a model entirely (drop table)."""
    
    def __init__(self, name: str) -> None:
        payload = {"name": name}
        super().__init__()
        self.operation_type = "delete_model"
        self.payload = payload

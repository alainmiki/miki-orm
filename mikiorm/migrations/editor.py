"""Schema editor - executes migration operations against a database.

Provides methods to safely apply schema changes: create/drop tables,
add/remove/alter columns, create/drop indexes. Handles backend-specific
SQL generation (SQLite, PostgreSQL, MySQL).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from . import operations
from ..query.safe_builder import get_safe_builder

logger = logging.getLogger(__name__)


class SchemaEditor:
    """Executes migration operations on a database connection."""

    def __init__(self, connection: Any, engine: str = "sqlite") -> None:
        self.connection = connection
        self.engine = engine.lower()
        self.builder = get_safe_builder(engine)

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> None:
        """Execute raw SQL."""
        logger.debug(f"Executing SQL: {sql} with params: {params}")
        self.connection.execute(sql, params or [])

    def add_create_table(self, table_name: str, columns: list) -> None:
        """Execute a CreateTable operation."""
        col_defs = []
        all_params = []

        for col_op in columns:
            # col_op is a tuple: (field_type, field_name, **attrs)
            if isinstance(col_op, tuple):
                ftype_or_obj = col_op[0]
                fname = col_op[1]
                attrs = col_op[2] if len(col_op) > 2 else {}

                # If first element is a field class, we need to reconstruct
                from mikiorm.models.fields import Field
                if isinstance(ftype_or_obj, type) and issubclass(ftype_or_obj, Field):
                    # Reconstruct field instance
                    from .engine import MigrationEngine as _ME
                    # Hand off to _sql_type_for_field
                    temp_field = ftype_or_obj(**attrs)
                    # We'll need a method to get SQL type; reuse MigrationEngine logic
                    sql_type = self._sql_type_for_field(temp_field)
                else:
                    # ftype_or_obj is the type string (fully qualified) - complicated
                    # For now just use attrs type hint
                    sql_type = attrs.pop("sql_type", "TEXT")

                # Build constraint list
                constraints = []
                if attrs.get("primary_key"):
                    constraints.append("PRIMARY KEY")
                    if attrs.get("auto_increment") or sql_type == "INTEGER":
                        constraints.append("AUTOINCREMENT")
                if attrs.get("null"):
                    constraints.append("NULL")
                else:
                    constraints.append("NOT NULL")
                if attrs.get("unique"):
                    constraints.append("UNIQUE")

                default = attrs.get("default")
                col_def = f"    {self.builder.quote_column(fname)} {sql_type} {' '.join(constraints)}"
                if default is not None:
                    col_def += " DEFAULT ?"
                    all_params.append(default)

                col_defs.append(col_def)
            else:
                logger.warning(f"Unknown column spec format: {col_op}")

        sql = f"CREATE TABLE IF NOT EXISTS {self.builder.quote_table(table_name)} (\n{',\n'.join(col_defs)}\n)"
        self.execute(sql, all_params)

    def add_field(self, model_name: str, field_op) -> None:
        """Add a column to an existing table."""
        # field_op should be an AddField operation with payload
        if isinstance(field_op, operations.AddField):
            field_type = field_op.payload["field_type"]
            field_name = field_op.payload.get("name", "")
            kwargs = {k: v for k, v in field_op.payload.items() if k not in ("model_name", "field_type", "name")}

            # Import field class instantiate to get SQL type
            import importlib
            mod_path, class_name = field_type.rsplit(".", 1)
            mod = importlib.import_module(mod_path)
            field_cls = getattr(mod, class_name)
            field_inst = field_cls(**kwargs)

            sql_type = self._sql_type_for_field(field_inst)

            constraints = []
            if kwargs.get("primary_key"):
                constraints.append("PRIMARY KEY")
            if kwargs.get("null"):
                constraints.append("NULL")
            else:
                constraints.append("NOT NULL")
            if kwargs.get("unique"):
                constraints.append("UNIQUE")

            default = kwargs.get("default")
            col_def = f"{self.builder.quote_column(field_name)} {sql_type} {' '.join(constraints)}"
            if default is not None:
                col_def += " DEFAULT ?"
                self.execute(f"ALTER TABLE {self.builder.quote_table(model_name)} ADD COLUMN {col_def}", [default])
            else:
                self.execute(f"ALTER TABLE {self.builder.quote_table(model_name)} ADD COLUMN {col_def}")

    def remove_field(self, model_name: str, field_name: str) -> None:
        """Remove a column from a table. (Some DBs don't support DROP COLUMN)."""
        # SQLite doesn't support DROP COLUMN easily; we'd need to recreate table
        # For now, log a warning
        logger.warning(f"DROP COLUMN not fully supported on {self.engine} - may require table rebuild")

    def alter_field(self, model_name: str, field_op) -> None:
        """Alter a column's definition."""
        # This is complex: often requires table rebuild
        logger.warning(f"ALTER COLUMN not fully implemented for {self.engine}")

    def create_index(self, model_name: str, columns: list[str], unique: bool = False) -> None:
        """Create an index on one or more columns."""
        idx_name = f"idx_{model_name}_{'_'.join(columns)}"
        quoted_cols = [self.builder.quote_column(c) for c in columns]
        quoted_table = self.builder.quote_table(model_name)
        uniq = "UNIQUE" if unique else ""
        sql = f"CREATE {uniq} INDEX {idx_name} ON {quoted_table} ({', '.join(quoted_cols)})"
        self.execute(sql, [])

    def drop_index(self, model_name: str, index_name: str) -> None:
        """Drop an index."""
        self.execute(f"DROP INDEX {index_name} ON {self.builder.quote_table(model_name)}", [])

    def _sql_type_for_field(self, field: Any) -> str:
        """Generate SQL column type for a field instance."""
        from mikiorm.models.fields import (
            IntegerField, BigIntegerField, SmallIntegerField,
            PositiveIntegerField, PositiveSmallIntegerField,
            AutoField, BigAutoField, SmallAutoField,
            CharField, TextField, BooleanField,
            DecimalField, FloatField, DurationField,
            DateTimeField, DateField, TimeField,
            UUIDField, JSONField, BinaryField,
            EmailField, URLField, SlugField,
            GenericIPAddressField, FilePathField,
        )

        if isinstance(field, (IntegerField, AutoField, SmallAutoField,
                              PositiveIntegerField, PositiveSmallIntegerField)):
            return "INTEGER"
        if isinstance(field, BigIntegerField):
            return "BIGINT"
        if isinstance(field, BigAutoField):
            return "BIGINT"
        if isinstance(field, CharField):
            ml = field.max_length or 255
            return f"VARCHAR({ml})"
        if isinstance(field, TextField):
            return "TEXT"
        if isinstance(field, BooleanField):
            return "BOOLEAN"
        if isinstance(field, DecimalField):
            return f"DECIMAL({field.max_digits}, {field.decimal_places})"
        if isinstance(field, FloatField):
            return "FLOAT"
        if isinstance(field, DurationField):
            return "BIGINT"
        if isinstance(field, DateTimeField):
            return "DATETIME"
        if isinstance(field, DateField):
            return "DATE"
        if isinstance(field, TimeField):
            return "TIME"
        if isinstance(field, UUIDField):
            return "VARCHAR(36)"
        if isinstance(field, JSONField):
            return "TEXT"
        if isinstance(field, BinaryField):
            return "BLOB"
        if isinstance(field, EmailField):
            ml = field.max_length or 254
            return f"VARCHAR({ml})"
        if isinstance(field, URLField):
            ml = field.max_length or 200
            return f"VARCHAR({ml})"
        if isinstance(field, SlugField):
            ml = field.max_length or 50
            return f"VARCHAR({ml})"
        if isinstance(field, GenericIPAddressField):
            return "VARCHAR(45)"
        if isinstance(field, FilePathField):
            return "VARCHAR(255)"

        return "TEXT"


# Factory function
def get_schema_editor(connection: Any, engine: str = "sqlite") -> SchemaEditor:
    return SchemaEditor(connection, engine)


class CollectingSchemaEditor(SchemaEditor):
    """A mock SchemaEditor that collects operations instead of executing them."""

    def __init__(self):
        # Pass dummy connection and builder, as we won't execute SQL
        # We need a valid builder for deconstruction, so let's use a default one.
        from mikiorm.query.safe_builder import get_safe_builder
        from mikiorm.settings import settings

        db_config = settings.databases.get("default")
        engine = db_config.engine if db_config else "sqlite"
        super().__init__(
            connection=None, engine=engine
        )  # Pass a dummy connection, but a real builder
        self.collected_operations = []

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> None:
        """Override execute to do nothing, as we are collecting."""
        pass

    def execute_operation(self, op: operations.MigrationOperation) -> None:
        """Collects the migration operation."""
        self.collected_operations.append(op)

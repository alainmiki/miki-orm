"""SQLite schema editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from mikiorm.backends.base.schema import BaseSchemaEditor
from mikiorm.query import get_safe_builder

if TYPE_CHECKING:
    from mikiorm.backends.base.adapter import BaseConnection
    from mikiorm.models.base import Model
    from mikiorm.models.fields import Field


class SQLiteSchemaEditor(BaseSchemaEditor):
    """Schema editor for SQLite databases."""

    sql_create_table = "CREATE TABLE {table} ({columns})"
    sql_create_column = "ALTER TABLE {table} ADD COLUMN {column}"
    sql_alter_column = "ALTER TABLE {table} ALTER COLUMN {column}"  # Not fully supported by SQLite
    sql_drop_column = "ALTER TABLE {table} DROP COLUMN {column}"  # Not fully supported by SQLite
    sql_rename_table = "ALTER TABLE {old_table} RENAME TO {new_table}"
    sql_drop_table = "DROP TABLE {table}"
    sql_create_index = "CREATE INDEX {name} ON {table} ({columns})"
    sql_drop_index = "DROP INDEX {name}"

    def __init__(self, connection: BaseConnection):
        super().__init__(connection)
        self.builder = get_safe_builder("sqlite")

    def _column_def(self, field: Field, *, for_alter: bool = False) -> tuple[str, list]:
        """Return (column_sql, params) compatible with the migration engine."""
        # Build the field-type portion; _safe_default_literal handles quoting.
        from mikiorm.backends.base.schema_editor import (
            field_to_sql_type,
            _safe_default_literal,
        )
        from mikiorm.backends.base.dialect import Dialect

        col_name = self.builder.quote_column(field.name)
        sql_type = field_to_sql_type(field, Dialect.SQLITE)
        parts: list[str] = [col_name, sql_type]
        params: list = []

        is_auto_pk = getattr(field, "auto_created", False) and field.primary_key
        if is_auto_pk:
            parts.append("PRIMARY KEY AUTOINCREMENT")
        elif field.primary_key:
            parts.append("PRIMARY KEY")

        if not is_auto_pk:
            parts.append("NULL" if field.null else "NOT NULL")

        if field.unique and not field.primary_key:
            parts.append("UNIQUE")

        default = getattr(field, "default", None)
        if default is not None and not callable(default) and not is_auto_pk:
            parts.append(f"DEFAULT {_safe_default_literal(default)}")

        return " ".join(parts), params

    def column_sql(self, model: Type[Model], field: Field, include_default: bool = True) -> str:
        """Generates the SQL for a column definition."""
        from mikiorm.backends.base.schema_editor import field_to_sql_type
        from mikiorm.backends.base.dialect import Dialect

        field_type = field_to_sql_type(field, Dialect.SQLITE)
        constraints = [field_type]

        if field.primary_key:
            constraints.append("PRIMARY KEY")
            if field.auto_created:  # Assuming AutoField
                constraints.append("AUTOINCREMENT")
        else:
            if field.unique:
                constraints.append("UNIQUE")
            if not field.null:
                constraints.append("NOT NULL")
            if include_default and field.has_default():
                default = field.get_default()
                if isinstance(default, str):
                    default = f"'{default}'"
                constraints.append(f"DEFAULT {default}")

        field_name = field.name or getattr(field, "column", "")
        return f"{self.builder.quote_column(field_name)} {' '.join(constraints)}"

    def create_model(self, model: Type[Model]) -> None:
        """Creates a table for the given model."""
        table_name = self.builder.quote_table(model._meta.table_name)
        columns: list[str] = []
        for field in model._meta.fields:
            columns.append(self.column_sql(model, field))

        # Add foreign key constraints
        for field in model._meta.fields:
            if field.is_relation and field.many_to_one:
                fk_target_table = self.builder.quote_table(field.related_model._meta.table_name)
                fk_target_column = self.builder.quote_column(
                    field.related_model._meta.pk.column
                )
                columns.append(
                    f"FOREIGN KEY ({self.builder.quote_column(field.column)}) "
                    f"REFERENCES {fk_target_table} ({fk_target_column}) "
                    f"{self.sql_on_delete(field.on_delete)}"
                )

        sql = self.sql_create_table.format(table=table_name, columns=", ".join(columns))
        self.connection.execute(sql)
        self.connection.commit()

    def add_field(self, model: Type[Model], field: Field) -> None:
        """Adds a column to an existing table."""
        # SQLite has limited ALTER TABLE support. Adding a column is generally fine.
        table_name = self.builder.quote_table(model._meta.table_name)
        column_sql = self.column_sql(model, field, include_default=True)
        sql = self.sql_create_column.format(table=table_name, column=column_sql)
        self.connection.execute(sql)
        self.connection.commit()

    def rename_field(self, model: Type[Model], old_name: str, new_name: str) -> None:
        """Rename a column on the model's table."""
        table_name = self.builder.quote_table(model._meta.table_name)
        old_col = self.builder.quote_column(old_name)
        new_col = self.builder.quote_column(new_name)
        sql = f"ALTER TABLE {table_name} RENAME COLUMN {old_col} TO {new_col}"
        self.connection.execute(sql)
        self.connection.commit()

    def remove_field(self, model: Type[Model], field: Field) -> None:
        """Removes a column from an existing table."""
        # SQLite does not support DROP COLUMN directly. Implement table rebuild.
        table_name = model._meta.table_name
        quoted_table_name = self.builder.quote_table(table_name)
        temp_table_name = f"{table_name}_tmp"
        quoted_temp_table_name = self.builder.quote_table(temp_table_name)

        # Use introspection to identify indexes to preserve (exclude those on the dropped column)
        from mikiorm.backends.sqlite.introspection import SQLiteIntrospection
        introspector = SQLiteIntrospection(self.connection)
        all_indexes = introspector.get_indexes(table_name)
        preserved_indexes = [
            idx for idx in all_indexes if field.column not in idx["columns"]
        ]

        # Get all fields except the one being removed
        remaining_fields = [f for f in model._meta.fields if f.column != field.column]
        remaining_columns = [
            self.builder.quote_column(f.column) for f in remaining_fields
        ]

        try:
            # Get original table creation statement
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Table {table_name} not found")

            original_create_sql = result[0]

            # Create temporary table with remaining fields
            columns = []
            for field_obj in remaining_fields:
                columns.append(self.column_sql(model, field_obj))

            # Add foreign key constraints for remaining fields
            for field_obj in remaining_fields:
                if field_obj.is_relation and field_obj.many_to_one:
                    fk_target_table = self.builder.quote_table(field_obj.related_model._meta.table_name)
                    fk_target_column = self.builder.quote_column(
                        field_obj.related_model._meta.pk.column
                    )
                    columns.append(
                        f"FOREIGN KEY ({self.builder.quote_column(field_obj.column)}) "
                        f"REFERENCES {fk_target_table} ({fk_target_column}) "
                        f"{self.sql_on_delete(field_obj.on_delete)}"
                    )

            create_temp_sql = f"CREATE TABLE {quoted_temp_table_name} ({', '.join(columns)})"

            # Create temporary table
            self.connection.execute(create_temp_sql)

            # Copy data from original table to temporary table
            copy_sql = f"INSERT INTO {quoted_temp_table_name} ({', '.join(remaining_columns)}) SELECT {', '.join(remaining_columns)} FROM {quoted_table_name}"
            self.connection.execute(copy_sql)

            # Drop original table
            self.connection.execute(f"DROP TABLE {quoted_table_name}")

            # Rename temporary table to original name
            self.connection.execute(f"ALTER TABLE {quoted_temp_table_name} RENAME TO {quoted_table_name}")

            # Re-create preserved indexes
            for idx in preserved_indexes:
                unique = "UNIQUE " if idx["unique"] else ""
                cols = ", ".join(self.builder.quote_column(c) for c in idx["columns"])
                self.connection.execute(
                    f"CREATE {unique}INDEX {self.builder.quote_column(idx['name'])} "
                    f"ON {quoted_table_name} ({cols})"
                )

            self.connection.commit()

        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Failed to remove field {field.column} from table {table_name}: {str(e)}")

    def alter_field(self, model: Type[Model], old_field: Field, new_field: Field) -> None:
        """
        Alters a field on a table. SQLite doesn't support ALTER COLUMN,
        so we perform a table rebuild.
        """
        table_name = model._meta.table_name
        quoted_table_name = self.builder.quote_table(table_name)
        temp_table_name = f"{table_name}_alter_tmp"
        quoted_temp_table_name = self.builder.quote_table(temp_table_name)

        # Use introspection to identify indexes to preserve
        from mikiorm.backends.sqlite.introspection import SQLiteIntrospection
        introspector = SQLiteIntrospection(self.connection)
        all_indexes = introspector.get_indexes(table_name)

        # Get all fields with their current definitions (new_field should be in model._meta.fields)
        fields = model._meta.fields

        # If the shim model has no fields (migration shim), introspect the
        # current table structure and synthesize lightweight field objects
        # sufficient for rebuilding the table.
        if not fields:
            from types import SimpleNamespace
            from mikiorm.backends.sqlite.introspection import SQLiteIntrospection

            introspector = SQLiteIntrospection(self.connection)
            cols = introspector.get_columns(table_name)
            synth: list[SimpleNamespace] = []
            for col in cols:
                fn = SimpleNamespace()
                fn.name = col["name"]
                fn.column = col["name"]
                fn.primary_key = col.get("primary_key", False)
                fn.null = col.get("null", True)
                fn.unique = col.get("unique", False)
                fn.default = col.get("default", None)
                fn.is_relation = False
                fn.many_to_one = False
                fn.on_delete = None
                fn.auto_created = fn.primary_key and str(
                    col.get("type", "")
                ).upper().startswith("INT")

                def has_default(self=fn):
                    return self.default is not None

                def get_default(self=fn):
                    return self.default

                fn.has_default = has_default
                fn.get_default = get_default
                synth.append(fn)

            # Append the new_field if it's not present in introspection
            new_name = getattr(new_field, "name", None)
            if new_name and new_name not in [c.name for c in synth]:
                # Ensure new_field has `column` attr
                if not hasattr(new_field, "column"):
                    setattr(
                        new_field, "column", getattr(new_field, "db_column", new_name)
                    )
                synth.append(new_field)

            fields = synth
        columns = []
        for field_obj in fields:
            columns.append(self.column_sql(model, field_obj))

        # Add foreign key constraints
        for field_obj in fields:
            if field_obj.is_relation and field_obj.many_to_one:
                fk_target_table = self.builder.quote_table(field_obj.related_model._meta.table_name)
                fk_target_column = self.builder.quote_column(
                    field_obj.related_model._meta.pk.column
                )
                columns.append(
                    f"FOREIGN KEY ({self.builder.quote_column(field_obj.column)}) "
                    f"REFERENCES {fk_target_table} ({fk_target_column}) "
                    f"{self.sql_on_delete(field_obj.on_delete)}"
                )

        create_temp_sql = f"CREATE TABLE {quoted_temp_table_name} ({', '.join(columns)})"

        # Prepare data copy columns (handle mapping from old column name to new if changed)
        new_cols = [self.builder.quote_column(f.column) for f in fields]
        old_cols = []
        for f in fields:
            if f.name == new_field.name:
                old_cols.append(self.builder.quote_column(old_field.column))
            else:
                old_cols.append(self.builder.quote_column(f.column))

        try:
            self.connection.execute(create_temp_sql)
            copy_sql = f"INSERT INTO {quoted_temp_table_name} ({', '.join(new_cols)}) SELECT {', '.join(old_cols)} FROM {quoted_table_name}"
            self.connection.execute(copy_sql)
            self.connection.execute(f"DROP TABLE {quoted_table_name}")
            self.connection.execute(f"ALTER TABLE {quoted_temp_table_name} RENAME TO {quoted_table_name}")

            # Restore indexes, updating column references if the field name changed
            for idx in all_indexes:
                unique = "UNIQUE " if idx["unique"] else ""
                idx_cols = ", ".join(
                    (
                        self.builder.quote_column(c)
                        if c != old_field.column
                        else self.builder.quote_column(new_field.column)
                    )
                    for c in idx["columns"]
                )
                self.connection.execute(
                    f"CREATE {unique}INDEX {self.builder.quote_column(idx['name'])} ON {quoted_table_name} ({idx_cols})"
                )
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Failed to alter field {new_field.column} in table {table_name}: {str(e)}")

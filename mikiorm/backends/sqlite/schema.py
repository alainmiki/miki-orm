"""SQLite schema editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from mikiorm.backends.base.schema import BaseSchemaEditor
from mikiorm.query.safe_builder import get_safe_builder

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

    def column_sql(self, model: Type[Model], field: Field, include_default: bool = True) -> str:
        """Generates the SQL for a column definition."""
        field_type = field.db_type(self.connection)
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

        return f"{self.builder.quote_name(field.column)} {' '.join(constraints)}"

    def create_model(self, model: Type[Model]) -> None:
        """Creates a table for the given model."""
        table_name = self.builder.quote_table(model._meta.table_name)
        columns = []
        for field in model._meta.fields:
            columns.append(self.column_sql(model, field))

        # Add foreign key constraints
        for field in model._meta.fields:
            if field.is_relation and field.many_to_one:
                fk_target_table = self.builder.quote_table(field.related_model._meta.table_name)
                fk_target_column = self.builder.quote_name(field.related_model._meta.pk.column)
                columns.append(
                    f"FOREIGN KEY ({self.builder.quote_name(field.column)}) "
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
        remaining_columns = [self.builder.quote_name(f.column) for f in remaining_fields]
        
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
                    fk_target_column = self.builder.quote_name(field_obj.related_model._meta.pk.column)
                    columns.append(
                        f"FOREIGN KEY ({self.builder.quote_name(field_obj.column)}) "
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
                cols = ", ".join(self.builder.quote_name(c) for c in idx["columns"])
                self.connection.execute(
                    f"CREATE {unique}INDEX {self.builder.quote_name(idx['name'])} "
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
        columns = []
        for field_obj in fields:
            columns.append(self.column_sql(model, field_obj))

        # Add foreign key constraints
        for field_obj in fields:
            if field_obj.is_relation and field_obj.many_to_one:
                fk_target_table = self.builder.quote_table(field_obj.related_model._meta.table_name)
                fk_target_column = self.builder.quote_name(field_obj.related_model._meta.pk.column)
                columns.append(
                    f"FOREIGN KEY ({self.builder.quote_name(field_obj.column)}) "
                    f"REFERENCES {fk_target_table} ({fk_target_column}) "
                    f"{self.sql_on_delete(field_obj.on_delete)}"
                )

        create_temp_sql = f"CREATE TABLE {quoted_temp_table_name} ({', '.join(columns)})"
        
        # Prepare data copy columns (handle mapping from old column name to new if changed)
        new_cols = [self.builder.quote_name(f.column) for f in fields]
        old_cols = []
        for f in fields:
            if f.name == new_field.name:
                old_cols.append(self.builder.quote_name(old_field.column))
            else:
                old_cols.append(self.builder.quote_name(f.column))

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
                    self.builder.quote_name(c) if c != old_field.column else self.builder.quote_name(new_field.column) 
                    for c in idx["columns"]
                )
                self.connection.execute(
                    f"CREATE {unique}INDEX {self.builder.quote_name(idx['name'])} ON {quoted_table_name} ({idx_cols})"
                )
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Failed to alter field {new_field.column} in table {table_name}: {str(e)}")
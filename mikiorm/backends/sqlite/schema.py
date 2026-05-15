"""SQLite schema editor for migrations."""

from __future__ import annotations

from typing import Any, Optional

from mikiorm.query.safe_builder import SafeBuilder


class DatabaseSchemaEditor:
    """Encapsulates SQL schema editing for SQLite."""

    sql_create_table = "CREATE TABLE {table} ({definition})"
    sql_create_table_unique = "CREATE UNIQUE INDEX {name} ON {table} ({columns})"
    sql_delete_table = "DROP TABLE {table}"
    sql_delete_unique = "DROP INDEX {name}"
    
    def __init__(self, connection: Any, collect_sql: bool = False, atomic: bool = True) -> None:
        self.connection = connection
        self.collect_sql = collect_sql
        self.atomic = atomic
        self.builder = SafeBuilder()
        self._sql_statements: list[str] = []

    def _execute(self, sql: str, params: tuple = ()) -> None:
        """Execute SQL statement."""
        if self.collect_sql:
            self._sql_statements.append(sql)
        else:
            if params:
                self.connection.execute(sql, params)
            else:
                self.connection.execute(sql)

    def quote_value(self, value: Any) -> str:
        """Quote a value for SQL."""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            return f"'{value}'"
        elif isinstance(value, bool):
            return "1" if value else "0"
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            return f"'{str(value)}'"

    def column_sql(self, model: Any, field: Any) -> str:
        """Return the SQL for a column definition."""
        name = self.builder.quote_column(field.name)
        
        # Map field types to SQLite column types
        field_type_map = {
            'AutoField': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'IntegerField': 'INTEGER',
            'BigIntegerField': 'BIGINT',
            'SmallIntegerField': 'SMALLINT',
            'PositiveIntegerField': 'INTEGER',
            'PositiveSmallIntegerField': 'SMALLINT',
            'FloatField': 'REAL',
            'DoubleField': 'REAL',
            'DecimalField': 'DECIMAL(10,5)',
            'CharField': f'VARCHAR({field.max_length or 255})',
            'TextField': 'TEXT',
            'BooleanField': 'INTEGER',
            'DateField': 'DATE',
            'DateTimeField': 'DATETIME',
            'TimeField': 'TIME',
            'UUIDField': 'VARCHAR(36)',
            'JSONField': 'TEXT',
            'BinaryField': 'BLOB',
            'ForeignKey': 'INTEGER',
        }
        
        sql_type = field_type_map.get(field.__class__.__name__, 'TEXT')
        
        # Add constraints
        if field.primary_key:
            sql_type += ' PRIMARY KEY'
        if not field.null:
            sql_type += ' NOT NULL'
        if field.unique:
            sql_type += ' UNIQUE'
        if field.default is not None and not callable(field.default):
            sql_type += f" DEFAULT {self.quote_value(field.default)}"
        
        return f"{name} {sql_type}"

    def create_model(self, model: Any) -> None:
        """Create a table for the model."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        
        columns = []
        for field_name, field in model._meta.fields.items():
            columns.append(self.column_sql(model, field))
        
        columns.append("version INTEGER NOT NULL DEFAULT 1")
        
        definition = ", ".join(columns)
        sql = self.sql_create_table.format(table=table, definition=definition)
        
        self._execute(sql)

    def delete_model(self, model: Any) -> None:
        """Drop the table for the model."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        sql = self.sql_delete_table.format(table=table)
        self._execute(sql)

    def add_field(self, model: Any, field: Any) -> None:
        """Add a field to a model's table."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        column_sql = self.column_sql(model, field)
        
        # SQLite requires a full table rebuild for adding columns
        sql = f"ALTER TABLE {table} ADD COLUMN {column_sql}"
        self._execute(sql)

    def remove_field(self, model: Any, field: Any) -> None:
        """Remove a field from a model's table (requires table rebuild)."""
        # SQLite doesn't support DROP COLUMN directly
        raise NotImplementedError(
            "SQLite doesn't support DROP COLUMN directly. "
            "Use a migration tool that handles table rebuilds."
        )

    def alter_field(self, model: Any, old_field: Any, new_field: Any) -> None:
        """Alter a field in a model's table (requires table rebuild in SQLite)."""
        # SQLite has limited ALTER TABLE support
        pass

    def create_index(self, model: Any, fields: list, name: str, unique: bool = False) -> None:
        """Create an index."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        columns = ", ".join(self.builder.quote_column(f.name) for f in fields)
        
        if unique:
            sql = self.sql_create_table_unique.format(
                name=self.builder.quote_column(name),
                table=table,
                columns=columns,
            )
        else:
            sql = f"CREATE INDEX {self.builder.quote_column(name)} ON {table} ({columns})"
        
        self._execute(sql)

    def delete_index(self, model: Any, name: str) -> None:
        """Delete an index."""
        sql = self.sql_delete_unique.format(name=self.builder.quote_column(name))
        self._execute(sql)

    def table_sql(self, model: Any) -> str:
        """Return the SQL to create the table."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        
        columns = []
        for field_name, field in model._meta.fields.items():
            columns.append(self.column_sql(model, field))
        
        definition = ", ".join(columns)
        return self.sql_create_table.format(table=table, definition=definition)
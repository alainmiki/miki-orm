"""MySQL schema editor for migrations."""

from __future__ import annotations

from typing import Any, Optional, Type

from mikiorm.query import SafeBuilder, Dialect
from mikiorm.backends.base.schema import BaseSchemaEditor


class DatabaseSchemaEditor(BaseSchemaEditor):
    """Encapsulates SQL schema editing for MySQL."""

    sql_create_table = "CREATE TABLE {table} ({definition}){extra}"
    sql_create_table_unique = "CREATE UNIQUE INDEX {name} ON {table} ({columns})"
    sql_delete_table = "DROP TABLE {table}"
    sql_delete_unique = "DROP INDEX {name} ON {table}"
    sql_rename_table = "RENAME TABLE {old_table} TO {new_table}"
    
    def __init__(self, connection: Any, collect_sql: bool = False, atomic: bool = True) -> None:
        super().__init__(connection)
        self.collect_sql = collect_sql
        self.atomic = atomic
        self.builder = SafeBuilder(Dialect.MYSQL)
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
        
        field_type_map = {
            'AutoField': 'INT AUTO_INCREMENT PRIMARY KEY',
            'IntegerField': 'INT',
            'BigIntegerField': 'BIGINT',
            'SmallIntegerField': 'SMALLINT',
            'PositiveIntegerField': 'INT UNSIGNED',
            'PositiveSmallIntegerField': 'SMALLINT UNSIGNED',
            'FloatField': 'FLOAT',
            'DoubleField': 'DOUBLE',
            'DecimalField': 'DECIMAL({max_digits},{decimal_places})'.format(
                max_digits=field.max_digits, decimal_places=field.decimal_places
            ),
            'CharField': 'VARCHAR({max_length})'.format(max_length=field.max_length or 255),
            'TextField': 'LONGTEXT',
            'BooleanField': 'TINYINT(1)',
            'DateField': 'DATE',
            'DateTimeField': 'DATETIME',
            'TimeField': 'TIME',
            'UUIDField': 'VARCHAR(36)',
            'JSONField': 'JSON',
            'BinaryField': 'LONGBLOB',
            'ForeignKey': 'INT',
        }
        
        sql_type = field_type_map.get(field.__class__.__name__, 'TEXT')
        
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
        
        columns.append("version INT NOT NULL DEFAULT 1")
        
        definition = ", ".join(columns)
        sql = self.sql_create_table.format(table=table, definition=definition, extra="")
        
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
        
        sql = f"ALTER TABLE {table} ADD COLUMN {column_sql}"
        self._execute(sql)

    def remove_field(self, model: Any, field: Any) -> None:
        """Remove a field from a model's table."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        column = self.builder.quote_column(field.name)
        
        # MySQL 8.0+ supports DROP COLUMN
        sql = f"ALTER TABLE {table} DROP COLUMN {column}"
        self._execute(sql)

    def alter_field(self, model: Any, old_field: Any, new_field: Any) -> None:
        """Alter a field in a model's table."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        column = self.builder.quote_column(new_field.name)
        
        new_type = self._get_field_type(new_field)
        
        sql = f"ALTER TABLE {table} MODIFY COLUMN {column} {new_type}"
        self._execute(sql)

    def _get_field_type(self, field: Any) -> str:
        """Get MySQL type for field."""
        field_type_map = {
            'AutoField': 'INT AUTO_INCREMENT',
            'IntegerField': 'INT',
            'BigIntegerField': 'BIGINT',
            'SmallIntegerField': 'SMALLINT',
            'FloatField': 'FLOAT',
            'DoubleField': 'DOUBLE',
            'DecimalField': f'DECIMAL({field.max_digits},{field.decimal_places})',
            'CharField': f'VARCHAR({field.max_length or 255})',
            'TextField': 'LONGTEXT',
            'BooleanField': 'TINYINT(1)',
            'DateField': 'DATE',
            'DateTimeField': 'DATETIME',
            'UUIDField': 'VARCHAR(36)',
            'JSONField': 'JSON',
            'BinaryField': 'LONGBLOB',
        }
        return field_type_map.get(field.__class__.__name__, 'TEXT')

    def create_index(self, model: Any, fields: list[Any], name: str, unique: bool = False) -> None:
        """Create an index."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        columns = ", ".join(self.builder.quote_column(f.column if hasattr(f, 'column') else f.name) for f in fields)
        
        if unique:
            sql = f"CREATE UNIQUE INDEX {self.builder.quote_column(name)} ON {table} ({columns})"
        else:
            sql = f"CREATE INDEX {self.builder.quote_column(name)} ON {table} ({columns})"
        
        self._execute(sql)

    def drop_index(self, model: Any, name: str) -> None:
        """Drop an index."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        sql = self.sql_delete_unique.format(name=self.builder.quote_column(name), table=table)
        self._execute(sql)

    def rename_table(self, model: Any, new_name: str) -> None:
        """Rename a table."""
        table = self.builder.quote_table(model._meta.table_name or model.__name__.lower() + 's')
        new_table = self.builder.quote_table(new_name)
        sql = self.sql_rename_table.format(old_table=table, new_table=new_table)
        self._execute(sql)
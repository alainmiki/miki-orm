"""MySQL database introspection utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mikiorm.query import SafeBuilder


class DatabaseIntrospection:
    """Encapsulates introspection methods for MySQL."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.builder = SafeBuilder()

    def get_table_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of table names in the database."""
        sql = """
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_type = 'BASE TABLE'
        """
        if cursor is None:
            cursor = self.connection.execute(sql, ())
        rows = cursor.fetchall()
        return [{"name": row[0]} for row in rows]

    def get_table_description(self, table_name: str) -> List[Dict[str, Any]]:
        """Return a description of the table columns."""
        sql = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                column_key
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
        """
        rows = self.connection.fetchall(sql, (table_name,))
        
        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "primary_key": row[4] == "PRI",
            }
            for row in rows
        ]

    def get_relations(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of foreign key relations."""
        sql = """
            SELECT
                k.table_name,
                k.column_name,
                k.referenced_table_name,
                k.referenced_column_name
            FROM information_schema.key_column_usage k
            WHERE k.table_schema = DATABASE()
            AND k.referenced_table_name IS NOT NULL
        """
        rows = cursor.fetchall() if cursor else self.connection.fetchall(sql, ())
        
        return [
            {
                "table_name": row[0],
                "column": row[1],
                "foreign_table": row[2],
                "foreign_column": row[3],
            }
            for row in rows
        ]

    def get_key_columns(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of columns that are foreign keys."""
        return self.get_relations(cursor)

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Return a list of indexes for the table."""
        sql = f"SHOW INDEX FROM {self.builder.quote_table(table_name)}"
        rows = self.connection.fetchall(sql, ())
        
        indexes = {}
        for row in rows:
            index_name = row[2]
            if index_name not in indexes:
                indexes[index_name] = {
                    "name": index_name,
                    "columns": [],
                    "unique": not bool(row[1]),  # Non_unique = 0 means unique
                }
            indexes[index_name]["columns"].append(row[4])
        
        return list(indexes.values())

    def get_schema_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return list of schemas (databases)."""
        sql = "SELECT schema_name FROM information_schema.schemata"
        rows = cursor.fetchall() if cursor else self.connection.fetchall(sql, ())
        return [{"name": row[0]} for row in rows]

    def table_exists(self, table_name: str, cursor: Any = None) -> bool:
        """Check if a table exists."""
        sql = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s"
        row = self.connection.fetchone(sql, (table_name,))
        return bool(row[0]) if row else False

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table."""
        sql = """
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
        """
        row = self.connection.fetchone(sql, (table_name, column_name))
        return bool(row[0]) if row else False
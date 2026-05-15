"""SQLite database introspection utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mikiorm.query.safe_builder import SafeBuilder


class DatabaseIntrospection:
    """Encapsulates introspection methods for SQLite."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.builder = SafeBuilder()

    def get_table_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of table names in the database."""
        cursor = cursor or self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        rows = cursor.fetchall()
        return [{"name": row[0]} for row in rows]

    def get_table_description(self, table_name: str) -> List[Dict[str, Any]]:
        """Return a description of the table columns."""
        cursor = self.connection.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall()
        
        return [
            {
                "name": row[1],
                "type": row[2],
                "nullable": not bool(row[3]),
                "default": row[4],
                "primary_key": bool(row[5]),
            }
            for row in rows
        ]

    def get_relations(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of foreign key relations."""
        # SQLite doesn't have a simple way to get all relations
        # We need to query each table's foreign keys
        tables = self.get_table_list()
        relations = []
        
        for table in tables:
            table_name = table["name"]
            cursor = self.connection.execute(f"PRAGMA foreign_key_list({table_name})")
            fk_rows = cursor.fetchall()
            
            for fk_row in fk_rows:
                relations.append({
                    "table_name": table_name,
                    "column": fk_row[3],
                    "foreign_table": fk_row[2],
                    "foreign_column": fk_row[4],
                })
        
        return relations

    def get_key_columns(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of columns that are foreign keys."""
        return self.get_relations(cursor)

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Return a list of indexes for the table."""
        cursor = self.connection.execute(f"PRAGMA index_list({table_name})")
        rows = cursor.fetchall()
        
        indexes = []
        for row in rows:
            index_name = row[1]
            cursor2 = self.connection.execute(f"PRAGMA index_info({index_name})")
            index_info = cursor2.fetchall()
            
            indexes.append({
                "name": index_name,
                "columns": [info[2] for info in index_info],
                "unique": bool(row[2]),
            })
        
        return indexes

    def get_schema_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return schema list (SQLite uses 'main' as default schema)."""
        return [{"name": "main"}]

    def table_exists(self, table_name: str, cursor: Any = None) -> bool:
        """Check if a table exists."""
        cursor = cursor or self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        return cursor.fetchone() is not None

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table."""
        cursor = self.connection.execute(f"PRAGMA table_info({table_name})")
        for row in cursor.fetchall():
            if row[1] == column_name:
                return True
        return False
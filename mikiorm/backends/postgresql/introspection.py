"""PostgreSQL database introspection utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mikiorm.query.safe_builder import SafeBuilder


class DatabaseIntrospection:
    """Encapsulates introspection methods for PostgreSQL."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.builder = SafeBuilder()

    def get_table_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of table names in the database."""
        sql = """
            SELECT tablename FROM pg_tables 
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """
        if cursor is None:
            cursor = self.connection.execute(sql, ())
        rows = cursor.fetchall()
        return [{"name": row[0]} for row in rows]

    def get_table_description(self, table_name: str) -> List[Dict[str, Any]]:
        """Return a description of the table columns."""
        sql = """
            SELECT 
                a.attname AS column_name,
                t.typname AS data_type,
                a.attnotnull AS not_null,
                a.atthasdef AS has_default,
                adsrc.adsrc AS default_value,
                a.attnum = ANY(ix.indkey::smallint[]) AS is_primary_key
            FROM pg_attribute a
            JOIN pg_type t ON a.atttypid = t.oid
            JOIN pg_class c ON a.attrelid = c.oid
            LEFT JOIN pg_index ix ON a.attrelid = ix.indrelid AND ix.indisprimary
            LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
            LEFT JOIN pg_description adsrc ON ad.adrelid = adsrc.objoid AND ad.adnum = adsrc.objsubid
            WHERE c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
        """
        rows = self.connection.fetchall(sql, (table_name,))
        
        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": not row[2],
                "default": row[4],
                "primary_key": bool(row[5]),
            }
            for row in rows
        ]

    def get_relations(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return a list of foreign key relations."""
        sql = """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
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
        sql = """
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = %s
        """
        rows = self.connection.fetchall(sql, (table_name,))
        
        return [
            {
                "name": row[0],
                "definition": row[1],
                "columns": self._extract_columns_from_index(row[1]),
                "unique": "UNIQUE" in row[1].upper(),
            }
            for row in rows
        ]

    def _extract_columns_from_index(self, definition: str) -> List[str]:
        """Extract column names from an index definition."""
        import re
        match = re.search(r'\((.+)\)', definition)
        if match:
            columns_str = match.group(1)
            return [col.strip('"').strip() for col in columns_str.split(',')]
        return []

    def get_schema_list(self, cursor: Any = None) -> List[Dict[str, Any]]:
        """Return list of schemas."""
        sql = """
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        """
        rows = cursor.fetchall() if cursor else self.connection.fetchall(sql, ())
        return [{"name": row[0]} for row in rows]

    def table_exists(self, table_name: str, cursor: Any = None) -> bool:
        """Check if a table exists."""
        sql = """
            SELECT EXISTS (
                SELECT FROM pg_tables WHERE tablename = %s
            )
        """
        row = self.connection.fetchone(sql, (table_name,))
        return bool(row[0]) if row else False

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table."""
        sql = """
            SELECT EXISTS (
                SELECT FROM pg_attribute 
                WHERE attrelid = %s::regclass AND attname = %s
            )
        """
        row = self.connection.fetchone(sql, (table_name, column_name))
        return bool(row[0]) if row else False
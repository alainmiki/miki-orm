"""Schema introspection for comparing model registry to database schema."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SchemaIntrospector:
    """Introspects database schema for tables, columns, indexes, constraints."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get_tables(self) -> List[str]:
        """Return list of table names in the database."""
        raise NotImplementedError

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Return column metadata for a table.
        
        Returns list of dicts with keys: name, type, null, default, primary_key, unique.
        """
        raise NotImplementedError

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Return index metadata for a table."""
        raise NotImplementedError

    def get_constraints(self, table_name: str) -> List[Dict[str, Any]]:
        """Return constraint metadata (FK, UNIQUE, CHECK) for a table."""
        raise NotImplementedError


class SQLiteIntrospector(SchemaIntrospector):
    """SQLite-specific schema introspection."""

    def get_tables(self) -> List[str]:
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        rows = self.connection.fetchall(sql, ())
        return [row[0] for row in rows]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        sql = f"PRAGMA table_info({table_name})"
        rows = self.connection.fetchall(sql, ())
        columns = []
        for row in rows:
            # row: (cid, name, type, notnull, default, pk)
            columns.append({
                "name": row[1],
                "type": row[2].upper() if row[2] else "TEXT",
                "null": not row[3],  # notnull=1 means NOT NULL
                "default": row[4],
                "primary_key": row[5] > 0,
                "unique": False,  # Need separate query for unique constraints
            })
        
        # Also get unique info from index_list
        self._augment_unique_info(table_name, columns)
        return columns

    def _augment_unique_info(self, table_name: str, columns: List[Dict[str, Any]]) -> None:
        """Augment column dicts with unique constraint info from indexes."""
        try:
            sql = f"PRAGMA index_list({table_name})"
            indexes = self.connection.fetchall(sql, ())
            for idx_row in indexes:
                idx_name = idx_row[1]
                is_unique = idx_row[2] == 1
                if is_unique:
                    # Get index info to see which columns
                    sql2 = f"PRAGMA index_info({idx_name})"
                    idx_cols = self.connection.fetchall(sql2, ())
                    for ic in idx_cols:
                        col_name = ic[2]
                        for col in columns:
                            if col["name"] == col_name:
                                col["unique"] = True
        except Exception as e:
            logger.debug(f"Could not get unique index info: {e}")

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        sql = f"PRAGMA index_list({table_name})"
        rows = self.connection.fetchall(sql, ())
        indexes = []
        for row in rows:
            idx_name = row[1]
            is_unique = row[2] == 1
            # Get columns for this index
            sql2 = f"PRAGMA index_info({idx_name})"
            cols_data = self.connection.fetchall(sql2, ())
            col_names = [c[2] for c in cols_data]
            indexes.append({
                "name": idx_name,
                "columns": col_names,
                "unique": is_unique,
            })
        return indexes

    def get_constraints(self, table_name: str) -> List[Dict[str, Any]]:
        """SQLite doesn't expose FKs directly in a convenient way; use pragma."""
        sql = f"PRAGMA foreign_key_list({table_name})"
        try:
            rows = self.connection.fetchall(sql, ())
            constraints = []
            for row in rows:
                # row: (id, seq, table, from, to, on_update, on_delete, match)
                constraints.append({
                    "type": "FOREIGN_KEY",
                    "column": row[3],
                    "reference_table": row[2],
                    "reference_column": row[4],
                    "on_delete": row[6],
                    "on_update": row[5],
                })
            return constraints
        except Exception:
            return []


class PostgresIntrospector(SchemaIntrospector):
    """PostgreSQL-specific schema introspection using information_schema."""

    def get_tables(self) -> List[str]:
        sql = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
        rows = self.connection.fetchall(sql, ())
        return [row[0] for row in rows]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT column_name, data_type, is_nullable, column_default,
                   (SELECT COUNT(*) FROM information_schema.key_column_usage kcu
                    JOIN information_schema.table_constraints tc 
                      ON kcu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY' 
                      AND kcu.table_name = c.table_name 
                      AND kcu.column_name = c.column_name) as pk_count
            FROM information_schema.columns c
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """
        rows = self.connection.fetchall(sql, (table_name,))
        columns = []
        for row in rows:
            columns.append({
                "name": row[0],
                "type": row[1].upper() if row[1] else "TEXT",
                "null": row[2] == "YES",
                "default": row[3],
                "primary_key": row[4] > 0,
                "unique": False,  # will be filled from get_constraints
            })
        # Augment with unique info
        self._augment_unique_info(table_name, columns)
        return columns

    def _augment_unique_info(self, table_name: str, columns: List[Dict[str, Any]]) -> None:
        indexes = self.get_indexes(table_name)
        for idx in indexes:
            if idx.get("unique") and len(idx["columns"]) == 1:
                col_name = idx["columns"][0]
                for col in columns:
                    if col["name"] == col_name:
                        col["unique"] = True

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = %s AND schemaname = 'public'
        """
        rows = self.connection.fetchall(sql, (table_name,))
        indexes = []
        for row in rows:
            idx_name = row[0]
            def_str = row[1]
            # Parse columns from definition: CREATE UNIQUE INDEX idx ON tbl(col1, col2)
            columns = []
            if "(" in def_str:
                inside = def_str[def_str.index("(") + 1:def_str.rindex(")")]
                columns = [c.strip() for c in inside.split(",")]
            is_unique = "UNIQUE" in def_str.upper()
            indexes.append({
                "name": idx_name,
                "columns": columns,
                "unique": is_unique,
            })
        return indexes

    def get_constraints(self, table_name: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT kcu.constraint_name, kcu.column_name,
                   ccu.table_name AS reference_table,
                   ccu.column_name AS reference_column,
                   rc.update_rule AS on_update,
                   rc.delete_rule AS on_delete
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.table_constraints tc 
              ON kcu.constraint_name = tc.constraint_name
            JOIN information_schema.referential_constraints rc 
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu 
              ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' 
              AND kcu.table_name = %s 
              AND kcu.table_schema = 'public'
        """
        rows = self.connection.fetchall(sql, (table_name,))
        constraints = []
        for row in rows:
            constraints.append({
                "type": "FOREIGN_KEY",
                "name": row[0],
                "column": row[1],
                "reference_table": row[2],
                "reference_column": row[3],
                "on_update": row[4],
                "on_delete": row[5],
            })
        return constraints


class MySQLIntrospector(SchemaIntrospector):
    """MySQL-specific schema introspection."""

    def get_tables(self) -> List[str]:
        sql = "SHOW TABLES"
        rows = self.connection.fetchall(sql, ())
        return [row[0] for row in rows]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        sql = f"DESCRIBE {table_name}"
        rows = self.connection.fetchall(sql, ())
        columns = []
        for row in rows:
            # row: Field, Type, Null, Key, Default, Extra
            col_name = row[0]
            col_type = row[1].upper() if row[1] else "TEXT"
            is_null = row[2] == "YES"
            default = row[4]
            key = row[3]  # PRI, UNI, MUL
            extra = row[5] if len(row) > 5 else ""
            primary_key = key == "PRI"
            unique = key == "UNI"
            columns.append({
                "name": col_name,
                "type": col_type,
                "null": is_null,
                "default": default,
                "primary_key": primary_key,
                "unique": unique,
            })
        return columns

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        sql = f"SHOW INDEX FROM {table_name}"
        rows = self.connection.fetchall(sql, ())
        indexes_dict: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            idx_name = row[2]
            col_name = row[4]
            is_unique = row[1] == 1
            if idx_name not in indexes_dict:
                indexes_dict[idx_name] = {
                    "name": idx_name,
                    "columns": [],
                    "unique": is_unique,
                }
            indexes_dict[idx_name]["columns"].append(col_name)
        return list(indexes_dict.values())

    def get_constraints(self, table_name: str) -> List[Dict[str, Any]]:
        """Fetch foreign key constraints from information_schema."""
        sql = """
            SELECT 
                rc.CONSTRAINT_NAME,
                kcu.COLUMN_NAME,
                kcu.REFERENCED_TABLE_NAME,
                kcu.REFERENCED_COLUMN_NAME,
                rc.UPDATE_RULE,
                rc.DELETE_RULE
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            JOIN information_schema.KEY_COLUMN_USAGE kcu 
              ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            WHERE kcu.TABLE_NAME = %s AND kcu.TABLE_SCHEMA = DATABASE()
        """
        rows = self.connection.fetchall(sql, (table_name,))
        constraints = []
        for row in rows:
            constraints.append({
                "type": "FOREIGN_KEY",
                "name": row[0],
                "column": row[1],
                "reference_table": row[2],
                "reference_column": row[3],
                "on_update": row[4],
                "on_delete": row[5],
            })
        return constraints


def get_introspector(connection: Any, engine: str) -> SchemaIntrospector:
    """Return appropriate introspector for the given engine."""
    if engine == "sqlite":
        return SQLiteIntrospector(connection)
    elif engine == "postgresql":
        return PostgresIntrospector(connection)
    elif engine == "mysql":
        return MySQLIntrospector(connection)
    else:
        raise ValueError(f"Unsupported engine: {engine}")

"""Oracle database introspection utilities."""

from __future__ import annotations
from typing import Any
from ..base.introspection import BaseIntrospection


class OracleIntrospection(BaseIntrospection):
    """Encapsulates introspection methods for Oracle."""

    def get_tables(self) -> list[str]:
        """Return a list of table names in the database."""
        cursor = self.connection.execute("SELECT table_name FROM user_tables")
        return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        """Return a description of the table columns."""
        # Oracle stores object names in uppercase by default.
        sql = """
            SELECT
                cols.column_name,
                cols.data_type,
                cols.nullable,
                cols.data_default,
                (SELECT COUNT(*)
                 FROM user_constraints cons
                 JOIN user_cons_columns c ON cons.constraint_name = c.constraint_name
                 WHERE cons.constraint_type = 'P'
                   AND cons.table_name = cols.table_name
                   AND c.column_name = cols.column_name) AS is_pk
            FROM user_tab_columns cols
            WHERE cols.table_name = :1
            ORDER BY cols.column_id
        """
        rows = self.connection.fetchall(sql, (table_name.upper(),))

        return [
            {
                "name": row[0],
                "type": row[1],
                "null": row[2] == "Y",
                "default": row[3],
                "primary_key": bool(row[4]),
            }
            for row in rows
        ]

    def get_indexes(self, table_name: str) -> list[dict[str, Any]]:
        """Return a list of index dictionaries for the given table."""
        sql = """
            SELECT
                i.index_name,
                i.uniqueness,
                c.column_name
            FROM user_indexes i
            JOIN user_ind_columns c ON i.index_name = c.index_name
            WHERE i.table_name = :1
              AND i.index_type = 'NORMAL'
            ORDER BY i.index_name, c.column_position
        """
        rows = self.connection.fetchall(sql, (table_name.upper(),))

        indexes: dict[str, dict[str, Any]] = {}
        for row in rows:
            name, uniqueness, col_name = row
            if name not in indexes:
                indexes[name] = {
                    "name": name,
                    "columns": [],
                    "unique": uniqueness == "UNIQUE",
                }
            indexes[name]["columns"].append(col_name)

        return list(indexes.values())

    def get_constraints(self, table_name: str) -> list[dict[str, Any]]:
        """Return a list of constraints for the table."""
        sql = """
            SELECT constraint_name, constraint_type, search_condition
            FROM user_constraints
            WHERE table_name = :1
        """
        rows = self.connection.fetchall(sql, (table_name.upper(),))
        return [
            {
                "name": row[0],
                "type": row[1],
                "details": row[2],
            }
            for row in rows
        ]

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        sql = "SELECT COUNT(*) FROM user_tables WHERE table_name = :1"
        row = self.connection.fetchone(sql, (table_name.upper(),))
        return bool(row[0]) if row else False
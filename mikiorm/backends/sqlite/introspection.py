"""SQLite database introspection."""

from __future__ import annotations

from typing import Any

from mikiorm.backends.base.introspection import BaseIntrospection


class SQLiteIntrospection(BaseIntrospection):
    """Introspects SQLite database tables and columns."""

    def get_tables(self) -> list[str]:
        """Returns a list of table names in the database."""
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        """
        Returns a list of column dictionaries for the given table.
        Each dictionary contains:
            - name (str)
            - type (str)
            - null (bool)
            - primary_key (bool)
            - default (Any)
            - unique (bool)
        """
        cursor = self.connection.execute(f"PRAGMA table_info({table_name});")
        columns_info = cursor.fetchall()

        columns = []
        for col_info in columns_info:
            # cid, name, type, notnull, dflt_value, pk
            col_name = col_info[1]
            col_type = col_info[2]
            not_null = bool(col_info[3])
            default_value = col_info[4]
            is_pk = bool(col_info[5])

            # Check for unique constraint (SQLite doesn't have a direct PRAGMA for this per column)
            # This is a simplification; a full implementation would parse CREATE TABLE SQL.
            is_unique = False
            if not is_pk:  # PK implies unique
                try:
                    unique_check_cursor = self.connection.execute(
                        f"PRAGMA index_list({table_name});"
                    )
                    indexes = unique_check_cursor.fetchall()
                    for index in indexes:
                        index_name = index[1]
                        is_unique_index = bool(index[2])
                        if is_unique_index:
                            index_info_cursor = self.connection.execute(
                                f"PRAGMA index_info({index_name});"
                            )
                            index_cols = index_info_cursor.fetchall()
                            if len(index_cols) == 1 and index_cols[0][2] == col_name:
                                is_unique = True
                                break
                except Exception:
                    # Fallback if index introspection fails
                    pass

            columns.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "null": not not_null,
                    "primary_key": is_pk,
                    "default": default_value,
                    "unique": is_unique,
                }
            )
        return columns

    def get_primary_key_column(self, table_name: str) -> str | None:
        columns = self.get_columns(table_name)
        for col in columns:
            if col["primary_key"]:
                return col["name"]
        return None

    def get_indexes(self, table_name: str) -> list[dict[str, Any]]:
        """
        Returns a list of index dictionaries for the given table.
        Each dictionary contains:
            - name (str)
            - columns (list[str])
            - unique (bool)
        """
        cursor = self.connection.execute(f"PRAGMA index_list({table_name});")
        indexes_info = cursor.fetchall()

        indexes = []
        for idx_info in indexes_info:
            # seq, name, unique, origin, partial
            idx_name = idx_info[1]
            is_unique = bool(idx_info[2])
            origin = idx_info[3]

            # Skip primary key indexes if they were already handled by column PK
            if origin == 'pk':
                continue

            info_cursor = self.connection.execute(f"PRAGMA index_info({idx_name});")
            cols_info = info_cursor.fetchall()
            # seqno, cid, name
            columns = [c[2] for c in cols_info if c[2]]

            indexes.append({
                "name": idx_name,
                "columns": columns,
                "unique": is_unique
            })
        return indexes

    def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        """
        Returns a list of foreign key dictionaries for the given table.
        Each dictionary contains:
            - column (str): The column in the current table.
            - referred_table (str): The table being referenced.
            - referred_column (str): The column in the referenced table.
        """
        cursor = self.connection.execute(f"PRAGMA foreign_key_list({table_name});")
        fks_info = cursor.fetchall()

        fks = []
        for fk_info in fks_info:
            # id, seq, table, from, to, on_update, on_delete, match
            fks.append(
                {
                    "column": fk_info[3],
                    "referred_table": fk_info[2],
                    "referred_column": fk_info[4],
                }
            )
        return fks

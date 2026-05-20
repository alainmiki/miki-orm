"""SQLite database operations."""

from __future__ import annotations

import datetime
from typing import Any, Optional, Tuple

from mikiorm.query import SafeBuilder


class DatabaseOperations:
    """Encapsulates database operations for SQLite."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.builder = SafeBuilder()

    def sql_flush(self, style: Any, tables: list, **kwargs: Any) -> list:
        """Return SQL statements to flush the database."""
        if not tables:
            return []
        
        # SQLite doesn't support TRUNCATE, use DELETE
        statements = []
        for table in tables:
            # SQLite doesn't enforce foreign keys without PRAGMA, so we need to disable them
            statements.extend([
                "PRAGMA foreign_keys = OFF",
                f"DELETE FROM {self.builder.quote_table(table)}",
            ])
        
        return statements

    def sql_sequence_reset(self, style: Any, model_list: list, **kwargs: Any) -> list:
        """Return SQL statements to reset sequences (SQLite doesn't use them)."""
        return []

    def start_transaction_sql(self, connection: Any) -> str:
        """Return SQL to start a transaction."""
        return "BEGIN"

    def set_time_zone_sql(self) -> Optional[str]:
        """SQLite doesn't support time zones."""
        return None

    def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'"{name}"'

    def no_limit_value(self) -> int:
        """Return the value that represents no limit in SQLite."""
        return -1

    def last_insert_id(self, connection: Any, cursor: Any) -> int:
        """Return the last inserted ID."""
        return cursor.lastrowid if cursor else 0

    def date_extract_sql(self, lookup_type: str, field_name: str) -> Tuple[str, list]:
        """Extract date parts for SQLite."""
        if lookup_type == 'year':
            return f"CAST(strftime('%Y', {field_name}) AS INTEGER)", []
        elif lookup_type == 'month':
            return f"CAST(strftime('%m', {field_name}) AS INTEGER)", []
        elif lookup_type == 'day':
            return f"CAST(strftime('%d', {field_name}) AS INTEGER)", []
        elif lookup_type == 'hour':
            return f"CAST(strftime('%H', {field_name}) AS INTEGER)", []
        elif lookup_type == 'minute':
            return f"CAST(strftime('%M', {field_name}) AS INTEGER)", []
        elif lookup_type == 'second':
            return f"CAST(strftime('%S', {field_name}) AS INTEGER)", []
        return field_name, []

    def date_interval_sql(self, timedelta: datetime.timedelta) -> Tuple[str, list]:
        """Return SQL for a date interval."""
        raise NotImplementedError("SQLite does not support interval arithmetic")

    def datetime_cast_sql(self, field_name: str, tzname: str) -> str:
        """Cast to datetime for SQLite."""
        return field_name

    def random_function_sql(self) -> str:
        """Return SQL for a random function."""
        return "RANDOM()"

    def bulk_batch_size(self, fields: list, objs: list) -> int:
        """Return the batch size for bulk inserts."""
        return 100

    def combine_expression(self, connector: str, sub_expressions: list) -> str:
        """Combine expressions with a connector."""
        conn = f" {connector.upper()} "
        return f"({conn.join(sub_expressions)})"

    def get_db_converters(self, expression: Any) -> list:
        """Return converters for database values."""
        return []

    def check_expression_support(self, expression: Any) -> bool:
        """Check if the expression is supported."""
        return True
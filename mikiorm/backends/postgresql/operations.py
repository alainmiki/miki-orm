"""PostgreSQL database operations."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from mikiorm.query.safe_builder import SafeBuilder


class DatabaseOperations:
    """Encapsulates database operations for PostgreSQL."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.builder = SafeBuilder()

    def sql_flush(self, style: Any, tables: list, **kwargs: Any) -> list:
        """Return SQL statements to flush the database."""
        if not tables:
            return []
        
        # PostgreSQL: TRUNCATE with CASCADE to handle foreign keys
        table_list = ", ".join(self.builder.quote_table(t) for t in tables)
        
        statements = [
            f"SET FOREIGN_KEY_CHECKS=0",  # Disable FK checks
            f"TRUNCATE TABLE {table_list} CASCADE",
            "SET FOREIGN_KEY_CHECKS=1",  # Re-enable
        ]
        
        return statements

    def sql_sequence_reset(self, style: Any, model_list: list, **kwargs: Any) -> list:
        """Return SQL statements to reset sequences."""
        statements = []
        for model in model_list:
            for field_name, field in model._meta.fields.items():
                if hasattr(field, 'primary_key') and field.primary_key:
                    table = model._meta.table_name or model.__name__.lower() + 's'
                    # PostgreSQL uses sequences for auto-increment
                    seq_name = f"{table}_{field_name}_seq"
                    statements.append(f"SELECT setval('{seq_name}', 1, false)")
        return statements

    def start_transaction_sql(self, connection: Any) -> str:
        """Return SQL to start a transaction."""
        return "BEGIN"

    def set_time_zone_sql(self) -> Optional[str]:
        """PostgreSQL supports setting timezone."""
        return "SET TIME ZONE 'UTC'"

    def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'"{name}"'

    def no_limit_value(self) -> int:
        """Return the value that represents no limit."""
        return -1

    def last_insert_id(self, connection: Any, cursor: Any) -> int:
        """PostgreSQL doesn't have last_insert_id; use RETURNING clause."""
        return cursor.fetchone()[0] if cursor else 0

    def date_extract_sql(self, lookup_type: str, field_name: str) -> Tuple[str, list]:
        """Extract date parts for PostgreSQL."""
        lookup_map = {
            'year': "EXTRACT(year FROM {})",
            'month': "EXTRACT(month FROM {})",
            'day': "EXTRACT(day FROM {})",
            'hour': "EXTRACT(hour FROM {})",
            'minute': "EXTRACT(minute FROM {})",
            'second': "EXTRACT(second FROM {})",
            'week': "EXTRACT(week FROM {})",
            'quarter': "EXTRACT(quarter FROM {})",
        }
        
        sql_template = lookup_map.get(lookup_type, "EXTRACT({})")
        return sql_template.format(field_name), []

    def date_interval_sql(self, timedelta: Any) -> Tuple[str, list]:
        """Return SQL for a date interval."""
        days = timedelta.days
        seconds = timedelta.seconds
        microseconds = timedelta.microseconds
        
        interval_parts = []
        if days:
            interval_parts.append(f"{days} days")
        if seconds:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            if hours:
                interval_parts.append(f"{hours} hours")
            if minutes:
                interval_parts.append(f"{minutes} minutes")
            if secs:
                interval_parts.append(f"{secs} seconds")
        if microseconds:
            interval_parts.append(f"{microseconds} microseconds")
        
        if not interval_parts:
            return "INTERVAL '0 seconds'", []
        
        interval_str = " + ".join(f"'{p}'" for p in interval_parts)
        return f"({interval_str})", []

    def datetime_cast_sql(self, field_name: str, tzname: str) -> str:
        """Cast to datetime with timezone for PostgreSQL."""
        if tzname:
            return f"({field_name} AT TIME ZONE '{tzname}')"
        return field_name

    def random_function_sql(self) -> str:
        """Return SQL for a random function."""
        return "RANDOM()"

    def bulk_batch_size(self, fields: list, objs: list) -> int:
        """Return the batch size for bulk inserts."""
        return 1000

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
"""MySQL database operations."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from mikiorm.query import SafeBuilder


class DatabaseOperations:
    """Encapsulates database operations for MySQL."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.builder = SafeBuilder()

    def sql_flush(self, style: Any, tables: list, **kwargs: Any) -> list:
        """Return SQL statements to flush the database."""
        if not tables:
            return []
        
        # MySQL: TRUNCATE with CASCADE equivalent
        statements = []
        for table in reversed(tables):  # Reverse order to handle foreign keys
            statements.append(f"SET FOREIGN_KEY_CHECKS=0")
            statements.append(f"DROP TABLE IF EXISTS {self.builder.quote_table(table)}")
        
        statements.append("SET FOREIGN_KEY_CHECKS=1")
        return statements

    def sql_sequence_reset(self, style: Any, model_list: list, **kwargs: Any) -> list:
        """Return SQL statements to reset auto_increment values."""
        statements = []
        for model in model_list:
            for field_name, field in model._meta.fields.items():
                if hasattr(field, 'primary_key') and field.primary_key and hasattr(field, 'auto_created'):
                    table = model._meta.table_name or model.__name__.lower() + 's'
                    # MySQL uses AUTO_INCREMENT
                    seq_stmt = f"ALTER TABLE {self.builder.quote_table(table)} AUTO_INCREMENT = 1"
                    statements.append(seq_stmt)
        return statements

    def start_transaction_sql(self, connection: Any) -> str:
        """Return SQL to start a transaction."""
        return "START TRANSACTION"

    def set_time_zone_sql(self) -> Optional[str]:
        """MySQL supports setting timezone."""
        return "SET time_zone = '+00:00'"

    def quote_name(self, name: str) -> str:
        """Quote a database identifier."""
        return f'`{name}`'

    def no_limit_value(self) -> int:
        """Return the value that represents no limit."""
        return -1

    def last_insert_id(self, connection: Any, cursor: Any) -> int:
        """Return the last inserted ID."""
        return cursor.lastrowid if cursor else 0

    def date_extract_sql(self, lookup_type: str, field_name: str) -> Tuple[str, list]:
        """Extract date parts for MySQL."""
        lookup_map = {
            'year': "EXTRACT(YEAR FROM {})",
            'month': "EXTRACT(MONTH FROM {})",
            'day': "EXTRACT(DAY FROM {})",
            'hour': "EXTRACT(HOUR FROM {})",
            'minute': "EXTRACT(MINUTE FROM {})",
            'second': "EXTRACT(SECOND FROM {})",
            'week': "EXTRACT(WEEK FROM {})",
            'quarter': "EXTRACT(QUARTER FROM {})",
        }
        
        sql_template = lookup_map.get(lookup_type, "EXTRACT({})")
        return sql_template.format(field_name), []

    def date_interval_sql(self, timedelta: Any) -> Tuple[str, list]:
        """Return SQL for a date interval."""
        from datetime import timedelta as td
        days = timedelta.days
        seconds = timedelta.seconds
        microseconds = timedelta.microseconds
        
        interval_strs = []
        if days:
            interval_strs.append(f"{days} DAY")
        if seconds >= 3600:
            hours = seconds // 3600
            interval_strs.append(f"{hours} HOUR")
            seconds %= 3600
        if seconds >= 60:
            minutes = seconds // 60
            interval_strs.append(f"{minutes} MINUTE")
            seconds %= 60
        if seconds:
            interval_strs.append(f"{seconds} SECOND")
        if microseconds:
            interval_strs.append(f"{microseconds} MICROSECOND")
        
        if not interval_strs:
            return "INTERVAL '0' SECOND", []
        
        interval_str = " + ".join(f"INTERVAL '{s}'" for s in interval_strs)
        return interval_str, []

    def datetime_cast_sql(self, field_name: str, tzname: str) -> str:
        """Cast to datetime for MySQL."""
        return field_name

    def random_function_sql(self) -> str:
        """Return SQL for a random function."""
        return "RAND()"

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
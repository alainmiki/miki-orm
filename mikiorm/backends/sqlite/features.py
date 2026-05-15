"""SQLite database feature support detection."""

from __future__ import annotations


class DatabaseFeatures:
    """Defines what features SQLite supports."""

    # Transaction support
    supports_transactions = True
    supports_savepoints = True
    supports_mixed_managed_not_managed_transactions = False
    
    # DDL
    can_rollback_ddl = False
    supports_column_check_constraints = False
    supports_table_check_constraints = True
    
    # Data types
    supports_timezones = False
    supports_json_field = False  # SQLite doesn't have native JSON type
    supports_binary_field = True
    
    # Query features
    supports_regex_backreference = False
    supports_date_lookup = True
    supports_time_lookup = True
    supports_datetime_lookup = True
    supports_seconds_precision = False
    
    # Aggregations
    supports_aggregates = True
    
    # Indexes
    supports_index_on_text_field = True
    supports_index_on_json_field = False
    
    # Miscellaneous
    supports_sequence_reset = False
    supports_stored_generated_columns = True
    
    # SQLite-specific defaults
    uses_savepoints = True
    atomic_transactions = True
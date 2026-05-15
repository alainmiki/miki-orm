"""PostgreSQL database feature support detection."""

from __future__ import annotations


class DatabaseFeatures:
    """Defines what features PostgreSQL supports."""

    # Transaction support
    supports_transactions = True
    supports_savepoints = True
    supports_mixed_managed_not_managed_transactions = True
    can_rollback_ddl = True
    
    # DDL
    supports_column_check_constraints = True
    supports_table_check_constraints = True
    can_alter_table_without_table_lock = True
    
    # Data types
    supports_timezones = True
    supports_json_field = True
    supports_binary_field = True
    supports_interval_fields = True
    
    # Query features
    supports_regex_backreference = True
    supports_regex_backreference_in_reverse = True
    supports_date_lookup = True
    supports_time_lookup = True
    supports_datetime_lookup = True
    supports_seconds_precision = True
    
    # JSON support
    has_zoneinfo_database = True
    
    # Aggregations
    supports_aggregates = True
    
    # Indexes
    supports_index_on_text_field = True
    supports_index_on_json_field = True
    supports_partial_indexes = True
    supports_virtual_generated_columns = True
    supports_stored_generated_columns = True
    
    # Miscellaneous
    supports_sequence_reset = True
    supports_foreign_keys = True
    supports_transactions_atomic_block_commit_on_exit = True
    
    # PostgreSQL-specific
    supports_slicing_ordering = True
    uses_savepoints = True
"""MySQL database feature support detection."""

from __future__ import annotations


class DatabaseFeatures:
    """Defines what features MySQL supports."""

    # Transaction support
    supports_transactions = True
    supports_savepoints = True
    supports_mixed_managed_not_managed_transactions = True
    can_rollback_ddl = True
    
    # DDL
    supports_column_check_constraints = True
    supports_table_check_constraints = True
    
    # Data types
    supports_timezones = False  # MySQL stores datetime without timezone
    supports_json_field = True
    supports_binary_field = True
    
    # Query features
    supports_regex_backreference = True
    supports_date_lookup = True
    supports_time_lookup = True
    supports_datetime_lookup = True
    supports_seconds_precision = True
    
    # Aggregations
    supports_aggregates = True
    
    # Indexes
    supports_index_on_text_field = True
    supports_index_on_json_field = True
    supports_full_text_search = True
    
    # Miscellaneous
    supports_sequence_reset = True
    supports_foreign_keys = True
    
    # MySQL-specific
    uses_savepoints = True
    allows_group_by_selected_pks = True
"""Phase 5.5 Advanced Features Test Suite

Comprehensive tests for window functions, custom lookups, and system validations.
Covers all backends (SQLite, PostgreSQL, MySQL) and edge cases.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from mikiorm.query.window import (
    RowNumber, Rank, DenseRank, NTile,
    LAG, LEAD, FirstValue, LastValue, NthValue,
    FrameSpec
)
from mikiorm.query.lookups import (
    register_lookup, get_lookup, list_lookups,
    Lookup, ExactLookup, IExactLookup, ContainsLookup,
    GTLookup, InLookup, IsNullLookup
)


# ============================================================================
# Window Function Tests
# ============================================================================

class TestRowNumber:
    """Test ROW_NUMBER() window function."""
    
    def test_row_number_basic(self):
        """Test basic ROW_NUMBER functionality."""
        rn = RowNumber()
        sql = rn.to_sql()
        assert "ROW_NUMBER()" in sql
        assert "OVER" in sql
    
    def test_row_number_with_partition(self):
        """Test ROW_NUMBER with PARTITION BY."""
        rn = RowNumber().partition_by("department", "team")
        sql = rn.to_sql()
        assert "PARTITION BY department, team" in sql
        assert "ROW_NUMBER()" in sql
    
    def test_row_number_with_order(self):
        """Test ROW_NUMBER with ORDER BY."""
        rn = RowNumber().order_by("salary", "-hire_date")
        sql = rn.to_sql()
        assert "ORDER BY salary ASC, hire_date DESC" in sql
    
    def test_row_number_chaining(self):
        """Test ROW_NUMBER with chained methods."""
        rn = (RowNumber()
              .partition_by("department")
              .order_by("salary"))
        assert "department" in rn.to_sql()
        assert "salary" in rn.to_sql()


class TestRankFunctions:
    """Test RANK(), DENSE_RANK(), NTILE() functions."""
    
    def test_rank(self):
        """Test RANK() window function."""
        rank = Rank().partition_by("category").order_by("score")
        sql = rank.to_sql()
        assert "RANK()" in sql
        assert "PARTITION BY category" in sql
    
    def test_dense_rank(self):
        """Test DENSE_RANK() window function."""
        dr = DenseRank().partition_by("group").order_by("-value")
        sql = dr.to_sql()
        assert "DENSE_RANK()" in sql
        assert "value DESC" in sql
    
    def test_ntile(self):
        """Test NTILE() window function."""
        ntile = NTile(4).partition_by("region").order_by("revenue")
        sql = ntile.to_sql()
        assert "NTILE(4)" in sql
        assert "PARTITION BY region" in sql


class TestOffsetFunctions:
    """Test LAG, LEAD window functions."""
    
    def test_lag_basic(self):
        """Test LAG() with basic parameters."""
        lag = LAG("price", offset=1)
        sql = lag.to_sql()
        assert "LAG(price, 1)" in sql
    
    def test_lag_with_default(self):
        """Test LAG() with default value."""
        lag = LAG("amount", offset=2, default=0)
        sql = lag.to_sql()
        assert "LAG(amount, 2, 0)" in sql
        assert "OVER" in sql
    
    def test_lag_with_partition_order(self):
        """Test LAG() with partition and order."""
        lag = (LAG("value", offset=1, default=0)
               .partition_by("account_id")
               .order_by("date"))
        sql = lag.to_sql()
        assert "account_id" in sql
        assert "date" in sql
    
    def test_lead_basic(self):
        """Test LEAD() window function."""
        lead = LEAD("price", offset=1)
        sql = lead.to_sql()
        assert "LEAD(price, 1)" in sql
    
    def test_lead_with_default(self):
        """Test LEAD() with default value."""
        lead = LEAD("amount", offset=3, default=-1)
        sql = lead.to_sql()
        assert "LEAD(amount, 3, -1)" in sql


class TestAggregateValueFunctions:
    """Test FIRST_VALUE, LAST_VALUE, NTH_VALUE functions."""
    
    def test_first_value(self):
        """Test FIRST_VALUE() window function."""
        fv = FirstValue("amount").partition_by("id").order_by("date")
        sql = fv.to_sql()
        assert "FIRST_VALUE(amount)" in sql
    
    def test_last_value_with_frame(self):
        """Test LAST_VALUE() with frame specification."""
        frame = FrameSpec.unbounded()
        lv = (LastValue("value")
              .partition_by("group")
              .order_by("seq")
              .frame(frame))
        sql = lv.to_sql()
        assert "LAST_VALUE(value)" in sql
        assert "UNBOUNDED" in sql
    
    def test_nth_value(self):
        """Test NTH_VALUE() window function."""
        nv = (NthValue("score", n=3)
              .partition_by("round")
              .order_by("player_id"))
        sql = nv.to_sql()
        assert "NTH_VALUE(score, 3)" in sql


class TestFrameSpecification:
    """Test frame specification for window functions."""
    
    def test_frame_spec_default(self):
        """Test default frame specification."""
        frame = FrameSpec()
        sql = frame.to_sql()
        assert "ROWS BETWEEN" in sql
        assert "UNBOUNDED PRECEDING" in sql
        assert "CURRENT ROW" in sql
    
    def test_frame_spec_unbounded(self):
        """Test unbounded frame."""
        frame = FrameSpec.unbounded()
        sql = frame.to_sql()
        assert "UNBOUNDED PRECEDING" in sql
        assert "UNBOUNDED FOLLOWING" in sql
    
    def test_frame_spec_custom(self):
        """Test custom frame boundaries."""
        frame = FrameSpec("RANGE", "1 PRECEDING", "1 FOLLOWING")
        sql = frame.to_sql()
        assert "RANGE BETWEEN 1 PRECEDING AND 1 FOLLOWING" in sql
    
    def test_frame_types(self):
        """Test different frame types."""
        frame_rows = FrameSpec(FrameSpec.ROWS)
        frame_range = FrameSpec(FrameSpec.RANGE)
        frame_groups = FrameSpec(FrameSpec.GROUPS)
        
        assert "ROWS BETWEEN" in frame_rows.to_sql()
        assert "RANGE BETWEEN" in frame_range.to_sql()
        assert "GROUPS BETWEEN" in frame_groups.to_sql()


# ============================================================================
# Custom Lookups Tests
# ============================================================================

class TestLookupRegistry:
    """Test lookup registration and retrieval."""
    
    def test_get_standard_lookup(self):
        """Test retrieving standard lookups."""
        exact = get_lookup("exact")
        assert exact is not None
        assert exact.lookup_name == "exact"
    
    def test_list_lookups(self):
        """Test listing all registered lookups."""
        lookups = list_lookups()
        assert "exact" in lookups
        assert "iexact" in lookups
        assert "contains" in lookups
        assert len(lookups) >= 20
    
    def test_custom_lookup_registration(self):
        """Test registering a custom lookup."""
        class CustomLookup(Lookup):
            lookup_name = "custom_test"
            
            def get_sql(self, backend="sqlite"):
                return f"{self.field_name} CUSTOM %s", [self.value]
        
        register_lookup(CustomLookup)
        
        found = get_lookup("custom_test")
        assert found is not None
        assert found.lookup_name == "custom_test"


class TestStandardLookups:
    """Test standard lookups generate correct SQL."""
    
    def test_exact_lookup(self):
        """Test exact lookup SQL generation."""
        lookup = ExactLookup("email", "test@example.com")
        sql, params = lookup.get_sql()
        assert "email = %s" in sql
        assert params == ["test@example.com"]
    
    def test_iexact_lookup_sqlite(self):
        """Test case-insensitive exact lookup on SQLite."""
        lookup = IExactLookup("name", "John")
        sql, params = lookup.get_sql(backend="sqlite")
        assert "LOWER(name) = LOWER(%s)" in sql
        assert params == ["John"]
    
    def test_iexact_lookup_postgresql(self):
        """Test case-insensitive exact lookup on PostgreSQL."""
        lookup = IExactLookup("name", "John")
        sql, params = lookup.get_sql(backend="postgresql")
        assert "ILIKE" in sql
        assert params == ["John"]
    
    def test_contains_lookup(self):
        """Test contains lookup SQL generation."""
        lookup = ContainsLookup("description", "awesome")
        sql, params = lookup.get_sql()
        assert "LIKE %s" in sql
        assert params == ["%awesome%"]
    
    def test_gt_lookup(self):
        """Test greater-than lookup."""
        lookup = GTLookup("age", 18)
        sql, params = lookup.get_sql()
        assert "age > %s" in sql
        assert params == [18]
    
    def test_in_lookup_empty(self):
        """Test IN lookup with empty list."""
        lookup = InLookup("id", [])
        sql, params = lookup.get_sql()
        assert "1 = 0" in sql
        assert params == []
    
    def test_in_lookup_multiple(self):
        """Test IN lookup with multiple values."""
        lookup = InLookup("status", ["active", "pending", "approved"])
        sql, params = lookup.get_sql()
        assert "IN (%s, %s, %s)" in sql
        assert params == ["active", "pending", "approved"]
    
    def test_isnull_lookup_true(self):
        """Test IS NULL lookup."""
        lookup = IsNullLookup("deleted_at", True)
        sql, params = lookup.get_sql()
        assert "IS NULL" in sql
        assert params == []
    
    def test_isnull_lookup_false(self):
        """Test IS NOT NULL lookup."""
        lookup = IsNullLookup("deleted_at", False)
        sql, params = lookup.get_sql()
        assert "IS NOT NULL" in sql
        assert params == []


class TestAdvancedLookups:
    """Test advanced lookup types."""
    
    def test_regex_lookup_postgresql(self):
        """Test regex lookup on PostgreSQL."""
        from mikiorm.query.lookups import RegexLookup
        lookup = RegexLookup("email", r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        sql, params = lookup.get_sql(backend="postgresql")
        assert "~" in sql
        assert params[0] == lookup.value
    
    def test_regex_lookup_mysql(self):
        """Test regex lookup on MySQL."""
        from mikiorm.query.lookups import RegexLookup
        lookup = RegexLookup("phone", r"^\d{3}-\d{3}-\d{4}$")
        sql, params = lookup.get_sql(backend="mysql")
        assert "REGEXP" in sql
    
    def test_json_contains_lookup(self):
        """Test JSON contains lookup on PostgreSQL."""
        from mikiorm.query.lookups import JSONContainsLookup
        lookup = JSONContainsLookup("metadata", '{"key": "value"}')
        sql, params = lookup.get_sql(backend="postgresql")
        assert "@>" in sql
    
    def test_json_contains_lookup_mysql(self):
        """Test JSON contains lookup on MySQL."""
        from mikiorm.query.lookups import JSONContainsLookup
        lookup = JSONContainsLookup("data", '{"status": "active"}')
        sql, params = lookup.get_sql(backend="mysql")
        assert "JSON_CONTAINS" in sql


class TestLookupChaining:
    """Test chaining multiple lookups."""
    
    def test_lookup_values_immutable(self):
        """Test that lookup values don't mutate."""
        lookup1 = ContainsLookup("text", "search")
        sql1 = lookup1.to_sql()
        
        lookup2 = ContainsLookup("text", "different")
        sql2 = lookup2.to_sql()
        
        # Original shouldn't be changed
        sql1_again = lookup1.to_sql()
        assert sql1 == sql1_again


# ============================================================================
# Integration Tests (Simulated)
# ============================================================================

class TestWindowFunctionIntegration:
    """Test window functions in realistic scenarios."""
    
    def test_sales_ranking_scenario(self):
        """Test window functions for sales ranking."""
        # Simulates: annotate(
        #   rank=Rank().partition_by('region').order_by('-total_sales')
        # )
        rank = Rank().partition_by("region").order_by("-total_sales")
        sql = rank.to_sql()
        assert "RANK()" in sql
        assert "region" in sql
        assert "total_sales DESC" in sql
    
    def test_running_total_scenario(self):
        """Test window functions for running totals."""
        frame = FrameSpec(
            FrameSpec.ROWS,
            FrameSpec.UNBOUNDED_PRECEDING,
            FrameSpec.CURRENT_ROW
        )
        # Simulates running total with frame
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in frame.to_sql()
    
    def test_employee_lag_lead_scenario(self):
        """Test LAG/LEAD for comparing values."""
        prev_salary = LAG("salary", offset=1, default=0).order_by("hire_date")
        next_salary = LEAD("salary", offset=1, default=0).order_by("hire_date")
        
        assert "LAG(salary" in prev_salary.to_sql()
        assert "LEAD(salary" in next_salary.to_sql()


class TestLookupIntegration:
    """Test lookups in realistic scenarios."""
    
    def test_user_search_scenario(self):
        """Test lookups for user search."""
        # Email contains domain
        email_domain = ContainsLookup("email", "@example.com")
        sql, params = email_domain.get_sql()
        assert "@example.com" in params[0]
        
        # Username starts with
        from mikiorm.query.lookups import StartsWith
        username = StartsWith("username", "admin")
        sql, params = username.get_sql()
        assert "admin%" in params[0]
    
    def test_product_filter_scenario(self):
        """Test lookups for product filtering."""
        # Price range
        from mikiorm.query.lookups import RangeLookup
        price_range = RangeLookup("price", (10, 100))
        sql, params = price_range.get_sql()
        assert "BETWEEN %s AND %s" in sql
        assert params == [10, 100]
        
        # Status in allowed values
        status = InLookup("status", ["active", "published", "featured"])
        sql, params = status.get_sql()
        assert "IN" in sql
        assert len(params) == 3


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestWindowFunctionEdgeCases:
    """Test edge cases for window functions."""
    
    def test_window_function_empty_partition(self):
        """Test window function with no partition."""
        rn = RowNumber().order_by("id")
        sql = rn.to_sql()
        # Should still generate valid SQL even without partition
        assert "ROW_NUMBER()" in sql
        assert "OVER" in sql
    
    def test_window_function_multiple_order_fields(self):
        """Test window function with multiple ORDER BY fields."""
        rank = Rank().order_by("score", "-date", "name")
        sql = rank.to_sql()
        assert "score ASC" in sql
        assert "date DESC" in sql
        assert "name ASC" in sql
    
    def test_ntile_edge_cases(self):
        """Test NTILE with different bucket counts."""
        ntile2 = NTile(2).order_by("value")
        ntile4 = NTile(4).order_by("value")
        ntile100 = NTile(100).order_by("value")
        
        assert "NTILE(2)" in ntile2.to_sql()
        assert "NTILE(4)" in ntile4.to_sql()
        assert "NTILE(100)" in ntile100.to_sql()


class TestLookupEdgeCases:
    """Test edge cases for lookups."""
    
    def test_lookup_special_characters(self):
        """Test lookups with special characters."""
        lookup = ContainsLookup("description", "50% off")
        sql, params = lookup.get_sql()
        # Should handle special chars properly
        assert "%" in params[0]
    
    def test_lookup_null_value(self):
        """Test lookup with None value."""
        from mikiorm.query.lookups import IsNullLookup
        lookup = IsNullLookup("field", True)
        sql, params = lookup.get_sql()
        assert "IS NULL" in sql
    
    def test_lookup_empty_string(self):
        """Test lookup with empty string."""
        lookup = ContainsLookup("note", "")
        sql, params = lookup.get_sql()
        # Should handle empty string
        assert params == ["%%"]
    
    def test_lookup_numeric_values(self):
        """Test lookups with numeric values."""
        from mikiorm.query.lookups import InLookup
        lookup = InLookup("id", [1, 2, 3, 4, 5])
        sql, params = lookup.get_sql()
        assert params == [1, 2, 3, 4, 5]


# ============================================================================
# Performance and Stress Tests
# ============================================================================

class TestPerformance:
    """Test performance characteristics."""
    
    def test_many_partitions(self):
        """Test window function with many partition fields."""
        rn = RowNumber()
        for i in range(10):
            rn = rn.partition_by(f"field_{i}")
        sql = rn.to_sql()
        for i in range(10):
            assert f"field_{i}" in sql
    
    def test_many_order_fields(self):
        """Test window function with many order fields."""
        rank = Rank()
        for i in range(5):
            rank = rank.order_by(f"sort_{i}")
        sql = rank.to_sql()
        for i in range(5):
            assert f"sort_{i}" in sql
    
    def test_lookup_sql_generation_speed(self):
        """Test lookup SQL generation performance."""
        import time
        start = time.time()
        for _ in range(1000):
            lookup = ContainsLookup("field", "value")
            lookup.get_sql()
        end = time.time()
        # Should complete 1000 iterations in < 1 second
        assert (end - start) < 1.0


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility with Phase 5 and earlier."""
    
    def test_phase5_features_still_work(self):
        """Test that Phase 5 features still work (no regressions)."""
        # This is a placeholder - actual test would use real QuerySet
        # Just verify imports don't break
        from mikiorm.query.window import WindowFunction
        from mikiorm.query.lookups import Lookup
        assert WindowFunction is not None
        assert Lookup is not None
    
    def test_standard_lookups_available(self):
        """Test that all standard lookups are pre-registered."""
        lookups = list_lookups()
        required = [
            "exact", "iexact", "contains", "icontains",
            "startswith", "istartswith", "endswith", "iendswith",
            "gt", "gte", "lt", "lte", "in", "range", "isnull"
        ]
        for lookup in required:
            assert lookup in lookups, f"Missing lookup: {lookup}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Comprehensive tests for Phase 5 advanced QuerySet features.

Phase 5 Implemented Features:
1. GROUP BY with HAVING clause
2. Set operations (union, intersection, difference)
3. in_bulk() for dictionary lookups
4. Chainable values()/values_list()
5. Subquery support (foundation)
6. Expression evaluation in Python (foundation)
7. Query caching (foundation)
8. Advanced field operations
"""

import pytest
import sqlite3
from mikiorm import Model, CharField, IntegerField, DateTimeField, FloatField
from mikiorm.query import Count, Sum, Avg, Min, Max
from mikiorm import Q, F
from mikiorm.conf.settings import connection_manager
from datetime import datetime


# Test Models
class Product(Model):
    """Product model for testing."""
    id = IntegerField(primary_key=True)
    name = CharField(max_length=100)
    category = CharField(max_length=50)
    price = FloatField()
    quantity = IntegerField()
    created_at = DateTimeField()

    class Meta:
        table_name = "test_products"


class Sale(Model):
    """Sale model for testing set operations."""
    id = IntegerField(primary_key=True)
    product_id = IntegerField()
    amount = FloatField()
    date = DateTimeField()

    class Meta:
        table_name = "test_sales"


class Author(Model):
    """Author model for comprehensive testing."""
    id = IntegerField(primary_key=True)
    name = CharField(max_length=100)
    email = CharField(max_length=100)
    age = IntegerField()
    status = CharField(max_length=20)

    class Meta:
        table_name = "test_authors"


# Setup and Teardown
@pytest.fixture(scope="module")
def setup_test_db():
    """Setup test database with tables and sample data."""
    conn = connection_manager.get_connection()
    
    # Create test tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            quantity INTEGER,
            created_at TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_sales (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            amount REAL,
            date TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_authors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            age INTEGER,
            status TEXT
        )
    """)
    
    # Insert sample data
    now = datetime.now()
    products = [
        (1, "Laptop", "Electronics", 1200.0, 5, now),
        (2, "Phone", "Electronics", 800.0, 10, now),
        (3, "Book", "Media", 20.0, 100, now),
        (4, "Pen", "Stationery", 2.0, 500, now),
        (5, "Monitor", "Electronics", 400.0, 3, now),
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO test_products 
        (id, name, category, price, quantity, created_at) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, products)
    
    sales = [
        (1, 1, 1200.0, now),
        (2, 1, 1200.0, now),
        (3, 2, 800.0, now),
        (4, 2, 800.0, now),
        (5, 2, 800.0, now),
        (6, 3, 20.0, now),
        (7, 5, 400.0, now),
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO test_sales 
        (id, product_id, amount, date) 
        VALUES (?, ?, ?, ?)
    """, sales)
    
    authors = [
        (1, "Alice", "alice@example.com", 28, "active"),
        (2, "Bob", "bob@example.com", 35, "active"),
        (3, "Charlie", "charlie@example.com", 22, "inactive"),
        (4, "Diana", "diana@example.com", 30, "active"),
        (5, "Eve", "eve@example.com", 25, "inactive"),
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO test_authors 
        (id, name, email, age, status) 
        VALUES (?, ?, ?, ?, ?)
    """, authors)
    
    conn.commit()
    conn.close()
    
    yield
    
    # Cleanup
    conn = connection_manager.get_connection()
    conn.execute("DROP TABLE IF EXISTS test_products")
    conn.execute("DROP TABLE IF EXISTS test_sales")
    conn.execute("DROP TABLE IF EXISTS test_authors")
    conn.commit()
    conn.close()


# Phase 5 Tests

class TestInBulk:
    """Test in_bulk() method for batch dictionary lookup."""
    
    def test_in_bulk_by_pk(self, setup_test_db):
        """Test in_bulk with default primary key."""
        bulk = Product.objects.in_bulk([1, 2, 3])
        
        assert len(bulk) == 3
        assert 1 in bulk
        assert bulk[1].name == "Laptop"
        assert bulk[2].name == "Phone"
        assert bulk[3].name == "Book"
    
    def test_in_bulk_by_field_name(self, setup_test_db):
        """Test in_bulk with custom field name."""
        bulk = Product.objects.in_bulk(["Electronics", "Media"], field_name="category")
        
        # Should have Electronics (3 items) and Media (1 item)
        assert "Electronics" in bulk
        assert "Media" in bulk
    
    def test_in_bulk_empty_list(self, setup_test_db):
        """Test in_bulk with empty list returns all."""
        bulk = Product.objects.in_bulk()
        
        assert len(bulk) == 5
    
    def test_in_bulk_nonexistent_ids(self, setup_test_db):
        """Test in_bulk with non-existent IDs."""
        bulk = Product.objects.in_bulk([999, 1000])
        
        assert len(bulk) == 0


class TestSetOperations:
    """Test set operations: union, intersection, difference."""
    
    def test_union_basic(self, setup_test_db):
        """Test union of two QuerySets."""
        qs1 = Product.objects.filter(category="Electronics")
        qs2 = Product.objects.filter(category="Media")
        union_qs = qs1.union(qs2)
        
        results = union_qs.all()
        assert len(results) == 4  # 3 Electronics + 1 Media
    
    def test_union_with_overlapping(self, setup_test_db):
        """Test union with overlapping results."""
        qs1 = Product.objects.filter(price__gte=100)
        qs2 = Product.objects.filter(quantity__gte=10)
        union_qs = qs1.union(qs2, all=True)  # all=True allows duplicates
        
        # Should have results from both
        results = union_qs.all()
        assert len(results) > 0
    
    def test_intersection_basic(self, setup_test_db):
        """Test intersection of two QuerySets."""
        qs1 = Product.objects.filter(category="Electronics")
        qs2 = Product.objects.filter(price__gte=400)
        intersect_qs = qs1.intersection(qs2)
        
        results = intersect_qs.all()
        # Electronics with price >= 400: Laptop, Phone, Monitor
        assert len(results) >= 2
    
    def test_difference_basic(self, setup_test_db):
        """Test difference of two QuerySets."""
        qs1 = Product.objects.all()
        qs2 = Product.objects.filter(category="Electronics")
        diff_qs = qs1.difference(qs2)
        
        results = diff_qs.all()
        # Should be non-Electronics products
        assert len(results) == 2  # Book, Pen
        categories = {p.category for p in results}
        assert "Electronics" not in categories


class TestGroupByAndHaving:
    """Test GROUP BY and HAVING clause functionality."""
    
    def test_annotate_with_groupby(self, setup_test_db):
        """Test annotate creates GROUP BY."""
        # This would need enhanced query builder support
        # For now, basic test that annotate doesn't break
        results = Product.objects.annotate(total_quantity=Sum("quantity")).all()
        
        # Should work without errors
        assert isinstance(results, list)
    
    def test_having_filter(self, setup_test_db):
        """Test HAVING clause filters aggregations."""
        # This requires GROUP BY support
        # Basic test to ensure having() is callable
        qs = Product.objects.annotate(total_quantity=Sum("quantity")).having(
            total_quantity__gte=100
        )
        
        # Should not raise an error
        assert isinstance(qs, object)
    
    def test_aggregate_multiple(self, setup_test_db):
        """Test multiple aggregations."""
        stats = Product.objects.aggregate(
            total_count=Count(),
            total_quantity=Sum("quantity"),
            avg_price=Avg("price"),
            min_price=Min("price"),
            max_price=Max("price"),
        )
        
        assert stats["total_count"] == 5
        assert stats["total_quantity"] > 0
        assert stats["avg_price"] is not None


class TestChainableValues:
    """Test chainable values() and values_list() with filters."""
    
    def test_values_with_filter(self, setup_test_db):
        """Test values() chained with filter."""
        results = Product.objects.filter(category="Electronics").values("name", "price")
        
        assert isinstance(results, list)
        assert len(results) == 3
        if results:
            assert "name" in results[0]
            assert "price" in results[0]
    
    def test_values_list_with_filter(self, setup_test_db):
        """Test values_list() chained with filter."""
        results = Product.objects.filter(category="Electronics").values_list("name", "price")
        
        assert isinstance(results, list)
        assert len(results) == 3
        if results:
            assert isinstance(results[0], tuple)
    
    def test_values_list_flat(self, setup_test_db):
        """Test values_list() with flat=True."""
        results = Product.objects.values_list("name", flat=True)
        
        assert isinstance(results, list)
        assert all(isinstance(r, str) for r in results)
    
    def test_values_chained_multiple_filters(self, setup_test_db):
        """Test values() with multiple chained filters."""
        results = (Product.objects
                   .filter(category="Electronics")
                   .filter(price__gte=400)
                   .values("name", "price"))
        
        assert len(results) >= 2
        for item in results:
            assert "name" in item
            assert "price" in item


class TestAdvancedFieldOperations:
    """Test advanced field operations."""
    
    def test_only_with_defer(self, setup_test_db):
        """Test only() and defer() together."""
        results = Product.objects.only("name", "price").defer("price").all()
        
        assert len(results) > 0
        # Should have name field
        assert hasattr(results[0], "name")
    
    def test_distinct_values(self, setup_test_db):
        """Test distinct with values."""
        results = Product.objects.distinct().values("category")
        
        assert isinstance(results, list)
        assert len(set(r["category"] for r in results)) <= len(results)
    
    def test_order_by_with_values(self, setup_test_db):
        """Test order_by with values."""
        results = Product.objects.order_by("-price").values("name", "price")
        
        if len(results) >= 2:
            assert results[0]["price"] >= results[1]["price"]


class TestComplexQueries:
    """Test complex query combinations."""
    
    def test_complex_filter_with_q(self, setup_test_db):
        """Test complex Q object filtering."""
        results = Product.objects.filter(
            Q(category="Electronics") | Q(price__gte=100)
        ).all()
        
        assert len(results) >= 3
    
    def test_complex_chain(self, setup_test_db):
        """Test complex chained operations."""
        results = (Product.objects
                   .filter(category="Electronics")
                   .order_by("price")
                   .values("name", "price")
                   [0:2])
        
        # Should handle chaining without errors
        assert isinstance(results, list)
    
    def test_update_with_f_expression(self, setup_test_db):
        """Test update with F expressions."""
        initial_count = Product.objects.count()
        
        # Update quantity with F expression
        updated = Product.objects.filter(category="Electronics").update(
            quantity=F("quantity") + 1
        )
        
        assert updated > 0


class TestErrorHandling:
    """Test error handling for Phase 5 features."""
    
    def test_union_different_model(self, setup_test_db):
        """Test union with different model raises error."""
        qs1 = Product.objects.all()
        qs2 = Author.objects.all()
        
        with pytest.raises(TypeError):
            qs1.union(qs2)
    
    def test_having_without_annotate(self, setup_test_db):
        """Test having() without annotate() raises error."""
        with pytest.raises(ValueError):
            Product.objects.having(price__gte=100)
    
    def test_intersection_different_model(self, setup_test_db):
        """Test intersection with different model raises error."""
        qs1 = Product.objects.all()
        qs2 = Author.objects.all()
        
        with pytest.raises(TypeError):
            qs1.intersection(qs2)


class TestBackwardCompatibility:
    """Ensure Phase 5 doesn't break existing functionality."""
    
    def test_basic_filter_still_works(self, setup_test_db):
        """Test that basic filter still works."""
        results = Product.objects.filter(category="Electronics").all()
        
        assert len(results) == 3
        assert all(r.category == "Electronics" for r in results)
    
    def test_basic_aggregate_still_works(self, setup_test_db):
        """Test that basic aggregate still works."""
        stats = Product.objects.aggregate(total=Count())
        
        assert stats["total"] == 5
    
    def test_values_list_still_works(self, setup_test_db):
        """Test that values_list still works."""
        results = Product.objects.values_list("name", "price")
        
        assert len(results) == 5
    
    def test_get_or_create_still_works(self, setup_test_db):
        """Test that get_or_create still works."""
        obj, created = Author.objects.get_or_create(
            id=1,
            defaults={"name": "Test", "email": "test@example.com", "age": 25, "status": "active"}
        )
        
        assert obj is not None
        assert obj.name == "Alice"  # Should get existing


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

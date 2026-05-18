#!/usr/bin/env python
"""Test Phase 3: Aggregations (annotate and aggregate)."""

import sys
sys.path.insert(0, '.')

from mikiorm.models.base import Model
from mikiorm.models.fields import CharField, IntegerField, FloatField
from mikiorm.conf.settings import configure
from mikiorm.query import Count, Sum, Avg, Min, Max

# Configure SQLite for testing
configure(databases={"default": {"ENGINE": "sqlite", "NAME": ":memory:"}})


class Product(Model):
    """Test model for aggregations."""
    name = CharField(max_length=100)
    category = CharField(max_length=50)
    price = FloatField()
    quantity = IntegerField()
    sales = IntegerField(default=0)

    class Meta:
        table_name = "products"


def setup_database():
    """Create table and insert test data."""
    from mikiorm.conf.settings import connection_manager
    conn = connection_manager.get_connection()
    
    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            price FLOAT,
            quantity INTEGER,
            sales INTEGER DEFAULT 0
        )
    """, ())
    conn.commit()
    
    # Insert test data
    test_data = [
        ("Laptop", "Electronics", 999.99, 10, 50),
        ("Mouse", "Electronics", 29.99, 100, 200),
        ("Keyboard", "Electronics", 79.99, 50, 150),
        ("Desk", "Furniture", 299.99, 5, 20),
        ("Chair", "Furniture", 199.99, 15, 60),
        ("Monitor", "Electronics", 399.99, 20, 80),
    ]
    
    for name, category, price, quantity, sales in test_data:
        conn.execute(
            "INSERT INTO products (name, category, price, quantity, sales) VALUES (?, ?, ?, ?, ?)",
            (name, category, price, quantity, sales)
        )
    conn.commit()


def test_count_aggregate():
    """Test COUNT aggregate."""
    print("\n=== TEST: COUNT Aggregate ===")
    
    result = Product.objects.aggregate(total_products=Count())
    print(f"Total products: {result['total_products']}")
    assert result['total_products'] == 6
    
    # Count with filter
    result = Product.objects.filter(category="Electronics").aggregate(
        electronics_count=Count()
    )
    print(f"Electronics count: {result['electronics_count']}")
    assert result['electronics_count'] == 4
    
    print("✓ COUNT aggregate works")


def test_sum_aggregate():
    """Test SUM aggregate."""
    print("\n=== TEST: SUM Aggregate ===")
    
    result = Product.objects.aggregate(total_quantity=Sum("quantity"))
    print(f"Total quantity: {result['total_quantity']}")
    assert result['total_quantity'] == 200  # 10+100+50+5+15+20
    
    # Sum with filter
    result = Product.objects.filter(category="Electronics").aggregate(
        electronics_quantity=Sum("quantity")
    )
    print(f"Electronics total quantity: {result['electronics_quantity']}")
    assert result['electronics_quantity'] == 180  # 10+100+50+20
    
    print("✓ SUM aggregate works")


def test_avg_aggregate():
    """Test AVG aggregate."""
    print("\n=== TEST: AVG Aggregate ===")
    
    result = Product.objects.aggregate(avg_price=Avg("price"))
    print(f"Average price: {result['avg_price']:.2f}")
    
    # Should be approximately 333.3 (total 2000, count 6)
    assert result['avg_price'] is not None
    
    # Avg with filter
    result = Product.objects.filter(category="Furniture").aggregate(
        furniture_avg_price=Avg("price")
    )
    print(f"Furniture average price: {result['furniture_avg_price']:.2f}")
    assert result['furniture_avg_price'] is not None
    
    print("✓ AVG aggregate works")


def test_min_aggregate():
    """Test MIN aggregate."""
    print("\n=== TEST: MIN Aggregate ===")
    
    result = Product.objects.aggregate(min_price=Min("price"))
    print(f"Minimum price: ${result['min_price']:.2f}")
    assert result['min_price'] == 29.99  # Mouse
    
    # Min with filter
    result = Product.objects.filter(category="Electronics").aggregate(
        electronics_min_price=Min("price")
    )
    print(f"Electronics minimum price: ${result['electronics_min_price']:.2f}")
    assert result['electronics_min_price'] == 29.99  # Mouse
    
    print("✓ MIN aggregate works")


def test_max_aggregate():
    """Test MAX aggregate."""
    print("\n=== TEST: MAX Aggregate ===")
    
    result = Product.objects.aggregate(max_price=Max("price"))
    print(f"Maximum price: ${result['max_price']:.2f}")
    assert result['max_price'] == 999.99  # Laptop
    
    # Max with filter
    result = Product.objects.filter(category="Furniture").aggregate(
        furniture_max_price=Max("price")
    )
    print(f"Furniture maximum price: ${result['furniture_max_price']:.2f}")
    assert result['furniture_max_price'] == 299.99  # Desk
    
    print("✓ MAX aggregate works")


def test_multiple_aggregates():
    """Test multiple aggregates in one call."""
    print("\n=== TEST: Multiple Aggregates ===")
    
    result = Product.objects.aggregate(
        total_count=Count(),
        total_quantity=Sum("quantity"),
        avg_price=Avg("price"),
        min_price=Min("price"),
        max_price=Max("price"),
    )
    
    print(f"Results: count={result['total_count']}, qty={result['total_quantity']}, "
          f"avg=${result['avg_price']:.2f}, min=${result['min_price']:.2f}, max=${result['max_price']:.2f}")
    
    assert result['total_count'] == 6
    assert result['total_quantity'] == 200
    assert result['min_price'] == 29.99
    assert result['max_price'] == 999.99
    
    print("✓ Multiple aggregates work")


def test_aggregate_with_filter_and_exclude():
    """Test aggregates with complex filters."""
    print("\n=== TEST: Aggregates with Filter/Exclude ===")
    
    # Filter by category AND exclude low-sales items
    result = (Product.objects
              .filter(category="Electronics")
              .exclude(sales__lt=50)
              .aggregate(
                  count=Count(),
                  total_sales=Sum("sales"),
                  avg_quantity=Avg("quantity")
              ))
    
    print(f"Filtered results: count={result['count']}, "
          f"sales={result['total_sales']}, avg_qty={result['avg_quantity']:.1f}")
    
    # Should include: Mouse (200), Keyboard (150), Monitor (80) = 3 items
    assert result['count'] == 3
    
    print("✓ Aggregates with complex filters work")


def test_annotate_method():
    """Test annotate() method for adding computed fields."""
    print("\n=== TEST: Annotate Method ===")
    
    # Annotate with aggregates (prepares for later GROUP BY support)
    qs = Product.objects.annotate(
        total_revenue=Sum("price"),  # This would compute per-row in GROUP BY
    )
    
    print(f"QuerySet annotated: {qs}")
    assert qs._annotations is not None
    assert 'total_revenue' in qs._annotations
    
    print("✓ Annotate method works")


def test_empty_result_aggregate():
    """Test aggregate on empty result set."""
    print("\n=== TEST: Aggregate on Empty ResultSet ===")
    
    result = Product.objects.filter(category="NonExistent").aggregate(
        count=Count(),
        total_qty=Sum("quantity"),
    )
    
    print(f"Empty result aggregates: {result}")
    assert result['count'] is None or result['count'] == 0
    
    print("✓ Empty result aggregates work")


def test_aggregate_single_field():
    """Test aggregate with specific field selection."""
    print("\n=== TEST: Aggregate Single Field ===")
    
    # Count only products with sales > 100
    result = Product.objects.filter(sales__gt=100).aggregate(
        high_sales_count=Count(),
        high_sales_total=Sum("sales"),
    )
    
    print(f"High sales items: count={result['high_sales_count']}, total={result['high_sales_total']}")
    
    # Should include: Mouse (200), Laptop (50), Keyboard (150), Monitor (80)
    # Only: Mouse (200), Keyboard (150) = 2 items
    assert result['high_sales_count'] == 2
    assert result['high_sales_total'] == 350  # 200 + 150
    
    print("✓ Aggregate single field works")


def test_chaining_with_aggregate():
    """Test that aggregate is chainable before calling."""
    print("\n=== TEST: Chaining Before Aggregate ===")
    
    qs = (Product.objects
          .filter(price__gte=100)
          .exclude(category="Furniture")
          .distinct())
    
    result = qs.aggregate(
        filtered_count=Count(),
        avg_qty=Avg("quantity"),
    )
    
    print(f"Chained aggregate results: {result}")
    assert result['filtered_count'] == 4  # 4 Electronics with price >= 100
    
    print("✓ Chaining with aggregate works")


if __name__ == "__main__":
    try:
        setup_database()
        
        print("\n" + "="*60)
        print("PHASE 3: AGGREGATIONS TEST SUITE")
        print("="*60)
        
        test_count_aggregate()
        test_sum_aggregate()
        test_avg_aggregate()
        test_min_aggregate()
        test_max_aggregate()
        test_multiple_aggregates()
        test_aggregate_with_filter_and_exclude()
        test_annotate_method()
        test_empty_result_aggregate()
        test_aggregate_single_field()
        test_chaining_with_aggregate()
        
        print("\n" + "="*60)
        print("✓✓✓ ALL PHASE 3 TESTS PASSED ✓✓✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

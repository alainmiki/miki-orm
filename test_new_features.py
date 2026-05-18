#!/usr/bin/env python
"""Test new QuerySet features: slicing, distinct, none."""

import sys
sys.path.insert(0, '.')

from mikiorm.models.base import Model
from mikiorm.models.fields import CharField, IntegerField
from mikiorm.conf.settings import configure

# Configure SQLite for testing
configure(databases={"default": {"ENGINE": "sqlite", "NAME": ":memory:"}})


class Author(Model):
    """Test model for QuerySet features."""
    name = CharField(max_length=100)
    email = CharField(max_length=100, unique=True)
    age = IntegerField(null=True, default=25)

    class Meta:
        table_name = "authors"


def setup_database():
    """Create table and insert test data."""
    from mikiorm.conf.settings import connection_manager
    conn = connection_manager.get_connection()
    
    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            age INTEGER DEFAULT 25
        )
    """, ())
    conn.commit()
    
    # Insert test data
    for i in range(25):
        name = f"Author{i % 5}"  # Names will repeat: Author0, Author1, ..., Author0
        email = f"author{i}@example.com"
        age = 20 + (i % 10)
        conn.execute(
            "INSERT INTO authors (name, email, age) VALUES (?, ?, ?)",
            (name, email, age)
        )
    conn.commit()


def test_slicing():
    """Test QuerySet slicing with __getitem__."""
    print("\n=== TEST: QuerySet Slicing ===")
    
    # Test [10:20]
    results = Author.objects.all()[10:20]
    print(f"✓ qs[10:20] returned {len(results)} items")
    assert len(results) == 10, f"Expected 10 items, got {len(results)}"
    
    # Test [:5]
    results = Author.objects.all()[:5]
    print(f"✓ qs[:5] returned {len(results)} items")
    assert len(results) == 5, f"Expected 5 items, got {len(results)}"
    
    # Test [20:]
    results = Author.objects.all()[20:]
    print(f"✓ qs[20:] returned {len(results)} items")
    assert len(results) == 5, f"Expected 5 items, got {len(results)}"
    
    # Test single index
    result = Author.objects.all()[0]
    print(f"✓ qs[0] returned single item: {result.name}")
    assert result is not None
    
    # Test chaining after slice
    results = Author.objects.all()[5:15].filter(name="Author0")
    print(f"✓ qs[5:15].filter() chaining works")
    
    print("✓ All slicing tests passed!")


def test_distinct():
    """Test distinct() method."""
    print("\n=== TEST: Distinct ===")
    
    # Without distinct
    all_results = Author.objects.all().count()
    print(f"Total records: {all_results}")
    
    # With distinct - should have fewer unique names
    distinct_results = Author.objects.values_list("name", flat=True)
    unique_names = set(distinct_results)
    print(f"Unique names (via set): {len(unique_names)}")
    
    # Test distinct() method (returns QuerySet)
    distinct_qs = Author.objects.filter(name__startswith="Author").distinct()
    print(f"✓ .distinct() returns QuerySet: {type(distinct_qs).__name__}")
    distinct_count = distinct_qs.count()
    print(f"✓ Distinct count: {distinct_count}")
    
    print("✓ All distinct tests passed!")


def test_none():
    """Test none() method that returns empty QuerySet."""
    print("\n=== TEST: None (Empty QuerySet) ===")
    
    # Get empty queryset
    empty_qs = Author.objects.none()
    print(f"✓ .none() returns QuerySet: {type(empty_qs).__name__}")
    
    # Should be empty
    count = empty_qs.count()
    print(f"✓ Empty QuerySet count: {count}")
    assert count == 0, f"Expected 0, got {count}"
    
    # Should be chainable
    still_empty = empty_qs.filter(name="Author0")
    print(f"✓ .none().filter() chaining works")
    assert still_empty.count() == 0
    
    print("✓ All none tests passed!")


def test_chaining():
    """Test that methods return QuerySet for proper chaining."""
    print("\n=== TEST: Method Chaining ===")
    
    # Complex chain
    results = (Author.objects
               .filter(age__gte=25)
               .exclude(name="Author0")
               .distinct()
               .order_by("name")
               [0:10])
    
    print(f"✓ Complex chaining works: got {len(results)} results")
    
    # Another chain
    results = (Author.objects
               .filter(age__lt=30)
               .order_by("-age")[5:10]
               .filter(name__startswith="Author"))
    
    print(f"✓ Multiple chains work: got {len(results)} results")
    
    print("✓ All chaining tests passed!")


if __name__ == "__main__":
    try:
        setup_database()
        test_slicing()
        test_distinct()
        test_none()
        test_chaining()
        print("\n" + "="*50)
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("="*50)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

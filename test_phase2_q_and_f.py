#!/usr/bin/env python
"""Test Phase 2: Q objects and F expressions integration."""

import sys
sys.path.insert(0, '.')

from mikiorm.models.base import Model
from mikiorm.models.fields import CharField, IntegerField
from mikiorm.conf.settings import configure
from mikiorm import Q, F

# Configure SQLite for testing
configure(databases={"default": {"ENGINE": "sqlite", "NAME": ":memory:"}})


class Author(Model):
    """Test model."""
    name = CharField(max_length=100)
    email = CharField(max_length=100, unique=True)
    age = IntegerField(null=True, default=25)
    views = IntegerField(default=0)

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
            age INTEGER DEFAULT 25,
            views INTEGER DEFAULT 0
        )
    """, ())
    conn.commit()
    
    # Insert test data
    test_data = [
        ("Alice", "alice@example.com", 25, 100),
        ("Bob", "bob@example.com", 30, 150),
        ("Charlie", "charlie@example.com", 20, 50),
        ("Diana", "diana@example.com", 35, 200),
        ("Eve", "eve@example.com", 22, 75),
    ]
    
    for name, email, age, views in test_data:
        conn.execute(
            "INSERT INTO authors (name, email, age, views) VALUES (?, ?, ?, ?)",
            (name, email, age, views)
        )
    conn.commit()


def test_q_or_logic():
    """Test Q objects with OR logic."""
    print("\n=== TEST: Q Objects - OR Logic ===")
    
    # Test Q(age=25) | Q(age=30)
    results = Author.objects.filter(Q(age=25) | Q(age=30)).all()
    names = [r.name for r in results]
    print(f"Results for Q(age=25) | Q(age=30): {names}")
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    assert "Alice" in names and "Bob" in names
    print("✓ Q OR logic works")


def test_q_and_logic():
    """Test Q objects with AND logic."""
    print("\n=== TEST: Q Objects - AND Logic ===")
    
    # Test Q(age__gte=25) & Q(name="Alice")
    results = Author.objects.filter(Q(age__gte=25) & Q(name="Alice")).all()
    print(f"Results for Q(age__gte=25) & Q(name='Alice'): {len(results)} found")
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0].name == "Alice"
    print("✓ Q AND logic works")


def test_q_not_logic():
    """Test Q objects with NOT logic."""
    print("\n=== TEST: Q Objects - NOT Logic ===")
    
    # Test ~Q(age=25)
    results = Author.objects.filter(~Q(age=25)).all()
    print(f"Results for ~Q(age=25): {len(results)} found (should exclude Alice)")
    assert len(results) == 4, f"Expected 4 results, got {len(results)}"
    names = [r.name for r in results]
    assert "Alice" not in names
    print("✓ Q NOT logic works")


def test_q_complex_logic():
    """Test complex Q object combinations."""
    print("\n=== TEST: Q Objects - Complex Logic ===")
    
    # (age >= 25 AND views >= 100) OR (age < 25)
    q = (Q(age__gte=25, views__gte=100) | Q(age__lt=25))
    results = Author.objects.filter(q).all()
    print(f"Complex Q filter results: {len(results)} found")
    # Should include: Alice (25, 100), Bob (30, 150), Diana (35, 200), Charlie (20, 50), Eve (22, 75)
    # = all 5 authors
    assert len(results) == 5
    print("✓ Complex Q logic works")


def test_q_exclude():
    """Test Q objects with exclude()."""
    print("\n=== TEST: Q Objects - Exclude ===")
    
    # exclude Q(age__lt=25)
    results = Author.objects.exclude(Q(age__lt=25)).all()
    print(f"Results excluding Q(age__lt=25): {len(results)} found")
    # Should exclude: Charlie (20), Eve (22)
    # Should include: Alice (25), Bob (30), Diana (35)
    assert len(results) == 3, f"Expected 3 results, got {len(results)}"
    names = [r.name for r in results]
    assert "Charlie" not in names and "Eve" not in names
    print("✓ Q exclude works")


def test_q_with_filter_chain():
    """Test Q objects chained with other filters."""
    print("\n=== TEST: Q Objects - Chained with filter() ===")
    
    # filter(Q(age__gte=25)).filter(name__startswith="A")
    results = Author.objects.filter(Q(age__gte=25)).filter(name__startswith="A").all()
    print(f"Results for Q(age__gte=25).filter(name__startswith='A'): {len(results)}")
    assert len(results) == 2  # Alice and Diana
    names = [r.name for r in results]
    assert all(n in ["Alice", "Diana"] for n in names)
    print("✓ Q chaining with filter works")


def test_f_expression_update():
    """Test F expressions in update()."""
    print("\n=== TEST: F Expressions - Update ===")
    
    # Update views for age >= 30
    updated_count = Author.objects.filter(age__gte=30).update(views=F("views") + 10)
    print(f"Updated {updated_count} rows with F('views') + 10")
    
    # Verify updates
    bob = Author.objects.get(name="Bob")
    assert bob.views == 160, f"Expected 160, got {bob.views}"  # 150 + 10
    
    diana = Author.objects.get(name="Diana")
    assert diana.views == 210, f"Expected 210, got {diana.views}"  # 200 + 10
    
    # Charlie (20) should not be updated
    charlie = Author.objects.get(name="Charlie")
    assert charlie.views == 50, f"Expected 50, got {charlie.views}"
    
    print("✓ F expression update works")


def test_f_expression_multiply():
    """Test F expressions with multiplication."""
    print("\n=== TEST: F Expressions - Multiply ===")
    
    # Reset views
    Author.objects.all().update(views=10)
    
    # Multiply views by 2
    Author.objects.all().update(views=F("views") * 2)
    
    # Verify
    results = Author.objects.all()
    for author in results:
        assert author.views == 20, f"Expected 20, got {author.views}"
    
    print("✓ F expression multiplication works")


def test_f_expression_subtract():
    """Test F expressions with subtraction."""
    print("\n=== TEST: F Expressions - Subtract ===")
    
    # Reset views
    Author.objects.all().update(views=100)
    
    # Subtract 10 from views
    Author.objects.all().update(views=F("views") - 10)
    
    # Verify
    results = Author.objects.all()
    for author in results:
        assert author.views == 90, f"Expected 90, got {author.views}"
    
    print("✓ F expression subtraction works")


def test_q_and_filter_mixed():
    """Test mixing Q objects with regular filters."""
    print("\n=== TEST: Mixed Q and Keyword Filters ===")
    
    # filter(Q(age__gte=25), name="Alice") - should AND them
    results = Author.objects.filter(Q(age__gte=25), name="Alice").all()
    print(f"Results for Q(age__gte=25), name='Alice': {len(results)}")
    assert len(results) == 1
    assert results[0].name == "Alice"
    print("✓ Mixed Q and keyword filters work")


def test_multiple_q_filters():
    """Test multiple Q objects in filter."""
    print("\n=== TEST: Multiple Q Objects ===")
    
    # filter(Q(...), Q(...), keyword=value)
    results = Author.objects.filter(Q(age__gte=25), Q(name__startswith="A")).all()
    print(f"Results for two Q objects: {len(results)}")
    # Should include Alice (25, starts with A), Diana (35, but doesn't start with A)
    # = only Alice
    assert len(results) == 1
    assert results[0].name == "Alice"
    print("✓ Multiple Q objects work")


def test_q_complex_nested():
    """Test deeply nested Q objects."""
    print("\n=== TEST: Nested Q Objects ===")
    
    # ((age=25 OR age=30) AND views >= 100)
    q = (Q(age=25) | Q(age=30)) & Q(views__gte=100)
    results = Author.objects.filter(q).all()
    print(f"Results for nested Q: {len(results)}")
    # Alice: age=25, views=100 ✓
    # Bob: age=30, views=150+ ✓
    assert len(results) == 2
    print("✓ Nested Q objects work")


if __name__ == "__main__":
    try:
        setup_database()
        
        print("\n" + "="*60)
        print("PHASE 2: Q OBJECTS AND F EXPRESSIONS TEST SUITE")
        print("="*60)
        
        # Q object tests
        test_q_or_logic()
        test_q_and_logic()
        test_q_not_logic()
        test_q_complex_logic()
        test_q_exclude()
        test_q_with_filter_chain()
        test_q_and_filter_mixed()
        test_multiple_q_filters()
        test_q_complex_nested()
        
        # F expression tests
        test_f_expression_update()
        test_f_expression_multiply()
        test_f_expression_subtract()
        
        print("\n" + "="*60)
        print("✓✓✓ ALL PHASE 2 TESTS PASSED ✓✓✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

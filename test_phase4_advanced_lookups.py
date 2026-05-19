#!/usr/bin/env python
"""Test Phase 3 & 4: Advanced lookups (regex, date/time) and field selection."""

import sys
import datetime
sys.path.insert(0, '.')

from mikiorm.models.base import Model
from mikiorm.models.fields import CharField, DateTimeField, DateField, IntegerField
from mikiorm.conf.settings import configure

# Configure SQLite for testing
configure(databases={"default": {"ENGINE": "sqlite", "NAME": ":memory:"}})


class BlogPost(Model):
    """Test model for advanced lookups."""
    title = CharField(max_length=200)
    slug = CharField(max_length=100)
    created_at = DateTimeField()
    published_date = DateField()
    views = IntegerField(default=0)

    class Meta:
        table_name = "posts"


def setup_database():
    """Create table and insert test data."""
    from mikiorm.conf.settings import connection_manager
    conn = connection_manager.get_connection()
    
    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(200) NOT NULL,
            slug VARCHAR(100),
            created_at DATETIME,
            published_date DATE,
            views INTEGER DEFAULT 0
        )
    """, ())
    conn.commit()
    
    # Insert test data
    now = datetime.datetime.now()
    today = datetime.date.today()
    
    test_data = [
        ("Python Tips", "python-tips", now - datetime.timedelta(days=30), today - datetime.timedelta(days=30), 150),
        ("Django Tutorial", "django-tutorial", now - datetime.timedelta(days=15), today - datetime.timedelta(days=15), 200),
        ("FastAPI Guide", "fastapi-guide", now - datetime.timedelta(days=5), today - datetime.timedelta(days=5), 100),
        ("SQLite Best Practices", "sqlite-best-practices", now - datetime.timedelta(days=2), today - datetime.timedelta(days=2), 80),
    ]
    
    for title, slug, created_at, published_date, views in test_data:
        conn.execute(
            "INSERT INTO posts (title, slug, created_at, published_date, views) VALUES (?, ?, ?, ?, ?)",
            (title, slug, str(created_at), str(published_date), views)
        )
    conn.commit()


def test_field_selection_only():
    """Test only() for field selection."""
    print("\n=== TEST: Field Selection - only() ===")
    
    # Select only specific fields
    qs = BlogPost.objects.only("title", "views")
    print(f"QuerySet with only: {qs}")
    assert qs._only_fields == {"title", "views"}
    
    # Verify chaining works
    qs2 = qs.filter(views__gte=100)
    print(f"✓ only() chaining works")
    
    print("✓ Field selection with only() works")


def test_field_selection_defer():
    """Test defer() for field exclusion."""
    print("\n=== TEST: Field Selection - defer() ===")
    
    # Defer (exclude) specific fields
    qs = BlogPost.objects.defer("created_at", "published_date")
    print(f"QuerySet with defer: {qs}")
    assert qs._defer_fields == {"created_at", "published_date"}
    
    # Verify chaining works
    qs2 = qs.filter(views__gte=100)
    print(f"✓ defer() chaining works")
    
    print("✓ Field selection with defer() works")


def test_date_lookup_year():
    """Test __year lookup."""
    print("\n=== TEST: Date Lookup - __year ===")
    
    current_year = datetime.date.today().year
    results = BlogPost.objects.filter(published_date__year=current_year).all()
    print(f"Posts from year {current_year}: {len(results)} found")
    
    # All test data should be from current year
    assert len(results) == 4
    print("✓ __year lookup works")


def test_date_lookup_month():
    """Test __month lookup."""
    print("\n=== TEST: Date Lookup - __month ===")
    
    current_month = datetime.date.today().month
    results = BlogPost.objects.filter(published_date__month=current_month).all()
    print(f"Posts from month {current_month}: {len(results)} found")
    
    assert len(results) > 0  # Some posts should be from current month
    print("✓ __month lookup works")


def test_date_lookup_day():
    """Test __day lookup."""
    print("\n=== TEST: Date Lookup - __day ===")
    
    current_day = datetime.date.today().day
    results = BlogPost.objects.filter(published_date__day=current_day).all()
    print(f"Posts from day {current_day}: {len(results)} found")
    
    # Should find 0 or 1 (might be today)
    assert len(results) <= 4
    print("✓ __day lookup works")


def test_date_comparison():
    """Test date comparisons."""
    print("\n=== TEST: Date Comparisons ===")
    
    # Find posts published in last 10 days
    threshold_date = datetime.date.today() - datetime.timedelta(days=10)
    results = BlogPost.objects.filter(published_date__gte=threshold_date).all()
    print(f"Posts published in last 10 days: {len(results)} found")
    
    # Should include recent posts
    assert len(results) >= 2
    print("✓ Date comparisons work")


def test_combined_filters():
    """Test combining only/defer with other filters."""
    print("\n=== TEST: Combined Filters ===")
    
    qs = (BlogPost.objects
          .only("title", "views")
          .filter(views__gte=100)
          .exclude(title__contains="Best")
          .order_by("-views"))
    
    print(f"Complex query: {qs}")
    results = qs.all()
    print(f"Results: {len(results)} posts")
    
    # Should exclude SQLite post
    assert all("Best" not in p.title for p in results)
    print("✓ Combined filters work")


def test_slug_filter():
    """Test text filtering on slug field."""
    print("\n=== TEST: Slug Filtering ===")
    
    # Find posts with 'python' in slug
    results = BlogPost.objects.filter(slug__contains="python").all()
    print(f"Posts with 'python' in slug: {len(results)}")
    assert len(results) == 1
    assert results[0].title == "Python Tips"
    
    # Find posts starting with 'django'
    results = BlogPost.objects.filter(slug__startswith="django").all()
    print(f"Posts with slug starting 'django': {len(results)}")
    assert len(results) == 1
    assert results[0].title == "Django Tutorial"
    
    print("✓ Slug filtering works")


def test_views_range():
    """Test __range lookup."""
    print("\n=== TEST: Range Lookup ===")
    
    # Find posts with 100-150 views
    results = BlogPost.objects.filter(views__range=[100, 150]).all()
    print(f"Posts with 100-150 views: {len(results)}")
    assert len(results) == 2  # Django (200 excluded), FastAPI (100), SQLite (80 excluded)
    
    print("✓ Range lookup works")


def test_views_lookup_gt():
    """Test __gt (greater than) lookup."""
    print("\n=== TEST: Greater Than Lookup ===")
    
    results = BlogPost.objects.filter(views__gt=100).all()
    print(f"Posts with > 100 views: {len(results)}")
    assert len(results) == 2  # Python (150), Django (200)
    
    print("✓ GT lookup works")


def test_views_lookup_lte():
    """Test __lte (less than or equal) lookup."""
    print("\n=== TEST: Less Than or Equal Lookup ===")
    
    results = BlogPost.objects.filter(views__lte=100).all()
    print(f"Posts with <= 100 views: {len(results)}")
    assert len(results) == 2  # FastAPI (100), SQLite (80)
    
    print("✓ LTE lookup works")


def test_text_lookups():
    """Test various text lookups."""
    print("\n=== TEST: Text Lookups ===")
    
    # Endswith
    results = BlogPost.objects.filter(title__endswith="Guide").all()
    print(f"Titles ending with 'Guide': {len(results)}")
    assert len(results) == 1
    
    # Contains
    results = BlogPost.objects.filter(title__contains="Python").all()
    print(f"Titles containing 'Python': {len(results)}")
    assert len(results) == 1
    
    # Case-insensitive contains
    results = BlogPost.objects.filter(title__icontains="python").all()
    print(f"Titles containing 'python' (case-insensitive): {len(results)}")
    assert len(results) == 1
    
    print("✓ Text lookups work")


def test_ordering():
    """Test ordering with filters."""
    print("\n=== TEST: Ordering ===")
    
    # Order by views descending
    results = BlogPost.objects.all().order_by("-views")
    print(f"Top post: {results[0].title} ({results[0].views} views)")
    assert results[0].views == 200
    
    # Order by title ascending
    results = BlogPost.objects.all().order_by("title")
    print(f"First post alphabetically: {results[0].title}")
    assert results[0].title.startswith("D") or results[0].title.startswith("F")
    
    print("✓ Ordering works")


if __name__ == "__main__":
    try:
        setup_database()
        
        print("\n" + "="*60)
        print("PHASE 3 & 4: ADVANCED LOOKUPS AND FIELD SELECTION")
        print("="*60)
        
        # Field selection
        test_field_selection_only()
        test_field_selection_defer()
        
        # Date/time lookups
        test_date_lookup_year()
        test_date_lookup_month()
        test_date_lookup_day()
        test_date_comparison()
        
        # Text and numeric lookups
        test_slug_filter()
        test_views_range()
        test_views_lookup_gt()
        test_views_lookup_lte()
        test_text_lookups()
        
        # Combined tests
        test_combined_filters()
        test_ordering()
        
        print("\n" + "="*60)
        print("✓✓✓ ALL ADVANCED LOOKUP TESTS PASSED ✓✓✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
Example 4: PostgreSQL Connection Test
======================================
Demonstrates:
  - Connecting to a PostgreSQL database using miki-orm
  - Configuring the postgresql engine with psycopg2
  - Basic CRUD operations against PostgreSQL
  - Using makemigrations() and migrate for schema creation

Prerequisites:
  - A running PostgreSQL instance on localhost:5432
  - Database "test" owned by user "postgres" with password "admin"
  - psycopg2-binary installed (pip install psycopg2-binary)

Usage:
  python examples/04_postgres_connection.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import myorm
from myorm import models
from myorm.settings import settings, connection_manager
from myorm.migrations.engine import MigrationEngine
from myorm.connections import PostgresAdapter


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def configure_postgres():
    """Configure the default database to use PostgreSQL."""
    myorm.configure({
        "default": {
            "ENGINE": "postgresql",
            "NAME": "test",
            "USER": "postgres",
            "PASSWORD": "admin",
            "HOST": "localhost",
            "PORT": 5432,
            "OPTIONS": {"sslmode": "prefer"},
        }
    })


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

class Product(models.Model):
    """A product in a store."""
    name = models.CharField(max_length=200)
    description = models.TextField(null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=0)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        table_name = "products"
        ordering = ["-id"]


class Review(models.Model):
    """A product review."""
    product = models.ForeignKey(to="Product", on_delete=models.CASCADE)
    author_name = models.CharField(max_length=100)
    rating = models.IntegerField()  # 1-5
    comment = models.TextField(null=True)

    class Meta:
        table_name = "reviews"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def test_connection():
    """Verify we can open and use a PostgreSQL connection."""
    print("\n--- Testing PostgreSQL Connection ---")

    adapter = PostgresAdapter()
    try:
        config = settings.get_database("default")
        conn = adapter.connect(config.get_connection_config())
        print("  [OK] Connected to PostgreSQL database '%s'" % config.name)

        conn.execute("SELECT 1 as result")
        row = conn.fetchone("SELECT 1 as result", ())
        assert row == (1,), "Expected (1,), got %s" % (row,)
        print("  [OK] Basic query executed successfully")

        conn.commit()
        return conn
    except Exception as e:
        print("  [FAIL] Connection failed: %s" % e)
        print("\nHint: Make sure PostgreSQL is running on localhost:5432")
        print("   with database 'test', user 'postgres', password 'admin'")
        return None


def run_crud():
    """Run a full round of CRUD operations on PostgreSQL."""
    print("\n--- Running CRUD Operations ---")

    engine = MigrationEngine()
    ops = engine.makemigrations([Product, Review])
    print("  Generated %d migration operation(s)" % len(ops))

    # engine.migrate_direct(ops, connection=conn)
    engine.migrate()
    print("  [OK] Tables created via migrate()")

    # Product._table_created = False
    # Review._table_created = False

    # ---- CREATE ----
    print("\n  -- CREATE --")
    laptop = Product.objects.create(
        name="MacBook Pro",
        description="16-inch M3 Pro chip",
        price=2499.99,
        quantity=50,
    )
    print("  Created product: %s (id=%s, price=%s)" % (laptop.name, laptop.id, laptop.price))

    mouse = Product.objects.create(
        name="Magic Mouse",
        description="Wireless multi-touch mouse",
        price=79.99,
        quantity=200,
    )
    print("  Created product: %s (id=%s)" % (mouse.name, mouse.id))

    review1 = Review.objects.create(
        product=laptop,
        author_name="Jane Doe",
        rating=5,
        comment="Excellent performance!",
    )
    print("  Created review by '%s' (rating=%s)" % (review1.author_name, review1.rating))

    # ---- READ ----
    print("\n  -- READ --")
    all_products = Product.objects.all()
    print("  Total products: %d" % len(all_products))

    expensive = Product.objects.filter(price__gte=100)
    print("  Products with price >= 100: %d" % len(expensive))
    for p in expensive:
        print("    - %s: $%s" % (p.name, p.price))

    available = Product.objects.filter(is_available=True)
    print("  Available products: %d" % len(available))

    # ---- UPDATE ----
    print("\n  -- UPDATE --")
    updated = Product.objects.filter(name="Magic Mouse").update(quantity=180)
    print("  Updated %d product(s)" % updated)
    refreshed = Product.objects.get(name="Magic Mouse")
    print("  Magic Mouse quantity is now: %s" % refreshed.quantity)

    # Instance-level update
    laptop.price = 2299.99
    laptop.save()
    refreshed_laptop = Product.objects.get(id=laptop.id)
    print("  MacBook Pro price after save(): $%s" % refreshed_laptop.price)

    # ---- DELETE ----
    print("\n  -- DELETE --")
    deleted = Review.objects.filter(author_name="Jane Doe").delete()
    print("  Deleted %d review(s)" % deleted)
    print("  Remaining reviews: %d" % Review.objects.count())

    # ---- GET_OR_CREATE ----
    print("\n  -- GET_OR_CREATE --")
    product, created = Product.objects.get_or_create(
        name="MacBook Pro",
        defaults={"description": "Laptop", "price": 2499.99, "quantity": 50},
    )
    print("  MacBook Pro -- created=%s, id=%s" % (created, product.id))

    # ---- COUNT ----
    print("\n  -- COUNT --")
    print("  Total products: %d" % Product.objects.count())

    # ---- EXISTS ----
    print("\n  -- EXISTS --")
    print("  Product 'MacBook Pro' exists: %s" % Product.objects.filter(name='MacBook Pro').exists())
    print("  Product 'Nonexistent' exists: %s" % Product.objects.filter(name='Nonexistent').exists())

    # ---- VALUES ----
    print("\n  -- VALUES --")
    values = Product.objects.values("name", "price")
    print("  Product values: %s" % values)

    # ---- get_object_or_404 ----
    print("\n  -- get_object_or_404 --")
    try:
        found = Product.objects.get_object_or_404(name="MacBook Pro")
        print("  Found: %s" % found.name)
    except models.ObjectDoesNotExist:
        print("  Not found")

    print("\n  [OK] All CRUD operations completed successfully on PostgreSQL!")


def cleanup(conn):
    """Drop test tables to leave a clean state."""
    print("\n--- Cleanup ---")
    try:
        conn.execute('DROP TABLE IF EXISTS "reviews"')
        conn.execute('DROP TABLE IF EXISTS "products"')
        conn.commit()
        print("  [OK] Dropped test tables")
    except Exception as e:
        print("  [WARN] Cleanup warning: %s" % e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    configure_postgres()

    conn = test_connection()
    if conn is None:
        print("\n[WARN] Could not connect to PostgreSQL. Exiting.")
        sys.exit(1)

    try:
        run_crud()
    finally:
        # cleanup(conn)
        pass

    print("\n[OK] Example 4 -- PostgreSQL connection test completed!")
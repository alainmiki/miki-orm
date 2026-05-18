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
import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import models
from mikiorm.settings import settings, connection_manager
# from mikiorm.migrations.engine import MigrationEngine # No longer needed directly here
from mikiorm.backends.postgresql import PostgresAdapter


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def configure(backend="postgres"):
    # Ensure the migrations directory exists for makemigrations
    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mikiorm", "migrations")
    os.makedirs(migrations_dir, exist_ok=True)

    if backend == "postgres":
        mikiorm.configure(
            databases={
                "default": {
                    "ENGINE": "postgresql",
                    "NAME": "test",
                    "USER": "postgres",
                    "PASSWORD": "admin",
                    "HOST": "localhost", "PORT": 5432, "OPTIONS": {"sslmode": "prefer"},
                }
            },
            model_paths=[os.path.dirname(__file__)]
        )
    else:
        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": "postgres_demo.db",
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

def test_connection(backend):
    """Verify we can open and use a PostgreSQL connection."""
    print(f"\n--- Testing {backend} Connection ---")

    try:
        conn = connection_manager.get_connection("default")
        print("  [OK] Connected to database")

        conn.execute("SELECT 1 as result")
        row = conn.fetchone("SELECT 1 as result", ())
        assert row == (1,), "Expected (1,), got %s" % (row,)
        print("  [OK] Basic query executed successfully")

        if hasattr(conn, "release"):
            conn.close()
        return conn
    except Exception as e:
        print("  [FAIL] Connection failed: %s" % e)
        if backend == "postgres":
            print("\nHint: Make sure PostgreSQL is running on localhost:5432")
            print("   with database 'test', user 'postgres', password 'admin'")
        return None


def run_crud(backend):
    """Run a full round of CRUD operations."""
    print(f"\n--- Running CRUD Operations on {backend} ---")

    # Use MigrationEngine directly as per updated cli/init
    from mikiorm.migrations.engine import MigrationEngine
    MigrationEngine().makemigrations([Product, Review])
    MigrationEngine().migrate()
    print("  [OK] Tables created via migrate()")

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "postgres"], default="postgres")
    args = parser.parse_args()

    configure(args.backend)

    conn = test_connection(args.backend)
    if conn is None:
        print(f"\n[WARN] Could not connect to {args.backend}. Exiting.")
        sys.exit(1)

    try:
        run_crud(args.backend)
    finally:
        # cleanup(conn)
        pass

    print("\n[OK] Example 4 -- PostgreSQL connection test completed!")
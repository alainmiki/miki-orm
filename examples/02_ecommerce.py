#!/usr/bin/env python3
"""
Example 2: E-Commerce System
==============================
Demonstrates:
  - Multiple related models (User, Product, Order, OrderItem)
  - ForeignKey relationships with different on_delete strategies (CASCADE, SET_NULL)
  - Nullable ForeignKey (optional relationship)
  - DecimalField for monetary values
  - PositiveIntegerField for quantities
  - DateField with auto_now_add
  - Complex cross-model queries
  - select_related() and prefetch_related() hints
  - Custom table naming
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import models

DB_PATH = os.path.join(os.path.dirname(__file__), "ecommerce.db")


def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def configure():
    mikiorm.configure({
        "default": {
            "ENGINE": "sqlite",
            "NAME": DB_PATH,
        }
    })


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

class Customer(models.Model):
    """A customer who can place orders."""
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()
    phone = models.CharField(max_length=20, null=True)
    is_premium = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "customers"

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name}>"


class Address(models.Model):
    """Shipping / billing address linked to a customer (OneToOne)."""
    customer = models.OneToOneField(to="Customer", on_delete=models.CASCADE)
    street = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, null=True)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="US")

    class Meta:
        table_name = "addresses"


class Product(models.Model):
    """An item in the store catalog."""
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        table_name = "products"

    def __repr__(self):
        return f"<Product {self.name} (${self.price})>"


class Order(models.Model):
    """A customer order containing multiple items."""
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )

    customer = models.ForeignKey(to="Customer", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default="0.00")
    shipping_address = models.ForeignKey(
        to="Address", on_delete=models.SET_NULL, null=True
    )
    notes = models.TextField(null=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        table_name = "orders"


class OrderItem(models.Model):
    """Individual line item within an order."""
    order = models.ForeignKey(to="Order", on_delete=models.CASCADE)
    product = models.ForeignKey(to="Product", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        table_name = "order_items"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run():
    cleanup()
    configure()

    # ---- Create customers ----
    cust1 = Customer.objects.create(
        first_name="Emma", last_name="Watson", email="emma@example.com",
        phone="555-0101", is_premium=True,
    )
    cust2 = Customer.objects.create(
        first_name="Liam", last_name="Brown", email="liam@example.com",
        is_premium=False,
    )
    cust3 = Customer.objects.create(
        first_name="Olivia", last_name="Davis", email="olivia@example.com",
        is_premium=True,
    )
    print(f"Customers: {Customer.objects.count()}")

    # ---- Create addresses (OneToOne) ----
    addr1 = Address.objects.create(
        customer=cust1, street="123 Main St", city="Springfield",
        state="IL", zip_code="62701",
    )
    addr2 = Address.objects.create(
        customer=cust2, street="456 Oak Ave", city="Shelbyville",
        state="IL", zip_code="62565",
    )
    print(f"Addresses: {Address.objects.count()}")

    # ---- Create products ----
    products = [
        Product(name="Wireless Mouse", sku="WM-001", price="29.99", cost="12.50", stock_quantity=150),
        Product(name="Mechanical Keyboard", sku="MK-002", price="89.99", cost="40.00", stock_quantity=80),
        Product(name="USB-C Hub", sku="UCH-003", price="49.99", cost="18.00", stock_quantity=200),
        Product(name="27\" Monitor", sku="MON-004", price="349.99", cost="200.00", stock_quantity=30),
        Product(name="Webcam HD", sku="WC-005", price="59.99", cost="22.00", stock_quantity=100),
    ]
    Product.objects.bulk_create(products)
    print(f"Products: {Product.objects.count()}")

    # ---- Create orders with items ----
    order1 = Order.objects.create(
        customer=cust1, status="shipped", shipping_address=addr1,
        notes="Gift wrap please",
    )
    OrderItem.objects.create(order=order1, product=products[0], quantity=2, unit_price="29.99")
    OrderItem.objects.create(order=order1, product=products[1], quantity=1, unit_price="89.99")
    order1.total_amount = "149.97"
    order1.save()

    order2 = Order.objects.create(
        customer=cust2, status="processing", shipping_address=addr2,
    )
    OrderItem.objects.create(order=order2, product=products[2], quantity=3, unit_price="49.99")
    OrderItem.objects.create(order=order2, product=products[3], quantity=1, unit_price="349.99")
    order2.total_amount = "499.96"
    order2.save()

    order3 = Order.objects.create(
        customer=cust1, status="pending", shipping_address=addr1,
        notes="Rush delivery",
    )
    OrderItem.objects.create(order=order3, product=products[4], quantity=1, unit_price="59.99")
    order3.total_amount = "59.99"
    order3.save()

    print(f"Orders: {Order.objects.count()}")
    print(f"Order Items: {OrderItem.objects.count()}")

    # ---- Query: All orders for a specific customer ----
    emma_orders = Order.objects.filter(customer=cust1)
    print(f"\nEmma's orders: {len(emma_orders)}")
    for o in emma_orders:
        print(f"  Order {o.id}: status={o.status}, total=${o.total_amount}")

    # ---- Query: Orders with status filter + exclude ----
    active_orders = Order.objects.exclude(status="cancelled")
    print(f"\nActive (non-cancelled) orders: {active_orders.count()}")

    # ---- Query: Premium customers ----
    premium = Customer.objects.filter(is_premium=True)
    print(f"\nPremium customers: {[f'{c.first_name} {c.last_name}' for c in premium]}")

    # ---- Query: Pending orders ----
    pending = Order.objects.filter(status="pending")
    print(f"Pending orders: {pending.count()}")

    # ---- Query: Products in price range ----
    affordable = Product.objects.filter(price__lt="100")
    # Note: price__lt syntax requires QuerySet enhancements; using direct filter
    affordable = Product.objects.filter(price__lt=100)
    print(f"\nProducts under $100: {affordable.count()}")

    # ---- Query: Expensive products ----
    expensive = Product.objects.filter(price__gte=100).order_by("-price")
    print(f"Expensive products ($100+): {[p.name for p in expensive]}")

    # ---- Query: Products with stock below threshold ----
    low_stock = Product.objects.filter(stock_quantity__lt=50)
    print(f"\nLow stock products (< 50): {[f'{p.name}: {p.stock_quantity}' for p in low_stock]}")

    # ---- Query: Order items for a specific order ----
    items = OrderItem.objects.filter(order=order1)
    print(f"\nOrder #{order1.id} items:")
    for item in items:
        print(f"  {item.product.name} x{item.quantity} @ ${item.unit_price}")

    # ---- get_or_create: Customer lookup ----
    customer, was_new = Customer.objects.get_or_create(
        email="emma@example.com",
        defaults={"first_name": "Emma", "last_name": "Watson"},
    )
    print(f"\nget_or_create Emma: new={was_new}, id={customer.id}")

    # ---- update_or_create: Upsert order status ----
    order, was_new = Order.objects.update_or_create(
        customer=cust3,
        status="pending",
        defaults={"total_amount": "0.00", "notes": "New cart"},
    )
    print(f"update_or_create order: new={was_new}, id={order.id}")

    # ---- VALUES: Extract specific columns ----
    emails = Customer.objects.values("email", "first_name")
    print(f"\nCustomer emails: {emails}")

    # ---- VALUES_LIST: Get SKUs as tuples ----
    skus = Product.objects.values_list("sku", "name")
    print(f"Product SKUs: {skus}")

    # ---- ORDER BY: Newest orders first ----
    recent = Order.objects.all().order_by("-placed_at")
    print(f"\nMost recent order first: Order #{recent[0].id}")

    # ---- DELETE: Cancel a pending order ----
    cancel_count = Order.objects.filter(status="pending").delete()
    print(f"\nCancelled {cancel_count} pending order(s)")
    print(f"Remaining orders: {Order.objects.count()}")

    # ---- OneToOne: Access address from customer ----
    # (Manual FK resolution — the address's customer_id points back to cust1)
    all_addresses = Address.objects.all()
    for addr in all_addresses:
        print(f"  Address for customer_id={addr.customer}: {addr.city}")

    # ---- to_dict() ----
    print(f"\nOrder as dict: {order1.to_dict()}")
    print(f"\nProduct as dict: {products[0].to_dict()}")

    print("\n✅ Example 2 — E-Commerce system completed successfully!")


if __name__ == "__main__":
    run()
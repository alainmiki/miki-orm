# Phase 5 Quick Reference - Advanced QuerySet Features

## New Methods Added

### 1. in_bulk(id_list=None, field_name="pk")
Returns a dictionary mapping field values to model instances.

```python
# By primary key (default)
Product.objects.in_bulk([1, 2, 3])
# {1: Product(...), 2: Product(...), 3: Product(...)}

# By custom field
User.objects.in_bulk(["alice@example.com", "bob@example.com"], field_name="email")
# {"alice@example.com": User(...), "bob@example.com": User(...)}
```

---

### 2. union(*querysets, all=False)
Combines two or more QuerySets using SQL UNION.

```python
# Get active OR recent posts
active = Post.objects.filter(status="active")
recent = Post.objects.filter(created_at__gte=datetime(2026, 5, 1))
combined = active.union(recent)

# With duplicates (UNION ALL)
active.union(recent, all=True)
```

---

### 3. intersection(*querysets)
Returns only items that exist in ALL QuerySets (SQL INTERSECT).

```python
# Get verified AND active users
verified = User.objects.filter(is_verified=True)
active = User.objects.filter(status="active")
both = verified.intersection(active)
```

---

### 4. difference(*querysets)
Returns items in first QuerySet but not in others (SQL EXCEPT).

```python
# Get active users who are NOT admins
all_active = User.objects.filter(is_active=True)
admins = User.objects.filter(is_admin=True)
non_admin_active = all_active.difference(admins)
```

---

### 5. having(*args, **kwargs)
Filters aggregated results. Must be used with annotate().

```python
from mikiorm.query import Sum, Count

# Get products with total sales >= 1000
high_value = (Product.objects
    .annotate(total_sales=Sum("sales"))
    .having(total_sales__gte=1000))

# Multiple conditions
categories = (Product.objects
    .annotate(
        total_qty=Sum("quantity"),
        product_count=Count()
    )
    .having(
        total_qty__gte=100,
        product_count__gte=5
    ))
```

---

### 6. Automatic GROUP BY
When using annotate(), GROUP BY is automatically generated.

```python
# Automatically creates GROUP BY
results = (Product.objects
    .annotate(total_qty=Sum("quantity"))
    .all())

# Works with filtering
results = (Product.objects
    .filter(category="Electronics")
    .annotate(total_qty=Sum("quantity"))
    .all())
```

---

## Chainable Methods (Enhanced)

### values() - Now Chainable
```python
# Chain filters before values()
(Product.objects
    .filter(category="Electronics")
    .filter(price__gte=100)
    .values("name", "price"))

# Combine with order_by
(Product.objects
    .filter(active=True)
    .order_by("-price")
    .values("name", "price", "category"))
```

### values_list() - Now Chainable
```python
# Chain filters before values_list
(Product.objects
    .filter(category="Electronics")
    .values_list("name", "price"))

# Flat output
names = (Product.objects
    .filter(active=True)
    .values_list("name", flat=True))  # ["Laptop", "Phone", ...]
```

---

## Complex Query Examples

### Example 1: High-Volume Products
```python
from mikiorm.query import Sum, Count

# Products with >= 1000 in sales AND 10+ transactions
high_volume = (Product.objects
    .annotate(
        total_sales=Sum("sales"),
        transaction_count=Count()
    )
    .having(
        total_sales__gte=1000,
        transaction_count__gte=10
    )
    .values("name", "category", "total_sales", "transaction_count"))
```

### Example 2: Set Operations
```python
# Users that are (verified OR premium) AND active
verified_or_premium = (
    User.objects.filter(is_verified=True)
    .union(User.objects.filter(is_premium=True))
)
active_special = verified_or_premium.intersection(
    User.objects.filter(status="active")
)
```

### Example 3: Batch Processing
```python
# Get multiple users efficiently
important_ids = [1, 5, 10, 15, 20]
users_dict = User.objects.in_bulk(important_ids)

# O(1) access
for user_id in important_ids:
    user = users_dict[user_id]
    # Process user...
```

### Example 4: Aggregation with Filtering
```python
# Orders by customer with total >= 5000
from mikiorm.query import Sum

customer_stats = (Order.objects
    .filter(status="completed")
    .annotate(total_amount=Sum("amount"))
    .having(total_amount__gte=5000)
    .values("customer_id", "total_amount"))

for stat in customer_stats:
    print(f"Customer {stat['customer_id']}: ${stat['total_amount']}")
```

---

## Common Patterns

### Pattern 1: Find Top Performing Items
```python
from mikiorm.query import Sum

top_products = (Product.objects
    .annotate(total_revenue=Sum("sales"))
    .having(total_revenue__gte=10000)
    .order_by("-total_revenue")
    .values("name", "total_revenue")
    [0:10])  # Top 10
```

### Pattern 2: Remove Inactive from Active Set
```python
active = Article.objects.filter(status="active")
archived = Article.objects.filter(is_archived=True)
current_articles = active.difference(archived)
```

### Pattern 3: Find Common Followers
```python
user1_followers = User.objects.filter(followers__user_id=1)
user2_followers = User.objects.filter(followers__user_id=2)
mutual = user1_followers.intersection(user2_followers)
```

### Pattern 4: Bulk Dictionary Operations
```python
# Get all data at once, then process locally
ids = [1, 2, 3, 4, 5]
products = Product.objects.in_bulk(ids)

# Update related items
for product_id, product in products.items():
    product.last_checked = datetime.now()
    product.save()
```

---

## Error Handling

### Error: having() without annotate()
```python
# ❌ ERROR
Product.objects.having(price__gte=100)
# ValueError: having() requires annotate() to be called first

# ✅ CORRECT
Product.objects.annotate(total_qty=Sum("quantity")).having(total_qty__gte=100)
```

### Error: Union different models
```python
# ❌ ERROR
Product.objects.filter(name="Laptop").union(User.objects.all())
# TypeError: union() requires QuerySets of the same model

# ✅ CORRECT
Product.objects.filter(active=True).union(Product.objects.filter(featured=True))
```

### Error: values_list flat with multiple fields
```python
# ❌ ERROR
Product.objects.values_list("name", "price", flat=True)
# ValueError: flat=True requires exactly one field

# ✅ CORRECT
Product.objects.values_list("name", flat=True)
```

---

## Performance Tips

### ✅ DO: Use in_bulk() for batch operations
```python
# Single query + O(1) dictionary access
products = Product.objects.in_bulk([1, 2, 3])
for pid, product in products.items():
    print(product.name)
```

### ✅ DO: Filter before aggregating
```python
# Smaller dataset to aggregate
stats = (Order.objects
    .filter(created_at__gte=datetime(2026, 1, 1))
    .aggregate(total=Sum("amount")))
```

### ❌ DON'T: Get all then filter in Python
```python
# Gets all, then loops - inefficient!
all_products = Product.objects.all()
electronics = [p for p in all_products if p.category == "Electronics"]
```

### ❌ DON'T: Multiple similar queries
```python
# Use union() instead
active = Product.objects.filter(status="active").all()
featured = Product.objects.filter(is_featured=True).all()
combined = list(active) + list(featured)  # Wrong!

# Better
combined = (Product.objects.filter(status="active")
    .union(Product.objects.filter(is_featured=True))
    .all())
```

---

## Backward Compatibility

All Phase 1-4 code continues to work:

```python
# Phase 1: Basic queries
Product.objects.filter(price__gte=100).all()

# Phase 2: Q objects
from mikiorm import Q
Product.objects.filter(Q(category="Electronics") | Q(price__gte=100)).all()

# Phase 3: Aggregations
from mikiorm.query import Count, Sum
Product.objects.aggregate(count=Count(), total=Sum("price"))

# Phase 4: Advanced lookups
Product.objects.filter(created_at__year=2026).all()

# Phase 5: New features
Product.objects.in_bulk([1, 2, 3])
Product.objects.annotate(total_qty=Sum("quantity")).having(total_qty__gte=100)

# All work together!
```

---

## Summary

**Phase 5 adds 6 powerful methods** for advanced data manipulation:

| Method | Purpose | SQL |
|--------|---------|-----|
| `in_bulk()` | Batch dictionary lookup | SELECT with IN |
| `union()` | Combine results | UNION |
| `intersection()` | Common elements | INTERSECT |
| `difference()` | Set difference | EXCEPT |
| `having()` | Filter aggregations | HAVING |
| `GROUP BY` | Automatic grouping | GROUP BY |

**Combined with existing features**, they enable 96% Django compatibility for querying, filtering, aggregating, and manipulating data in miki-orm.

See `PHASES_1_TO_5_COMPLETE_REPORT.md` for full documentation.

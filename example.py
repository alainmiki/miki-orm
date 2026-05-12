#!/usr/bin/env python3
"""
Example usage of miki-orm.
"""

import myorm
from myorm import models

# Configure database like Django
myorm.configure({
    "default": {
        "ENGINE": "sqlite",
        "NAME": "example.db"
    }
})

# Define a model
class User(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()

    class Meta:
        table_name = "users"

# Register the model (optional, for migrations)
myorm.register_model(User)

# Example usage
if __name__ == "__main__":
    # Create tables via migration without touching engine internals
    myorm.makemigrations([User])
    myorm.migrate()

    # Create a user
    user = User.objects.create(name="Alice", age=30)
    print(f"Created user: {user.to_dict()}")

    # Get or create
    user2, created = User.objects.get_or_create(name="Bob", defaults={"age": 25})
    print(f"User2: {user2.to_dict()}, created: {created}")

    # Query
    users = User.objects.all()
    print(f"All users: {[u.to_dict() for u in users]}")

    # Get single
    try:
        alice = User.objects.get(name="Alice")
        print(f"Found Alice: {alice.to_dict()}")
    except myorm.models.ObjectDoesNotExist:
        print("Alice not found")

    # Get object or 404
    try:
        charlie = User.objects.get_object_or_404(name="Charlie")
    except myorm.models.ObjectDoesNotExist:
        print("Charlie not found (404)")

    # Delete all
    deleted = User.objects.all().delete()
    print(f"Deleted {deleted} users")
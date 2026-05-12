#!/usr/bin/env python3
"""Debug: test table creation with SQLite."""
import os
import sys

# Set working directory to the repo root
os.chdir(r"F:\workstation\python\miki-orm")
sys.path.insert(0, r"F:\workstation\python\miki-orm")

from myorm import models, configure

db_path = r"F:\workstation\python\miki-orm\test_debug.db"

configure({
    "default": {"ENGINE": "sqlite", "NAME": db_path}
})

class IntModel(models.Model):
    name = models.CharField(max_length=50)
    age = models.IntegerField()
    class Meta:
        table_name = "int_test"

try:
    obj = IntModel(name="Test", age=30)
    obj.save()
    print("Saved:", obj.to_dict())

    fetched = IntModel.objects.get(id=obj.id)
    print("Fetched:", fetched.to_dict())
except Exception:
    import traceback
    traceback.print_exc()
finally:
    if os.path.exists(db_path):
        os.remove(db_path)
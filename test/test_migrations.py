"""Tests for migrations."""

import pytest
from mikiorm.migrations.engine import MigrationEngine
from mikiorm.models.base import Model
from mikiorm.models.fields import IntegerField, CharField
import mikiorm


@mikiorm.register("test")
class TestModel(Model):
    id = IntegerField(primary_key=True, auto_increment=True)
    name = CharField(max_length=100)

    class Meta:
        table_name = "test_model"


def test_makemigrations():
    mikiorm.configure({"default": {"ENGINE": "sqlite", "NAME": ":memory:"}})
    engine = MigrationEngine()
    migrations = engine.makemigrations()
    assert len(migrations) > 0
    assert migrations[0].operation_type == "create_table"

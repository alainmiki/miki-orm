"""Tests for migrations."""

import pytest
from myorm.migrations.engine import MigrationEngine
from myorm.models.base import Model
from myorm.models.fields import IntegerField, CharField
import myorm


class TestModel(Model):
    id = IntegerField(primary_key=True, auto_increment=True)
    name = CharField(max_length=100)

    class Meta:
        table_name = "test_model"


def test_makemigrations():
    myorm.configure({
        "default": {
            "ENGINE": "sqlite",
            "NAME": ":memory:"
        }
    })
    engine = MigrationEngine()
    migrations = engine.makemigrations([TestModel])
    assert len(migrations) > 0
    assert migrations[0].operation_type == "create_table"
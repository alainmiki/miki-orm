# Auto-generated migration
# Generated: 2026-05-12T05:24:52.055774

from myorm.migrations import operations
from myorm.models.fields import CharField
from myorm.models.fields import IntegerField


def apply_migration(apps, schema_editor):
    operations.CreateTable(
        name="test_model",
        columns=[
            (IntegerField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
            (CharField(type='VARCHAR(100)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
        ],
    )


def rollback_migration(apps, schema_editor):
    operations.CreateTable(
        name="test_model",
        columns=[
            (IntegerField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
            (CharField(type='VARCHAR(100)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
        ],
        reverse_op=operations.DeleteTable('test_model'),
    )


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
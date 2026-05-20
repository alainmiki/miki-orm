# Auto-generated migration
# Generated: 2026-05-20T14:53:31.344806

from mikiorm.migrations import operations
from mikiorm.models.fields import AutoField
from mikiorm.models.fields import CharField
from mikiorm.models.fields import IntegerField


def apply_migration(apps, schema_editor):
    schema_editor.execute_operation(operations.CreateTable(
        name="test_model",
        columns=[
            (IntegerField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
        ],
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="migration_test_model",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )
    )


def rollback_migration(apps, schema_editor):
    schema_editor.execute_operation(operations.CreateTable(
        name="migration_test_model",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('migration_test_model'),
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="test_model",
        columns=[
            (IntegerField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
        ],
        reverse_op=operations.DeleteTable('test_model'),
    )
    )


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
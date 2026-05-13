# Auto-generated migration
# Generated: 2026-05-13T10:22:23.416765

from myorm.migrations import operations


def apply_migration(apps, schema_editor):
    from myorm.models.fields import AutoField
    operations.AlterField(model_name='users', field=AutoField(field_name='id', name='id', unique=True))


def rollback_migration(apps, schema_editor):
    from myorm.models.fields import AutoField
    # AlterField reverse not yet fully reversible


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
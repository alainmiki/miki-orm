# Auto-generated migration
# Generated: 2026-05-13T10:50:40.868972

from myorm.migrations import operations


def apply_migration(apps, schema_editor):
    from myorm.models.fields import AutoField
    operations.AlterField(model_name='users', field=AutoField(field_name='id', field=AutoField(name='id', null=False, blank=False, default=None, primary_key=True, unique=True, auto_increment=False, unique_for_date=None, unique_for_month=None, unique_for_year=None, choices=None, db_column=None, db_comment=None, db_default=None, db_index=False, db_tablespace=None, editable=True, error_messages=None, help_text='', verbose_name=None, validators=[], serialize=True), name='id', unique=True))


def rollback_migration(apps, schema_editor):
    from myorm.models.fields import AutoField
    # AlterField reverse not yet fully reversible


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
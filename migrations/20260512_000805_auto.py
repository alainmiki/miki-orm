# Auto-generated migration
# Generated: 2026-05-12T00:08:05.166349

from myorm.migrations import operations
from myorm.models.fields import AutoField
from myorm.models.fields import CharField
from myorm.models.fields import IntegerField


def apply_migration(apps, schema_editor):
    operations.CreateTable(
        name="users",
        columns=[
            (CharField(max_length=100), 'name'),
            (IntegerField(), 'age'),
            (AutoField(primary_key=True, unique=True), 'id'),
        ],
    )



class Migration:
    dependencies = []

    operations = [apply_migration]
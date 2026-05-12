# Auto-generated migration
# Generated: 2026-05-11T22:59:19.062490

from myorm.migrations import operations
from myorm.models.fields import AutoField
from myorm.models.fields import BooleanField
from myorm.models.fields import CharField
from myorm.models.fields import DateTimeField
from myorm.models.fields import DecimalField
from myorm.models.relationships import ForeignKey
from myorm.models.fields import IntegerField
from myorm.models.fields import TextField


def apply_migration(apps, schema_editor):
    operations.CreateTable(
        name="products",
        columns=[
            (CharField(max_length=200), 'name'),
            (TextField(null=True), 'description'),
            (DecimalField(max_digits=10, decimal_places=2), 'price'),
            (IntegerField(default=0), 'quantity'),
            (BooleanField(default=True), 'is_available'),
            (DateTimeField(blank=True, auto_now_add=True), 'created_at'),
            (DateTimeField(blank=True, auto_now=True), 'updated_at'),
            (AutoField(primary_key=True, unique=True), 'id'),
        ],
    )

    operations.CreateTable(
        name="reviews",
        columns=[
            (ForeignKey(), 'product'),
            (CharField(max_length=100), 'author_name'),
            (IntegerField(), 'rating'),
            (TextField(null=True), 'comment'),
            (AutoField(primary_key=True, unique=True), 'id'),
        ],
    )



class Migration:
    dependencies = []

    operations = [apply_migration]
# Auto-generated migration
# Generated: 2026-05-13T10:07:09.953600

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
            (CharField(type='VARCHAR(200)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (TextField(type='TEXT', null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'description'),
            (DecimalField(type='DECIMAL(10, 2)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'price'),
            (IntegerField(type='INTEGER', null=False, default=0, primary_key=False, unique=False, auto_increment=False), 'quantity'),
            (BooleanField(type='BOOLEAN', null=False, default=True, primary_key=False, unique=False, auto_increment=False), 'is_available'),
            (DateTimeField(type='DATETIME', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (DateTimeField(type='DATETIME', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'updated_at'),
            (AutoField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )
    operations.CreateTable(
        name="reviews",
        columns=[
            (ForeignKey(type='INTEGER', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'product'),
            (CharField(type='VARCHAR(100)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'author_name'),
            (IntegerField(type='INTEGER', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'rating'),
            (TextField(type='TEXT', null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'comment'),
            (AutoField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )


def rollback_migration(apps, schema_editor):
    operations.CreateTable(
        name="reviews",
        columns=[
            (ForeignKey(type='INTEGER', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'product'),
            (CharField(type='VARCHAR(100)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'author_name'),
            (IntegerField(type='INTEGER', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'rating'),
            (TextField(type='TEXT', null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'comment'),
            (AutoField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('reviews'),
    )
    operations.CreateTable(
        name="products",
        columns=[
            (CharField(type='VARCHAR(200)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (TextField(type='TEXT', null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'description'),
            (DecimalField(type='DECIMAL(10, 2)', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'price'),
            (IntegerField(type='INTEGER', null=False, default=0, primary_key=False, unique=False, auto_increment=False), 'quantity'),
            (BooleanField(type='BOOLEAN', null=False, default=True, primary_key=False, unique=False, auto_increment=False), 'is_available'),
            (DateTimeField(type='DATETIME', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (DateTimeField(type='DATETIME', null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'updated_at'),
            (AutoField(type='INTEGER', null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('products'),
    )


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
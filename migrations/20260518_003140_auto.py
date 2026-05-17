# Auto-generated migration
# Generated: 2026-05-18T00:31:40.284344

from mikiorm.migrations import operations
from mikiorm.models.fields import AutoField
from mikiorm.models.fields import BooleanField
from mikiorm.models.fields import CharField
from mikiorm.models.fields import DateTimeField
from mikiorm.models.fields import EmailField
from mikiorm.models.relationships import ForeignKey
from mikiorm.models.fields import IntegerField
from mikiorm.models.fields import JSONField
from mikiorm.models.fields import SlugField
from mikiorm.models.fields import TextField


def apply_migration(apps, schema_editor):
    schema_editor.execute_operation(operations.CreateTable(
        name="authors",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (EmailField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'email'),
            (TextField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'bio'),
            (BooleanField(null=False, default=True, primary_key=False, unique=False, auto_increment=False), 'is_active'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="categories",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (SlugField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'slug'),
            (TextField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'description'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="posts",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'title'),
            (SlugField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'slug'),
            (TextField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'body'),
            (ForeignKey(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'author'),
            (ForeignKey(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'category'),
            (BooleanField(null=False, default=False, primary_key=False, unique=False, auto_increment=False), 'is_published'),
            (JSONField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'tags'),
            (JSONField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'metadata'),
            (DateTimeField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'published_at'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'updated_at'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
    )
    )


def rollback_migration(apps, schema_editor):
    schema_editor.execute_operation(operations.CreateTable(
        name="posts",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'title'),
            (SlugField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'slug'),
            (TextField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'body'),
            (ForeignKey(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'author'),
            (ForeignKey(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'category'),
            (BooleanField(null=False, default=False, primary_key=False, unique=False, auto_increment=False), 'is_published'),
            (JSONField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'tags'),
            (JSONField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'metadata'),
            (DateTimeField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'published_at'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'updated_at'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('posts'),
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="categories",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (SlugField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'slug'),
            (TextField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'description'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('categories'),
    )
    )
    schema_editor.execute_operation(operations.CreateTable(
        name="authors",
        columns=[
            (CharField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'name'),
            (EmailField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'email'),
            (TextField(null=True, default=None, primary_key=False, unique=False, auto_increment=False), 'bio'),
            (BooleanField(null=False, default=True, primary_key=False, unique=False, auto_increment=False), 'is_active'),
            (DateTimeField(null=False, default=None, primary_key=False, unique=False, auto_increment=False), 'created_at'),
            (IntegerField(null=False, default=1, primary_key=False, unique=False, auto_increment=False), 'version'),
            (AutoField(null=False, default=None, primary_key=True, unique=True, auto_increment=True), 'id'),
        ],
        reverse_op=operations.DeleteTable('authors'),
    )
    )


class Migration:
    dependencies = []

    operations = [apply_migration]
    rollback_operations = [rollback_migration]
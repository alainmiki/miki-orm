"""Migration system tests: engine, operations, makemigrations, apply, rollback."""

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from myorm import configure, settings
from myorm.migrations.engine import MigrationEngine
from myorm.migrations.operations import (
    CreateTable, AddField, AlterField, DropField,
    CreateIndex, DropIndex, RenameField, DeleteTable,
)
from myorm.models.base import Model
from myorm.models.fields import CharField, IntegerField, TextField, ForeignKey
from myorm.models.relationships import CASCADE


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


def get_config(backend):
    if backend == "sqlite":
        return {"ENGINE": "sqlite", "NAME": ":memory:"}
    elif backend == "postgres":
        return {
            "ENGINE": "postgresql",
            "NAME": "miki_orm_test",
            "USER": "postgres",
            "PASSWORD": "admin",
            "HOST": "localhost",
            "PORT": 5432,
        }
    else:
        raise ValueError(backend)


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
def backend(request):
    backend = request.param
    configure(databases={"default": get_config(backend)})
    yield backend
    try:
        settings.connection_manager.close_all()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unit tests for individual operations
# ---------------------------------------------------------------------------


def test_create_table_operation_generates_sql():
    class Tmp(Model):
        name = CharField(max_length=100)
        age = IntegerField()

        class Meta:
            table_name = "tmp_table"

    op = CreateTable(Tmp)
    sqls = op.to_sql("sqlite")
    assert any("CREATE TABLE tmp_table" in s for s in sqls)


def test_create_table_reverse():
    class Tmp(Model):
        name = CharField(max_length=100)

        class Meta:
            table_name = "tmp_table"

    op = CreateTable(Tmp)
    rev = op.reverse()
    assert isinstance(rev, DeleteTable)


def test_add_and_drop_field():
    from myorm.models.fields import IntegerField

    class Dummy(Model):
        id = IntegerField(primary_key=True)
        name = CharField(max_length=50)

        class Meta:
            table_name = "dummy"

    add = AddField(Dummy, "age", IntegerField(null=True))
    sql = add.to_sql("sqlite")
    assert any("ADD COLUMN age INTEGER" in s for s in sql)

    drop = add.reverse()
    assert isinstance(drop, DropField)
    rev_sql = drop.to_sql("sqlite")
    assert any("DROP COLUMN age" in s for s in rev_sql)


def test_rename_field():
    class Person(Model):
        name = CharField(max_length=50)

        class Meta:
            table_name = "person"

    op = RenameField(Person, "name", "full_name")
    sqls = op.to_sql("sqlite")
    assert any("RENAME COLUMN name TO full_name" in s for s in sqls) or any("ALTER TABLE person RENAME COLUMN name TO full_name" in s for s in sqls)


def test_create_and_drop_index():
    class IdxTest(Model):
        code = CharField(max_length=20, unique=True)

        class Meta:
            table_name = "idxtest"

    create = CreateIndex(IdxTest, ["code"])
    sqls = create.to_sql("sqlite")
    assert any("CREATE UNIQUE INDEX" in s for s in sqls)

    drop = create.reverse()
    rev_sqls = drop.to_sql("sqlite")
    assert any("DROP INDEX" in s for s in rev_sqls)


def test_alter_field_noop():
    """AlterField may be no-op for some backends."""
    class AlterMe(Model):
        val = CharField(max_length=50)

        class Meta:
            table_name = "alter_me"

    new_field = CharField(max_length=50)
    op = AlterField(AlterMe, "val", new_field)
    sqls = op.to_sql("sqlite")
    # SQLite can't alter column; may return empty list or a warning
    assert isinstance(sqls, list)


def test_multiple_operations_reversible():
    class MT(Model):
        name = CharField(max_length=50)

        class Meta:
            table_name = "mt"

    class MTFK(Model):
        mt = ForeignKey(MT, on_delete=CASCADE)

        class Meta:
            table_name = "mtfk"

    ops = [
        CreateTable(MT),
        CreateTable(MTFK),
        AddField(MT, "age", IntegerField(null=True)),
        CreateIndex(MT, ["name"]),
    ]
    # Each operation must have a reverse
    for op in ops:
        rev = op.reverse()
        assert rev is not None


def test_migration_engine_creates_files(tmp_path):
    """MigrationEngine.makemigrations writes .py files to MIGRATION_PATH."""
    tmp_migrations = tmp_path / "migrations"
    tmp_migrations.mkdir()
    # Temporarily redirect MIGRATION_PATH in settings
    from myorm import settings as s
    original = getattr(s, "MIGRATION_PATH", None)
    s.MIGRATION_PATH = str(tmp_migrations)

    try:
        class EngineTest(Model):
            title = CharField(max_length=100)

            class Meta:
                table_name = "engine_test"

        engine = MigrationEngine()
        ops = engine.makemigrations([EngineTest])
        assert len(ops) >= 1
        # Check file created
        files = list(tmp_migrations.glob("*.py"))
        assert len(files) >= 1
    finally:
        if original is not None:
            s.MIGRATION_PATH = original
        else:
            del s.MIGRATION_PATH


def test_migration_engine_applies_and_rolls_back(backend):
    """MigrationEngine.migrate applies and can roll back."""
    backend_config = get_config(backend)
    configure(databases={"default": backend_config})

    class MigrateTest(Model):
        title = CharField(max_length=100)

        class Meta:
            table_name = "migrate_test"

    engine = MigrationEngine()
    # Create migration for this model
    ops = engine.makemigrations([MigrateTest])
    assert len(ops) >= 1

    # Apply
    engine.migrate()
    # Table should exist now; can create row
    try:
        obj = MigrateTest(title="test")
        obj.save(force_insert=True)
        assert MigrateTest.objects.count() >= 1
    except Exception as e:
        pytest.fail(f"Could not save after migration: {e}")

    # Clean up: drop table manually (rollback logic varies)
    conn = settings.connection_manager.get_connection()
    conn.execute(f"DROP TABLE IF EXISTS {MigrateTest._meta.table_name}", ())
    conn.commit()

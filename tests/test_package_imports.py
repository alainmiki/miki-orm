"""Basic package import smoke tests."""

from myorm import Model, MigrationEngine
from myorm.connections import SQLiteAdapter, PostgresAdapter, MySQLAdapter
from myorm.managers import Manager


def test_package_imports() -> None:
    assert Model is not None
    assert MigrationEngine is not None
    assert SQLiteAdapter is not None
    assert PostgresAdapter is not None
    assert MySQLAdapter is not None
    assert Manager is not None

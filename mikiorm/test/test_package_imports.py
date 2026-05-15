"""Basic package import smoke tests."""

from mikiorm import Model, MigrationEngine
from mikiorm.connections import SQLiteAdapter, PostgresAdapter, MySQLAdapter
from mikiorm.managers.base import Manager

from mikiorm import Model as MikiModel, MigrationEngine as MikiMigrationEngine
from mikiorm.connections import SQLiteAdapter as MikiSQLiteAdapter, PostgresAdapter as MikiPostgresAdapter, MySQLAdapter as MikiMySQLAdapter
from mikiorm.managers.base import Manager as MikiBaseManager


def test_package_imports() -> None:
    assert Model is not None
    assert MigrationEngine is not None
    assert SQLiteAdapter is not None
    assert PostgresAdapter is not None
    assert MySQLAdapter is not None
    assert Manager is not None


def test_mikiorm_package_imports() -> None:
    assert MikiModel is not None
    assert MikiMigrationEngine is not None
    assert MikiSQLiteAdapter is not None
    assert MikiPostgresAdapter is not None
    assert MikiMySQLAdapter is not None
    assert MikiBaseManager is not None

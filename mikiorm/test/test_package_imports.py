"""Basic package import smoke tests."""

from mikiorm import Model
from mikiorm.backends import SQLite, Postgres, MySQL
from mikiorm.managers import Manager

from mikiorm import Model as MikiModel
from mikiorm.backends import (
    SQLite as MikiSQLite,
    Postgres as MikiPostgres,
    MySQL as MikiMySQL,
)
from mikiorm.managers import Manager as MikiBaseManager

def test_package_imports() -> None:
    assert Model is not None
    assert SQLite is not None
    assert Postgres is not None
    assert MySQL is not None
    assert Manager is not None


def test_mikiorm_package_imports() -> None:
    assert MikiModel is not None
    assert MikiSQLite is not None
    assert MikiPostgres is not None
    assert MikiMySQL is not None
    assert MikiBaseManager is not None

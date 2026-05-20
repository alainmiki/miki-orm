"""Database connection tests for SQLite, PostgreSQL, and MySQL adapters."""

from __future__ import annotations

import pytest
import sqlite3

from mikiorm.backends.sqlite.adapter import Adapter as SQLiteAdapter
from mikiorm.backends.sqlite.base import SQLiteConnection
from mikiorm.backends.base import BaseAdapter, BaseConnection, PooledConnection, SyncConnectionPool


class TestSQLiteAdapter:
    def test_adapter_is_base_adapter(self):
        adapter = SQLiteAdapter()
        assert isinstance(adapter, BaseAdapter)

    def test_connect_in_memory(self):
        adapter = SQLiteAdapter()
        conn = adapter.connect({"NAME": ":memory:"})
        assert isinstance(conn, SQLiteConnection)
        assert isinstance(conn, BaseConnection)

    def test_execute_and_fetchall(self):
        adapter = SQLiteAdapter()
        conn = adapter.connect({"NAME": ":memory:"})
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES (?)", ("Alice",))
        conn.execute("INSERT INTO test (name) VALUES (?)", ("Bob",))
        results = conn.fetchall("SELECT * FROM test ORDER BY id", ())
        assert results == [(1, "Alice"), (2, "Bob")]

    def test_fetchone(self):
        adapter = SQLiteAdapter()
        conn = adapter.connect({"NAME": ":memory:"})
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES (?)", ("Alice",))
        row = conn.fetchone("SELECT name FROM test WHERE id = 1", ())
        assert row == ("Alice",)

    def test_commit_and_rollback(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        adapter = SQLiteAdapter()
        conn = adapter.connect({"NAME": db_path})
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES (?)", ("Alice",))
        conn.commit()
        assert conn.fetchall("SELECT * FROM test", ()) == [(1, "Alice")]
        conn.execute("INSERT INTO test (name) VALUES (?)", ("Bob",))
        conn.rollback()
        # After rollback, Bob should not be there
        assert conn.fetchall("SELECT * FROM test", ()) == [(1, "Alice")]

    def test_create_pool_returns_connection(self):
        adapter = SQLiteAdapter()
        pool = adapter.create_pool({"NAME": ":memory:"})
        assert hasattr(pool, "acquire")
        conn = pool.acquire()
        assert isinstance(conn, PooledConnection)
        conn.close()


class TestPostgresAdapter:
    def test_module_imports(self):
        """psycopg2-based adapter should be importable."""
        from mikiorm.backends.postgresql.base import PostgresAdapter, PostgresConnection
        adapter = PostgresAdapter()
        assert isinstance(adapter, BaseAdapter)

    def test_configured_database_properties(self):
        """Postgres config should correctly parse host, port, user, password, dbname."""
        import mikiorm
        mikiorm.configure({
            "default": {
                "ENGINE": "postgresql",
                "NAME": "test",
                "USER": "postgres",
                "PASSWORD": "admin",
                "HOST": "localhost",
                "PORT": 5432,
            }
        })
        from mikiorm.settings import settings
        db_config = settings.get_database("default")
        assert db_config.name == "test"
        assert db_config.user == "postgres"
        assert db_config.password == "admin"
        assert db_config.host == "localhost"
        assert db_config.port == 5432
        assert db_config.engine == "postgresql"

    @pytest.mark.skip(reason="Requires a running PostgreSQL server")
    def test_connect_to_postgres(self):
        """Integration test: connect to a real PostgreSQL database."""
        import mikiorm
        from mikiorm.settings import connection_manager

        mikiorm.configure({
            "default": {
                "ENGINE": "postgresql",
                "NAME": "test",
                "USER": "postgres",
                "PASSWORD": "admin",
                "HOST": "localhost",
                "PORT": 5432,
            }
        })
        conn = connection_manager.get_connection("default")
        assert conn is not None
        conn.execute("SELECT 1 as val")
        row = conn.fetchone("SELECT 1 as val")
        assert row == (1,)


class TestMySQLAdapter:
    def test_module_imports(self):
        """pymysql-based adapter should be importable."""
        from mikiorm.backends.mysql.base import MySQLAdapter
        adapter = MySQLAdapter()
        assert isinstance(adapter, BaseAdapter)


class TestConnectionManager:
    def test_get_connection_manager(self):
        from mikiorm.settings import connection_manager
        # Initially empty
        assert len(connection_manager._pools) == 0

    def test_get_connection_uses_pool(self):
        import mikiorm
        from mikiorm.settings import connection_manager, settings

        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:",
                "POOL": {"min_size": 1, "max_size": 2, "timeout": 5},
            }
        })
        conn = connection_manager.get_connection("default")
        assert hasattr(conn, "execute")
        assert hasattr(conn, "close")
        conn.close()
        assert "default" in connection_manager._pools
        connection_manager.close_all()

    def test_validate_connection(self):
        import mikiorm
        from mikiorm.settings import connection_manager

        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:",
                "POOL": {"min_size": 1, "max_size": 1, "timeout": 5},
            }
        })
        assert connection_manager.validate_connection("default") is True
        connection_manager.close_all()

    def test_pool_context_manager_returns_connection(self):
        from mikiorm.backends.sqlite.adapter import Adapter as SQLiteAdapter

        adapter = SQLiteAdapter()
        pool = adapter.create_pool({"NAME": ":memory:"}, {"min_size": 1, "max_size": 1, "timeout": 5})
        with pool.acquire() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)", ())
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Alice",))
            row = conn.fetchone("SELECT name FROM test WHERE id = 1", ())
            assert row == ("Alice",)
        assert pool._idle.qsize() == 1
        pool.close()


class TestConfigure:
    def test_configure_exposed(self):
        import mikiorm
        assert hasattr(mikiorm, "configure")
        assert callable(mikiorm.configure)

    def test_configure_databases(self):
        import mikiorm
        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:"
            }
        })
        from mikiorm.settings import settings
        assert "default" in settings.databases


class TestMigrationWithSQLite:
    """Test full migration flow with SQLite in-memory database."""

    def test_makemigrations_creates_file(self, tmp_path):
        import mikiorm
        from mikiorm import models
        from mikiorm.migrations.engine import MigrationEngine

        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:"
            }
        })

        class TestModel(models.Model):
            id = models.IntegerField(primary_key=True, auto_increment=True)
            name = models.CharField(max_length=100)

            class Meta:
                table_name = "test_model"

        engine = MigrationEngine(migrations_path=str(tmp_path))
        ops = engine.makemigrations([TestModel])
        assert len(ops) > 0
        assert ops[0].operation_type == "create_table"

    def test_configure_and_use_connection(self):
        import mikiorm
        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:"
            }
        })
        from mikiorm.settings import connection_manager
        conn = connection_manager.get_connection("default")
        assert conn is not None

    def test_makemigrations_and_migrate_direct(self, tmp_path):
        import mikiorm
        from mikiorm import models
        from mikiorm.migrations.engine import MigrationEngine
        from mikiorm.models.fields import CharField, IntegerField
        from mikiorm.migrations.operations import AddField, AlterField, RemoveField
        from mikiorm.settings import connection_manager

        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:",
                "POOL": {"min_size": 1, "max_size": 1, "timeout": 5},
            }
        })

        class MigrationTestModel(models.Model):
            name = CharField(max_length=20)

            class Meta:
                table_name = "migration_test_model"

        engine = MigrationEngine(migrations_path=str(tmp_path))
        ops = engine.makemigrations([MigrationTestModel])
        assert ops
        assert ops[0].operation_type == "create_table"

        # Get the migration file that was just created
        history_map = engine._build_migration_map()
        assert history_map
        migration_name, migration_filepath = next(iter(history_map.items()))

        conn = connection_manager.get_connection("default")
        engine.migrate_direct(str(migration_filepath), connection=conn)
        conn.close()

        conn = connection_manager.get_connection("default")
        # Test add/alter/drop operations on a new field
        age_field = IntegerField(default=0)
        age_field.name = "age"
        add_field = AddField("migration_test_model", age_field)
        alter_field = AlterField("migration_test_model", age_field)
        drop_field = RemoveField("migration_test_model", "age")
        # Write these operations to a migration file
        migration_file = tmp_path / "0002_auto.py"
        engine._write_migration_file(str(migration_file), [add_field, alter_field, drop_field])
        engine.migrate_direct(str(migration_file), connection=conn)
        conn.close()

        connection_manager.close_all()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
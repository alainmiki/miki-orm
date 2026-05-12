"""Database connection tests for SQLite, PostgreSQL, and MySQL adapters."""

from __future__ import annotations

import pytest
import sqlite3

from myorm.connections import SQLiteAdapter, SQLiteConnection
from myorm.connections.base import BaseAdapter, BaseConnection


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
        conn = adapter.create_pool({"NAME": ":memory:"})
        assert isinstance(conn, SQLiteConnection)


class TestPostgresAdapter:
    def test_module_imports(self):
        """psycopg2-based adapter should be importable."""
        from myorm.connections import PostgresAdapter, PostgresConnection
        adapter = PostgresAdapter()
        assert isinstance(adapter, BaseAdapter)

    def test_configured_database_properties(self):
        """Postgres config should correctly parse host, port, user, password, dbname."""
        import myorm
        myorm.configure({
            "default": {
                "ENGINE": "postgresql",
                "NAME": "test",
                "USER": "postgres",
                "PASSWORD": "admin",
                "HOST": "localhost",
                "PORT": 5432,
            }
        })
        from myorm.settings import settings
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
        import myorm
        from myorm.settings import connection_manager

        myorm.configure({
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
        from myorm.connections import MySQLAdapter, MySQLConnection
        adapter = MySQLAdapter()
        assert isinstance(adapter, BaseAdapter)


class TestConnectionManager:
    def test_get_connection_manager(self):
        from myorm.settings import connection_manager
        # Initially empty
        assert len(connection_manager._connections) == 0


class TestConfigure:
    def test_configure_exposed(self):
        import myorm
        assert hasattr(myorm, "configure")
        assert callable(myorm.configure)

    def test_configure_databases(self):
        import myorm
        myorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:"
            }
        })
        from myorm.settings import settings
        assert "default" in settings.databases


class TestMigrationWithSQLite:
    """Test full migration flow with SQLite in-memory database."""

    def test_makemigrations_creates_file(self, tmp_path):
        from myorm import models
        from myorm.migrations.engine import MigrationEngine

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
        import myorm
        myorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": ":memory:"
            }
        })
        from myorm.settings import connection_manager
        conn = connection_manager.get_connection("default")
        assert conn is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
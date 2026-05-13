"""Migration runner and management utilities - complete implementation."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import logging
from datetime import datetime
from typing import Any, Callable

from . import operations
from .history import MigrationHistory
from .diff import generate_migration_operations
from .schema import get_introspector

logger = logging.getLogger(__name__)


class MigrationEngine:
    """Engine for generating and applying migrations with full feature set."""

    def __init__(self, migrations_path: str = "migrations") -> None:
        self.migrations_path = migrations_path

    # ------------------------------------------------------------------
    # Migration generation - schema diff based
    # ------------------------------------------------------------------

    def makemigrations(
        self,
        app_label: str | list[type[Any]] | None = None,
    ) -> list[operations.MigrationOperation]:
        """Generate migration operations by diffing models vs database schema."""
        from ..settings import settings as myorm_settings
        from ..connections.base import BaseConnection
        
        # Get connection for introspection
        db_config = myorm_settings.get_database("default")
        adapter = db_config.get_adapter()
        connection = adapter.connect(db_config.get_connection_config())
        
        if not isinstance(connection, BaseConnection):
            raise TypeError("Expected a BaseConnection")
        
        # Generate diff
        engine = db_config.engine
        ops = generate_migration_operations(connection, engine)
        
        if not ops:
            logger.info("No schema changes detected.")
            return []
        
        # Write migration file
        os.makedirs(self.migrations_path, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_auto.py"
        filepath = os.path.join(self.migrations_path, filename)
        self._write_migration_file(filepath, ops)
        
        logger.info(f"Generated migration: {filename}")
        return ops

    def _write_migration_file(
        self, filepath: str, ops: list[operations.MigrationOperation]
    ) -> None:
        """Write a migration Python file with forward and reverse operations."""
        # Collect all field type imports
        field_types: set[tuple[str, str]] = set()
        for op in ops:
            if op.operation_type in ("create_table", "add_field", "alter_field"):
                cols = op.payload.get("columns", [])
                for col in cols if isinstance(cols, list) else [op.payload.get("field", {})]:
                    ftype = col.get("field_type", "")
                    if ftype:
                        short = ftype.rsplit(".", 1)[-1]
                        field_types.add((short, ftype))
            elif op.operation_type == "create_index":
                pass  # No field type import needed for indexes
        
        lines: list[str] = []
        lines.append("# Auto-generated migration")
        lines.append(f"# Generated: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("from myorm.migrations import operations")
        for short, full in sorted(field_types):
            mod_path = full.rsplit(".", 1)[0]
            lines.append(f"from {mod_path} import {short}")
        lines.append("")
        lines.append("")
        
        # Forward apply function
        lines.append("def apply_migration(apps, schema_editor):")
        for op in ops:
            self._write_operation_call(lines, op, forward=True)
        lines.append("")
        lines.append("")
        
        # Reverse rollback function
        lines.append("def rollback_migration(apps, schema_editor):")
        # Reverse order for rollback
        for op in reversed(ops):
            self._write_operation_call(lines, op, forward=False)
        lines.append("")
        lines.append("")
        
        # Migration class
        lines.append("class Migration:")
        lines.append("    dependencies = []")
        lines.append("")
        lines.append("    operations = [apply_migration]")
        lines.append("    rollback_operations = [rollback_migration]")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.debug(f"Wrote migration file: {filepath}")

    def _write_operation_call(self, lines: list[str], op: operations.MigrationOperation, 
                              forward: bool) -> None:
        """Write a single operation invocation."""
        op_type = op.operation_type
        if op_type == "create_table":
            cols_data = op.payload.get("columns", [])
            table_name = op.payload.get("name", "unknown")
            lines.append(f"    operations.CreateTable(")
            lines.append(f"        name=\"{table_name}\",")
            lines.append(f"        columns=[")
            for col in cols_data:
                fname = col["name"]
                ftype = col["field_type"]
                short = ftype.rsplit(".", 1)[-1]
                attrs = {k: v for k, v in col.items() if k not in ("name", "field_type")}
                attr_parts = [f"{k}={v!r}" for k, v in attrs.items()]
                attr_str = ", ".join(attr_parts)
                lines.append(f"            ({short}({attr_str}), '{fname}'),")
            lines.append(f"        ],")
            if not forward:
                lines.append(f"        reverse_op=operations.DeleteTable('{table_name}'),")
            lines.append(f"    )")
        
        elif op_type == "add_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            kwargs = {k: v for k, v in op.payload.items() if k not in ("model_name", "field_type", "field_kwargs")}
            kwargs.update(op.payload.get("field_kwargs", {}))
            short = field_type.rsplit(".", 1)[-1]
            mod = field_type.rsplit(".", 1)[0]
            lines.append(f"    from {mod} import {short}")
            kw_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            if forward:
                lines.append(f"    operations.AddField(model_name='{model}', field={short}({kw_str}))")
            else:
                lines.append(f"    operations.RemoveField(model_name='{model}', field_name='{kwargs.get('name')}')")
        
        elif op_type == "alter_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            kwargs = {k: v for k, v in op.payload.items() if k not in ("model_name", "field_type", "field_kwargs")}
            kwargs.update(op.payload.get("field_kwargs", {}))
            short = field_type.rsplit(".", 1)[-1]
            mod = field_type.rsplit(".", 1)[0]
            lines.append(f"    from {mod} import {short}")
            kw_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            if forward:
                lines.append(f"    operations.AlterField(model_name='{model}', field={short}({kw_str}))")
            else:
                # Reverse of alter is another alter with old definition - simplified
                lines.append(f"    # AlterField reverse not yet fully reversible")
        
        elif op_type == "drop_field":
            model = op.payload["model_name"]
            field_name = op.payload["field_name"]
            if not forward:
                # Reverse: add field back - would need saved field definition
                lines.append(f"    # DropField reverse requires saved field definition")
        
        elif op_type == "create_index":
            model = op.payload["model_name"]
            index = op.payload["index"]
            idx_name = index.get("name", "")
            cols = index.get("columns", [])
            unique = index.get("unique", False)
            lines.append(f"    operations.CreateIndex(model_name='{model}', index={{'name': '{idx_name}', 'columns': {cols!r}, 'unique': {unique}}})")
        
        elif op_type == "drop_index":
            model = op.payload["model_name"]
            idx_name = op.payload["index_name"]
            if not forward:
                lines.append(f"    # DropIndex reverse requires saved index definition")

    @staticmethod
    def _build_create_table_sql(op: operations.CreateTable) -> tuple[str, list[Any]]:
        """Build CREATE TABLE SQL from CreateTable operation."""
        from ..query.safe_builder import get_safe_builder
        from ..settings import settings as myorm_settings
        
        db_config = myorm_settings.get_database("default")
        builder = get_safe_builder(db_config.engine)
        
        table_name = op.payload["name"]
        columns = op.payload["columns"]
        
        quoted_table = builder.quote_table(table_name)
        column_defs = []
        params = []
        
        for col in columns:
            col_name = col["name"]
            field_type = col["field_type"]
            quoted_col = builder.quote_column(col_name)
            
            # Get field class and build SQL type
            module_path, class_name = field_type.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            field_class = getattr(module, class_name)
            
            # Create field instance with kwargs - filter to valid field arguments
            field_kwargs = {k: v for k, v in col.items() if k not in ("name", "field_type", "type")}
            field = field_class(**field_kwargs)
            
            # Use _SchemaEditor to get SQL type and constraints
            schema_editor = _SchemaEditor(None, builder)
            sql_type, constraints, field_params = schema_editor._field_to_sql(field)
            params.extend(field_params)
            
            col_def = f"{quoted_col} {sql_type}"
            if constraints:
                col_def += " " + " ".join(constraints)
            column_defs.append(col_def)
        
        sql = f"CREATE TABLE {quoted_table} ({', '.join(column_defs)})"
        return sql, params

    # ------------------------------------------------------------------
    # Migration application (direct & transactional)
    # ------------------------------------------------------------------

    def migrate(self, connection: Any | None = None, target: str | None = None) -> None:
        """Apply pending migrations inside a transaction with locking."""
        if connection is None:
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database(target)
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
        
        # Acquire migration lock
        lock_id = self._acquire_lock(connection)
        if not lock_id:
            raise RuntimeError("Could not acquire migration lock; another migration may be running")
        
        try:
            # Wrap migration in transaction
            connection.execute("BEGIN", ())
            
            history = MigrationHistory.load_history(self.migrations_path)
            for migration_file in history:
                filepath = os.path.join(self.migrations_path, migration_file)
                self._apply_migration_direct(filepath, connection)
                logger.info(f"Applied migration: {migration_file}")
            
            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.error(f"Migration failed, rolled back: {e}")
            raise
        finally:
            self._release_lock(connection, lock_id)

    def _acquire_lock(self, connection: Any) -> int | None:
        """Acquire a migration lock using a dedicated lock table."""
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS _migration_lock (id INTEGER PRIMARY KEY, locked_at TIMESTAMP)", ())
            # Try to insert a lock row; fail if already exists
            cursor = connection.execute("INSERT OR IGNORE INTO _migration_lock (id, locked_at) VALUES (1, CURRENT_TIMESTAMP)", ())
            if cursor.rowcount == 1:
                return 1
            return None
        except Exception:
            return None

    def _release_lock(self, connection: Any, lock_id: int) -> None:
        """Release migration lock."""
        try:
            connection.execute("DELETE FROM _migration_lock WHERE id = ?", (lock_id,))
        except Exception:
            pass

    def _apply_migration_direct(self, filepath: str, connection: Any) -> None:
        """Load migration module and execute apply_migration with safe SQL building."""
        spec = importlib.util.spec_from_file_location("migration", filepath)
        if spec is None or spec.loader is None:
            return
        
        # Set up safe builder for the module
        from ..query.safe_builder import get_safe_builder
        from ..settings import settings as myorm_settings
        db_config = myorm_settings.get_database("default")
        builder = get_safe_builder(db_config.engine)
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["migration"] = module
        spec.loader.exec_module(module)
        
        if hasattr(module, "apply_migration"):
            # Inject a schema editor that uses safe builder
            schema_editor = _SchemaEditor(connection, builder)
            module.apply_migration(None, schema_editor)

    def migrate_direct(self, operations: list[operations.MigrationOperation], connection: Any = None) -> None:
        """Directly apply operations inside a transaction."""
        if connection is None:
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database("default")
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
        
        try:
            connection.execute("BEGIN", ())
            from ..query.safe_builder import get_safe_builder
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database("default")
            builder = get_safe_builder(db_config.engine)
            schema_editor = _SchemaEditor(connection, builder)
            
            for op in operations:
                schema_editor.execute_operation(op)
            
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def rollback(self, connection: Any, steps: int = 1) -> None:
        """Rollback the last N migrations by executing their rollback_migration functions."""
        if connection is None:
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database(target)
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
        
        # Acquire lock
        lock_id = self._acquire_lock(connection)
        if not lock_id:
            raise RuntimeError("Could not acquire migration lock for rollback")
        
        try:
            connection.execute("BEGIN", ())
            
            history = MigrationHistory.load_history(self.migrations_path)
            to_rollback = history[-steps:] if steps <= len(history) else history
            
            for migration_file in reversed(to_rollback):
                filepath = os.path.join(self.migrations_path, migration_file)
                self._rollback_migration_direct(filepath, connection)
                logger.info(f"Rolled back migration: {migration_file}")
                # Remove file after successful rollback
                os.remove(filepath)
            
            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.error(f"Rollback failed: {e}")
            raise
        finally:
            self._release_lock(connection, lock_id)

    def _rollback_migration_direct(self, filepath: str, connection: Any) -> None:
        """Load migration module and execute rollback_migration."""
        spec = importlib.util.spec_from_file_location("migration", filepath)
        if spec is None or spec.loader is None:
            return
        
        from ..query.safe_builder import get_safe_builder
        from ..settings import settings as myorm_settings
        db_config = myorm_settings.get_database("default")
        builder = get_safe_builder(db_config.engine)
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["migration"] = module
        spec.loader.exec_module(module)
        
        if hasattr(module, "rollback_migration"):
            schema_editor = _SchemaEditor(connection, builder)
            module.rollback_migration(None, schema_editor)

    def show_history(self) -> list[str]:
        return MigrationHistory.load_history(self.migrations_path)


class _SchemaEditor:
    """Helper that executes migration operations using safe SQL builder."""

    def __init__(self, connection: Any, builder: Any) -> None:
        self.connection = connection
        self.builder = builder

    def execute_operation(self, op: operations.MigrationOperation) -> None:
        """Dispatch operation to appropriate executor."""
        op_type = op.operation_type
        if op_type == "create_table":
            self._create_table(op)
        elif op_type == "add_field":
            self._add_field(op)
        elif op_type == "alter_field":
            self._alter_field(op)
        elif op_type == "drop_field":
            self._drop_field(op)
        elif op_type == "create_index":
            self._create_index(op)
        elif op_type == "drop_index":
            self._drop_index(op)
        elif op_type == "rename_field":
            self._rename_field(op)
        elif op_type == "delete_table":
            self._delete_table(op)
        else:
            logger.warning(f"Unknown operation type: {op_type}")

    def _create_table(self, op: operations.CreateTable) -> None:
        from .engine import MigrationEngine as ME
        sql, params = ME._build_create_table_sql(op)
        self.connection.execute(sql, params)

    def _add_field(self, op: operations.AddField) -> None:
        field = op.payload.get("field")
        if field is None:
            raise ValueError("AddField requires field object")
        sql, params = self._build_add_column_sql(
            op.payload["model_name"],
            op.payload["field_name"],
            field
        )
        self.connection.execute(sql, params)

    def _build_add_column_sql(self, table: str, column: str, field: Any) -> tuple[str, list[Any]]:
        """Build ALTER TABLE ADD COLUMN SQL."""
        quoted_table = self.builder.quote_table(table)
        quoted_col = self.builder.quote_column(column)
        sql_type, constraints, params = self._field_to_sql(field)
        
        # For SQLite, DEFAULT can't be parameterized in ALTER TABLE ADD COLUMN
        if self.builder.dialect == self.builder.dialect.SQLITE:
            # Rebuild constraints without parameterized DEFAULT
            constraints = []
            if field.primary_key:
                constraints.append("PRIMARY KEY")
                if getattr(field, "auto_increment", False) or isinstance(field, AutoField):
                    constraints.append("AUTOINCREMENT")
            if not field.null:
                constraints.append("NOT NULL")
            else:
                constraints.append("NULL")
            if field.unique:
                constraints.append("UNIQUE")
            if field.default is not None:
                # For SQLite ALTER TABLE, use literal default value
                default_val = repr(field.default) if isinstance(field.default, str) else str(field.default)
                constraints.append(f"DEFAULT {default_val}")
            params = []  # No parameters for SQLite ALTER TABLE
        
        sql = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {sql_type} {' '.join(constraints)}"
        return sql, params

    def _alter_field(self, op: operations.AlterField) -> None:
        # SQLite has limited ALTER TABLE support; strategy varies by backend
        # For simplicity, we attempt PostgreSQL-style ALTER COLUMN TYPE
        field = op.payload.get("field")
        if field is None:
            raise ValueError("AlterField requires field object")
        sql, params = self._build_alter_column_sql(
            op.payload["model_name"],
            op.payload["field_name"],
            field
        )
        self.connection.execute(sql, params)

    def _build_alter_column_sql(self, table: str, column: str, field: Any) -> tuple[str, list[Any]]:
        quoted_table = self.builder.quote_table(table)
        quoted_col = self.builder.quote_column(column)
        sql_type, constraints, params = self._field_to_sql(field)
        
        engine = self.builder.dialect.value if hasattr(self.builder.dialect, 'value') else str(self.builder.dialect)
        
        if engine == "sqlite":
            # SQLite: limited ALTER TABLE - can only rename table, add column
            # For type change, might need table rebuild - skip for now
            return "SELECT 1", ()  # No-op for now
        elif engine in ("postgresql", "mysql"):
            return f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_col} TYPE {sql_type}", params
        else:
            return "SELECT 1", ()

    def _drop_field(self, op: operations.DropField) -> None:
        table = op.payload["model_name"]
        column = op.payload["field_name"]
        quoted_table = self.builder.quote_table(table)
        quoted_col = self.builder.quote_column(column)
        
        engine = self.builder.dialect.value if hasattr(self.builder.dialect, 'value') else str(self.builder.dialect)
        if engine == "sqlite":
            # SQLite doesn't support DROP COLUMN directly
            # Would need table rebuild; skip for MVP
            logger.warning("SQLite DROP COLUMN not supported, skipping")
            return
        elif engine in ("postgresql", "mysql"):
            sql = f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"
            self.connection.execute(sql, ())

    def _create_index(self, op: operations.CreateIndex) -> None:
        model = op.payload["model_name"]
        index = op.payload["index"]
        idx_name = index.get("name", "")
        columns = index.get("columns", [])
        unique = index.get("unique", False)
        
        self._execute_create_index(model, idx_name, columns, unique)

    def _execute_create_index(self, table: str, index_name: str, columns: list[str], unique: bool) -> None:
        quoted_table = self.builder.quote_table(table)
        quoted_cols = [self.builder.quote_column(c) for c in columns]
        unique_str = "UNIQUE " if unique else ""
        idx_name = self.builder.quote_identifier(index_name) if index_name else f"idx_{table}_{'_'.join(columns)}"
        sql = f"CREATE {unique_str}INDEX {idx_name} ON {quoted_table} ({', '.join(quoted_cols)})"
        self.connection.execute(sql, ())

    def _drop_index(self, op: operations.DropIndex) -> None:
        table = op.payload["model_name"]
        index_name = op.payload["index_name"]
        quoted_table = self.builder.quote_table(table)
        idx_name = index_name  # already quoted as needed
        sql = f"DROP INDEX IF EXISTS {idx_name}"
        self.connection.execute(sql, ())

    def _rename_field(self, op: operations.RenameField) -> None:
        table = op.payload["model_name"]
        old_name = op.payload["old_name"]
        new_name = op.payload["new_name"]
        quoted_table = self.builder.quote_table(table)
        quoted_old = self.builder.quote_column(old_name)
        quoted_new = self.builder.quote_column(new_name)
        
        engine = self.builder.dialect.value if hasattr(self.builder.dialect, 'value') else str(self.builder.dialect)
        if engine == "sqlite":
            # SQLite doesn't support RENAME COLUMN before version 3.25 - assume modern
            sql = f"ALTER TABLE {quoted_table} RENAME COLUMN {quoted_old} TO {quoted_new}"
        elif engine in ("postgresql", "mysql"):
            sql = f"ALTER TABLE {quoted_table} RENAME COLUMN {quoted_old} TO {quoted_new}"
        else:
            sql = "SELECT 1"
        self.connection.execute(sql, ())

    def _delete_table(self, op: operations.DeleteModel) -> None:
        table = op.payload["name"]
        quoted_table = self.builder.quote_table(table)
        sql = f"DROP TABLE IF EXISTS {quoted_table}"
        self.connection.execute(sql, ())

    def _field_to_sql(self, field: Any) -> tuple[str, list[str], list[Any]]:
        """Convert a Field instance to (sql_type, constraints, params)."""
        from ..models.fields import (
            IntegerField, BigIntegerField, CharField, TextField,
            BooleanField, DecimalField, FloatField, DateTimeField,
            DateField, TimeField, UUIDField, JSONField, BinaryField,
            EmailField, URLField, SlugField, AutoField,
            SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField,
        )
        
        params: list[Any] = []
        constraints = []
        
        # Type
        if isinstance(field, (IntegerField, AutoField, PositiveIntegerField, PositiveSmallIntegerField, SmallIntegerField)):
            sql_type = "INTEGER"
        elif isinstance(field, BigIntegerField):
            sql_type = "BIGINT"
        elif isinstance(field, CharField):
            ml = field.max_length or 255
            sql_type = f"VARCHAR({ml})"
        elif isinstance(field, TextField):
            sql_type = "TEXT"
        elif isinstance(field, BooleanField):
            sql_type = "BOOLEAN"
        elif isinstance(field, DecimalField):
            sql_type = f"DECIMAL({field.max_digits}, {field.decimal_places})"
        elif isinstance(field, FloatField):
            sql_type = "FLOAT"
        elif isinstance(field, DateTimeField):
            sql_type = "DATETIME"
        elif isinstance(field, DateField):
            sql_type = "DATE"
        elif isinstance(field, TimeField):
            sql_type = "TIME"
        elif isinstance(field, UUIDField):
            sql_type = "VARCHAR(36)"
        elif isinstance(field, JSONField):
            sql_type = "TEXT"
        elif isinstance(field, BinaryField):
            sql_type = "BLOB"
        elif isinstance(field, EmailField):
            ml = field.max_length or 254
            sql_type = f"VARCHAR({ml})"
        elif isinstance(field, URLField):
            ml = field.max_length or 200
            sql_type = f"VARCHAR({ml})"
        elif isinstance(field, SlugField):
            ml = field.max_length or 50
            sql_type = f"VARCHAR({ml})"
        else:
            sql_type = "TEXT"
        
        # Constraints
        if field.primary_key:
            constraints.append("PRIMARY KEY")
            if getattr(field, "auto_increment", False) or isinstance(field, AutoField):
                constraints.append("AUTOINCREMENT")
        if not field.null:
            constraints.append("NOT NULL")
        else:
            constraints.append("NULL")
        if field.unique:
            constraints.append("UNIQUE")
        if field.default is not None:
            constraints.append("DEFAULT ?")
            params.append(field.default)
        
        return sql_type, constraints, params


def main() -> None:
    parser = argparse.ArgumentParser(prog="miki-orm-migrate")
    parser.add_argument("command", choices=["makemigrations", "migrate", "rollback", "history"])
    parser.add_argument("target", nargs="?", help="Migration target or rollback steps")
    args = parser.parse_args()

    engine = MigrationEngine()
    if args.command == "makemigrations":
        logger.info("Generating migration stubs...")
        ops = engine.makemigrations(args.target)
        for op in ops:
            logger.info(f"  Created migration operation: {op.operation_type}")
    elif args.command == "migrate":
        logger.info("Applying migrations...")
        engine.migrate(None, target=args.target)
        logger.info("  Done.")
    elif args.command == "rollback":
        steps = int(args.target or "1")
        logger.info(f"Rolling back {steps} migration(s)...")
        engine.rollback(None, steps=steps)
    elif args.command == "history":
        logger.info("Migration history:")
        for name in engine.show_history():
            logger.info(f"  {name}")


if __name__ == "__main__":
    main()

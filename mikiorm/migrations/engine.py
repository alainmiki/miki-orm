"""Migration runner and management utilities - production-ready implementation."""

from __future__ import annotations

import argparse
import importlib.util
import importlib
import os
import sys
import logging
import shutil
import uuid
from datetime import datetime
from typing import Any, Callable
from functools import wraps

from . import operations
from .operations import MigrationOperation
from .history import MigrationHistory
from .diff import generate_migration_operations
from .editor import CollectingSchemaEditor
from .validation import MigrationFileValidator, MigrationPathValidator
from .retry import retry_with_backoff, RetryConfig, is_transient_error
from mikiorm.backends.base.dialect import Dialect
from mikiorm.backends.base.schema_editor import field_to_sql_type, _safe_default_literal

logger = logging.getLogger(__name__)


class MigrationEngine:
    """Engine for generating and applying migrations with production safety."""

    def __init__(self, migrations_path: str | None = None) -> None:
        from ..conf.settings import settings

        self.migrations_path = migrations_path or settings.migration_path
        self._discovered = False
        self.retry_config = RetryConfig(max_retries=3)

    def _ensure_migrations_table(self, connection: Any, target: str = "default") -> None:
        """Ensure the migrations tracking table exists."""
        from ..backends.base.dialect import get_safe_builder
        from ..conf.settings import settings

        db_config = settings.get_database(target)
        builder = get_safe_builder(db_config.engine)

        quoted_table = builder.quote_table("_mikiorm_migrations")

        if db_config.engine == "postgresql":
            sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'applied' CHECK (status IN ('applied', 'rolled_back'))
            )"""
        else:
            # SQLite / MySQL
            auto_inc = (
                "AUTOINCREMENT" if db_config.engine == "sqlite" else "AUTO_INCREMENT"
            )
            sql = f"""CREATE TABLE IF NOT EXISTS {quoted_table} (
                id INTEGER PRIMARY KEY {auto_inc},
                name VARCHAR(255) UNIQUE NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'applied' CHECK (status IN ('applied', 'rolled_back'))
            )"""

        connection.execute(sql, ())

    def get_applied_migrations(self, connection: Any, target: str = "default") -> list[str]:
        """Return a list of applied migration names from the database."""
        from ..backends.base.dialect import get_safe_builder
        from ..conf.settings import settings

        db_config = settings.get_database(target)
        builder = get_safe_builder(db_config.engine)

        quoted_table = builder.quote_table("_mikiorm_migrations")
        sql = f"SELECT name FROM {quoted_table} ORDER BY applied_at ASC, id ASC"
        rows = connection.fetchall(sql, ())
        return [row[0] for row in rows]

    def get_unapplied_migrations(self, connection: Any, target: str = "default") -> list[str]:
        """Return a list of migration files that exist on disk but are not in the DB."""
        applied = self.get_applied_migrations(connection, target)
        history = MigrationHistory.load_history(self.migrations_path)
        return [m for m in history if m not in applied]

    # ------------------------------------------------------------------
    # Migration generation - schema diff based
    # ------------------------------------------------------------------

    def makemigrations(
        self,
        app_label: str | list[type[Any]] | None = None,
    ) -> list[operations.MigrationOperation]:
        """
        Generate migration operations by diffing models vs database schema.
        """
        from ..settings import settings
        from ..backends.base.base import BaseConnection

        # Get connection for introspection
        db_config = settings.get_database("default")
        adapter = db_config.get_adapter()
        connection = adapter.connect(db_config.get_connection_config())

        try:
            self.discover_models()

            from ..models.registry import ModelRegistry
            if not ModelRegistry.all_models():
                logger.warning("No registered models found. Ensure modules with @register are imported.")
                return []

            if not isinstance(connection, BaseConnection):
                raise TypeError("Expected a BaseConnection")

            ops = self.get_missing_migration_operations(connection)
            if not ops:
                logger.info("No schema changes detected.")
                return []

            # Enforce workflow: write the file, do not apply here.
            return self._save_migration(ops)
        finally:
            connection.close()

    def discover_models(self) -> None:
        """Scan configured model paths to trigger registration."""
        if self._discovered:
            return

        from ..conf.settings import settings
        if not settings.model_paths:
            self._discovered = True
            return

        for path in settings.model_paths:
            abs_path = os.path.abspath(path)
            if not os.path.exists(abs_path):
                logger.warning(f"Model path does not exist: {abs_path}")
                continue
            
            if abs_path not in sys.path:
                sys.path.insert(0, abs_path)
            
            for root, _, files in os.walk(abs_path):
                for file in files:
                    if file.endswith(".py") and file != "__init__.py":
                        module_path = os.path.join(root, file)
                        rel_path = os.path.relpath(module_path, abs_path)
                        module_name = rel_path[:-3].replace(os.sep, ".")
                        try:
                            importlib.import_module(module_name)
                        except Exception as e:
                            logger.debug(f"Failed to import discovered module {module_name}: {e}")
        self._discovered = True

    def get_missing_migration_operations(self, connection: Any) -> list[operations.MigrationOperation]:
        """Generate operations for model changes not yet captured in migration files."""
        self.discover_models()
        from ..conf.settings import settings
        db_config = settings.get_database("default")
        
        ops = generate_migration_operations(connection, db_config.engine)
        
        # Validate operations
        self._validate_operations(ops)
        
        return ops

    def _validate_operations(self, ops: list[operations.MigrationOperation]) -> None:
        """Validate migration operations for common issues."""
        seen_names = set()
        for op in ops:
            # Check for duplicate operations on same table/field
            if op.operation_type == "create_table":
                table_name = op.payload.get("name", "")
                if table_name in seen_names:
                    logger.warning(f"Duplicate create_table operation for table: {table_name}")
                seen_names.add(table_name)
            elif op.operation_type in ("add_field", "alter_field", "drop_field", "remove_field"):
                field_key = (op.payload.get("model_name", ""), op.payload.get("field_name", ""))
                if field_key in seen_names:
                    logger.warning(f"Multiple operations on field: {field_key}")
                seen_names.add(field_key)


    def _save_migration(self, ops: list[operations.MigrationOperation]) -> list[operations.MigrationOperation]:
            os.makedirs(self.migrations_path, exist_ok=True) 
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_auto.py"
            filepath = os.path.join(self.migrations_path, filename)
            self._write_migration_file(filepath, ops)

            logger.info(f"Generated migration: {filename}")
            return ops

    def _apply_operations_internally(
        self, operations: list[operations.MigrationOperation], connection: Any = None, target: str = "default"
    ) -> None:
        """Internal helper to apply operations without a migration file."""
        self.discover_models()
        backend_editor = self._get_backend_editor(connection, target=target)
        schema_editor = _MigrationSchemaEditor(backend_editor)
        self._apply_migration_operations(operations, connection)

    def _write_migration_file(
        self, filepath: str, ops: list[operations.MigrationOperation]
    ) -> None:
        """Write a migration Python file with forward and reverse operations (atomically)."""
        # Collect all field type imports
        field_types: set[tuple[str, str]] = set()
        for op in ops:
            if op.operation_type in ("create_table", "add_field", "alter_field"):
                cols = op.payload.get("columns", [])
                items = list(cols) if isinstance(cols, list) else [op.payload]
                if "old_field_type" in op.payload:
                    items.append({"field_type": op.payload["old_field_type"]})
                
                for item in items:
                    ftype = item.get("field_type", "")
                    if ftype:
                        short = ftype.rsplit(".", 1)[-1]
                        field_types.add((short, ftype))
            elif op.operation_type == "create_index":
                pass  # No field type import needed for indexes

        lines: list[str] = []
        lines.append("# Auto-generated migration")
        lines.append(f"# Generated: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("from mikiorm.migrations import operations")
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

        # Atomic file write: write to temp file first, then rename
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        tmp_filepath = f"{filepath}.tmp"
        try:
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            os.replace(tmp_filepath, filepath)
            logger.debug(f"Wrote migration file: {filepath}")
        except Exception as e:
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)
            raise RuntimeError(f"Failed to write migration file: {e}")

    def _write_operation_call(self, lines: list[str], op: operations.MigrationOperation, 
                              forward: bool) -> None:
        """Write a single operation invocation."""
        op_type = op.operation_type
        if op_type == "create_table":
            cols_data = op.payload.get("columns", [])
            table_name = op.payload.get("name", "unknown")
            lines.append(f"    schema_editor.execute_operation(operations.CreateTable(")
            lines.append(f"        name=\"{table_name}\",")
            lines.append(f"        columns=[")
            for col in cols_data:
                fname = col["name"]
                ftype = col["field_type"]
                short = ftype.rsplit(".", 1)[-1]
                attrs = {k: v for k, v in col.items() if k not in ("name", "field_type", "type")}
                attr_parts = [f"{k}={repr(v)}" for k, v in attrs.items()]
                attr_str = ", ".join(attr_parts)
                lines.append(f"            ({short}({attr_str}), '{fname}'),")
            lines.append(f"        ],")
            if not forward:
                lines.append(f"        reverse_op=operations.DeleteTable('{table_name}'),")
            lines.append(f"    )")
            lines.append(f"    )")
        elif op_type == "add_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            kwargs = {k: v for k, v in op.payload.items() if k not in ("model_name", "field_type", "field_kwargs")}
            kwargs.update(op.payload.get("field_kwargs", {}))
            short = field_type.rsplit(".", 1)[-1]
            mod = field_type.rsplit(".", 1)[0]
            kw_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            if forward:
                lines.append(f"    schema_editor.execute_operation(operations.AddField(model_name='{model}', field={short}({kw_str})))")
            else:
                lines.append(f"    schema_editor.execute_operation(operations.RemoveField(model_name='{model}', field_name='{kwargs.get('name')}'))")

        elif op_type == "alter_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            kwargs = {k: v for k, v in op.payload.items() if k not in ("model_name", "field_type", "field_kwargs")}
            kwargs.update(op.payload.get("field_kwargs", {}))
            short = field_type.rsplit(".", 1)[-1]
            kw_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())

            old_field_str = ""
            if "old_field_type" in op.payload:
                old_type = op.payload["old_field_type"]
                old_kwargs = op.payload["old_field_kwargs"]
                old_short = old_type.rsplit(".", 1)[-1]
                old_kw_str = ", ".join(f"{k}={v!r}" for k, v in old_kwargs.items())
                old_field_str = f", old_field={old_short}({old_kw_str})"

            if forward:
                lines.append(f"    schema_editor.execute_operation(operations.AlterField(model_name='{model}', field={short}({kw_str}){old_field_str}))")
            else:
                if "old_field_type" in op.payload:
                    old_type = op.payload["old_field_type"]
                    old_kwargs = op.payload["old_field_kwargs"]
                    old_short = old_type.rsplit(".", 1)[-1]
                    old_kw_str = ", ".join(f"{k}={v!r}" for k, v in old_kwargs.items())
                    lines.append(f"    schema_editor.execute_operation(operations.AlterField(model_name='{model}', field={old_short}({old_kw_str}), old_field={short}({kw_str})))")
                else:
                    lines.append(f"    # AlterField reverse requires saved old field definition")

        elif op_type == "drop_field":
            model = op.payload["model_name"]
            field_name = op.payload["field_name"]
            if forward:
                lines.append(f"    schema_editor.execute_operation(operations.RemoveField(model_name='{model}', field_name='{field_name}'))")
            if not forward:
                # Reverse: add field back - would need saved field definition
                lines.append(f"    # DropField reverse requires saved field definition")

        elif op_type == "create_index":
            model = op.payload["model_name"]
            index = op.payload["index"]
            idx_name = index.get("name", "")
            cols = index.get("columns", [])
            unique = index.get("unique", False)
            lines.append(f"    schema_editor.execute_operation(operations.CreateIndex(model_name='{model}', index={{'name': '{idx_name}', 'columns': {cols!r}, 'unique': {unique}}}))")

        elif op_type == "drop_index":
            model = op.payload["model_name"]
            idx_name = op.payload["index_name"]
            if not forward:
                lines.append(f"    # DropIndex reverse requires saved index definition")

    @staticmethod
    def _build_create_table_sql(op: operations.CreateTable, schema_editor: Any) -> tuple[str, list[Any]]:
        """Build CREATE TABLE SQL from CreateTable operation."""
        builder = schema_editor.builder

        table_name = op.payload["name"]
        columns = op.payload["columns"]

        quoted_table = builder.quote_table(table_name)
        column_defs: list[str] = []
        params: list[Any] = []

        for col in columns:
            # Accept both dict format (from diff generator) and
            # (field_instance, field_name) tuple format (from persisted files).
            if isinstance(col, (list, tuple)) and len(col) == 2:
                field_instance, col_name = col
                field_instance.name = col_name
            else:
                col_name = col["name"]
                if isinstance(col, dict):
                    field_type_str = col.get("field_type", "")
                    field_kwargs = {
                        k: v for k, v in col.items()
                        if k not in ("name", "field_type", "type")
                    }
                    field_kwargs["name"] = col_name
                    module_path, class_name = field_type_str.rsplit(".", 1)
                    module = __import__(module_path, fromlist=[class_name])
                    field_class = getattr(module, class_name)
                    field_instance = field_class(**field_kwargs)

            col_def, field_params = schema_editor._column_def(field_instance)
            params.extend(field_params)
            column_defs.append(col_def)

        sql = f"CREATE TABLE {quoted_table} ({', '.join(column_defs)})"
        return sql, params

    # ------------------------------------------------------------------
    # Migration application (direct & transactional)
    # ------------------------------------------------------------------

    def migrate(self, connection: Any | None = None, target: str | None = None) -> None:
        """Apply pending migrations inside a transaction with locking."""
        target_alias = target or "default"
        own_connection = False
        if connection is None:
            from ..conf.settings import settings
            db_config = settings.get_database(target_alias)
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
            own_connection = True

        from ..unit_of_work.transaction import atomic
        from ..backends.base.dialect import get_safe_builder
        from ..conf.settings import settings

        db_config = settings.get_database(target_alias)
        is_sqlite = db_config.engine == "sqlite"

        try:
            # Ensure all models are registered before migration begins
            self.discover_models()

            # Ensure infrastructure exists (outside main transaction for safety)
            self._ensure_migrations_table(connection, target_alias)
            
            # Acquire migration lock to prevent concurrent migrations
            lock_id = self._acquire_lock(connection, target_alias)
            if not lock_id:
                raise RuntimeError("Could not acquire migration lock; another migration may be running")

            try:
                applied = self.get_applied_migrations(connection, target_alias)
                history = MigrationHistory.load_history(self.migrations_path)
                pending = [m for m in history if m not in applied]

                if not pending:
                    logger.info("No migrations to apply.")
                    return

                # SQLite Safety: backup file before destructive changes
                if is_sqlite:
                    has_destructive = any(self._is_destructive(os.path.join(self.migrations_path, m)) for m in pending)
                    if has_destructive:
                        db_path = db_config.get_connection_config().get("name")
                        if db_path and db_path != ":memory:":
                            self._create_sqlite_backup(db_path)
                
                builder = get_safe_builder(db_config.engine)
                quoted_table = builder.quote_table("_mikiorm_migrations")
                ph = builder.param_placeholder

                # Apply each migration atomically
                for migration_file in pending:
                    filepath = os.path.join(self.migrations_path, migration_file)
                    try:
                        # Each migration in its own transaction for atomicity
                        with atomic(connection=connection):
                            self._apply_migration_direct(filepath, connection, target=target_alias)
                            # Record application
                            sql = f"INSERT INTO {quoted_table} (name) VALUES ({ph})"
                            connection.execute(sql, (migration_file,))
                            logger.info(f"Applied migration: {migration_file}")
                    except Exception as e:
                        logger.error(f"Failed to apply migration {migration_file}: {e}", exc_info=True)
                        raise
            finally:
                self._release_lock(connection, lock_id, target_alias)

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise
        finally:
            if own_connection:
                connection.close()

    def _is_destructive(self, filepath: str) -> bool:
        """Heuristic to check if a migration contains destructive operations."""
        destructive_keywords = (
            "RemoveField", "DropField", "DeleteTable", 
            "DeleteModel", "DropIndex", "AlterField"
        )
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                return any(kw in content for kw in destructive_keywords)
        except Exception:
            return False

    def _create_sqlite_backup(self, db_path: str) -> str | None:
        """Create a backup of the SQLite database file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.{timestamp}.bak"
        try:
            shutil.copy2(db_path, backup_path)
            logger.info(f"Created SQLite database backup: {backup_path}")
            logger.info(f"Safety backup created: {backup_path}")
            return backup_path
        except Exception as e:
            logger.warning(f"Failed to create SQLite backup: {e}")
            return None

    def _acquire_lock(self, connection: Any, target: str = "default") -> int | None:
        """Acquire a migration lock using a dedicated lock table."""
        from ..conf.settings import settings
        db_config = settings.get_database(target)

        if db_config.engine == "postgresql":
            # Use native Postgres advisory lock
            connection.execute("SELECT pg_advisory_lock(1337)", ())
            return 1337

        try:
            connection.execute("CREATE TABLE IF NOT EXISTS _mikiorm_migration_lock (id INTEGER PRIMARY KEY, locked_at TIMESTAMP)", ())
            # dialect-aware insert ignore
            sql = "INSERT OR IGNORE INTO _mikiorm_migration_lock (id, locked_at) VALUES (1, CURRENT_TIMESTAMP)"
            if db_config.engine == "mysql":
                sql = "INSERT IGNORE INTO _mikiorm_migration_lock (id, locked_at) VALUES (1, CURRENT_TIMESTAMP)"
            
            cursor = connection.execute(sql, ())
            if cursor.rowcount == 1:
                return 1
            return None
        except Exception:
            return None

    def _release_lock(self, connection: Any, lock_id: int, target: str = "default") -> None:
        """Release migration lock."""
        from ..conf.settings import settings
        db_config = settings.get_database(target)

        if db_config.engine == "postgresql" and lock_id == 1337:
            connection.execute("SELECT pg_advisory_unlock(1337)", ())
            return

        try:
            connection.execute("DELETE FROM _mikiorm_migration_lock WHERE id = ?", (lock_id,))
        except Exception:
            pass

    def _apply_migration_direct(self, filepath: str, connection: Any, target: str = "default") -> None:
        """Load migration module and execute apply_migration with safe SQL building."""
        spec = importlib.util.spec_from_file_location("migration", filepath)
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules["migration"] = module
        spec.loader.exec_module(module)

        if hasattr(module, "apply_migration"):
            # Obtain backend-specific schema editor
            backend_editor = self._get_backend_editor(connection, target=target)
            schema_editor = _MigrationSchemaEditor(backend_editor)
            module.apply_migration(None, schema_editor)

    def rollback(self, connection: Any = None, steps: int = 1, target: str | None = None) -> None:
        """Rollback applied migrations and update tracking history."""
        target_alias = target or "default"
        own_connection = False
        if connection is None:
            from ..conf.settings import settings
            db_config = settings.get_database(target_alias)
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
            own_connection = True

        from ..unit_of_work.transaction import atomic
        from ..backends.base.dialect import get_safe_builder
        from ..conf.settings import settings

        try:
            self.discover_models()
            self._ensure_migrations_table(connection, target_alias)
            lock_id = self._acquire_lock(connection, target_alias)
            if not lock_id:
                raise RuntimeError("Could not acquire migration lock for rollback")

            try:
                applied = self.get_applied_migrations(connection, target_alias)
                if not applied:
                    logger.info("No migrations to rollback.")
                    return

                db_config = settings.get_database(target_alias)
                builder = get_safe_builder(db_config.engine)
                quoted_table = builder.quote_table("_mikiorm_migrations")
                ph = builder.param_placeholder

                history = MigrationHistory.load_history(self.migrations_path)
                to_rollback = history[-steps:] if steps <= len(history) else history
                
                # Rollback each migration in reverse order, each in its own transaction
                for migration_file in reversed(to_rollback):
                    filepath = os.path.join(self.migrations_path, migration_file)
                    if not os.path.exists(filepath):
                        logger.warning(f"Migration file missing for rollback: {migration_file}")
                        continue

                    try:
                        with atomic(connection=connection):
                            self._rollback_migration_direct(filepath, connection, target=target_alias)
                            
                            # Remove from DB history
                            sql = f"DELETE FROM {quoted_table} WHERE name = {ph}"
                            connection.execute(sql, (migration_file,))
                            logger.info(f"Rolled back: {migration_file}")
                    except Exception as e:
                        logger.error(f"Failed to rollback {migration_file}: {e}", exc_info=True)
                        raise

            finally:
                self._release_lock(connection, lock_id, target_alias)
        except Exception as e:
            logger.error(f"Rollback failed: {e}", exc_info=True)
            raise
        finally:
            if own_connection:
                connection.close()

    def _rollback_migration_direct(self, filepath: str, connection: Any, target: str = "default") -> None:
        """Load migration module and execute rollback_migration."""
        spec = importlib.util.spec_from_file_location("migration", filepath)
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules["migration"] = module
        spec.loader.exec_module(module)

        if hasattr(module, "rollback_migration"):
            backend_editor = self._get_backend_editor(connection, target=target)
            schema_editor = _MigrationSchemaEditor(backend_editor)
            module.rollback_migration(None, schema_editor)

    def _get_backend_editor(self, connection: Any, target: str = "default") -> Any:
        """Returns the dialect-aware schema editor for the connection."""
        from ..conf.settings import settings
        db_config = settings.get_database(target)
        engine = db_config.engine if db_config else "sqlite"

        if engine == "sqlite":
            from mikiorm.backends.sqlite.schema import SQLiteSchemaEditor
            return SQLiteSchemaEditor(connection)
        elif engine == "postgresql":
            from mikiorm.backends.postgresql.schema import DatabaseSchemaEditor
            return DatabaseSchemaEditor(connection)
        elif engine == "mysql":
            from mikiorm.backends.mysql.schema import DatabaseSchemaEditor
            return DatabaseSchemaEditor(connection)
        
        from ..backends.base.schema_editor import SchemaEditor
        from ..backends.base.dialect import get_safe_builder

        builder = get_safe_builder(engine)
        return SchemaEditor(connection, builder.dialect)

    def _apply_migration_operations(
        self, operations: list[operations.MigrationOperation], connection: Any
    ) -> None:
        """Apply a list of migration operations to the database."""
        backend_editor = self._get_backend_editor(connection)
        schema_editor = _MigrationSchemaEditor(backend_editor)
        for op in operations:
            schema_editor.execute_operation(op)

    def show_history(self) -> list[str]:
        return MigrationHistory.load_history(self.migrations_path)

    def squash_migrations(self, app_label: str | None = None) -> str | None:
        """Squash multiple migration files into a single one."""
        history = MigrationHistory.load_history(self.migrations_path)
        if not history:
            logger.info("No migrations found to squash.")
            return None

        collected_ops = []
        collecting_schema_editor = CollectingSchemaEditor()

        # Load and execute all migrations against the collecting editor
        for migration_file in history:
            # For now, we'll squash all. If app_label is needed, it needs to be passed to makemigrations
            # and stored in the migration file name or content.
            # For simplicity, let's assume app_label is not used for filtering which migrations to squash,
            # but rather for the *name* of the squashed migration.

            filepath = os.path.join(self.migrations_path, migration_file)
            spec = importlib.util.spec_from_file_location("migration", filepath)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules["migration"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "apply_migration"):
                # Pass the collecting schema editor
                module.apply_migration(None, collecting_schema_editor)
                logger.debug(f"Collected operations from {migration_file}")

        if not collecting_schema_editor.collected_operations:
            logger.info("No operations collected from existing migrations.")
            return None

        # Generate a new squashed migration file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        squashed_filename = f"{timestamp}_squashed_{app_label or 'all'}.py"
        squashed_filepath = os.path.join(self.migrations_path, squashed_filename)
        self._write_migration_file(
            squashed_filepath, collecting_schema_editor.collected_operations
        )

        # Delete old migration files
        to_squash = history
        for migration_file in to_squash:
            filepath = os.path.join(self.migrations_path, migration_file)
            os.remove(filepath)
            logger.info(f"Deleted old migration file: {migration_file}")
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted old migration file: {migration_file}")

        logger.info(f"Created squashed migration: {squashed_filename}")
        return squashed_filename


class _FakeModel:
    """Shim to pass table/field names to backend schema editors."""
    def __init__(self, table_name: str, fields: list[Any] | None = None) -> None:
        from types import SimpleNamespace
        self._meta = SimpleNamespace(
            table_name=table_name,
            fields=fields or [],
            pk=next((f for f in (fields or []) if getattr(f, "primary_key", False)), None)
        )


class _MigrationSchemaEditor:
    """
    Shims migration operations to backend-specific schema editors.
    This replaces the internal _SchemaEditor and delegates to backend implementations.
    """
    def __init__(self, backend_editor: Any) -> None:
        self.backend_editor = backend_editor

    def execute_operation(self, op: MigrationOperation) -> None:
        op_type = op.operation_type
        payload = op.payload
        
        if op_type == "create_table":
            # CreateTable uses the engine's static SQL builder to avoid 
            # fragile Field instance reconstruction from col dicts.
            from .engine import MigrationEngine as ME
            sql, params = ME._build_create_table_sql(op, self.backend_editor)
            self.backend_editor.connection.execute(sql, params)

        elif op_type == "add_field":
            model = _FakeModel(payload["model_name"])
            field = payload["field"]
            self.backend_editor.add_field(model, field)

        elif op_type == "alter_field":
            model = _FakeModel(payload["model_name"])
            field = payload["field"]
            # Note: backend.alter_field might need old_field; using current field as shim.
            self.backend_editor.alter_field(model, field, field) 
            # Use captured old_field for precise alterations
            old_field = payload.get("old_field") or field
            self.backend_editor.alter_field(model, old_field, field) 
_field(model, field, field) 
ckend_editor.drop_index(model, payload["index_name"])

        elif op_type == "delete_table":
            model = _FakeModel(payload["name"])
            self.backend_editor.delete_model(model)

        else:
            logger.warning(f"Operation type {op_type} not handled by migration editor shim")



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

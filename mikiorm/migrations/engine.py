"""Migration runner and management utilities - complete implementation."""

from __future__ import annotations

import argparse
import importlib.util
import importlib
import os
import sys
import logging
import shutil
from datetime import datetime
from typing import Any, Callable

from . import operations
from .operations import MigrationOperation
from .history import MigrationHistory

from .diff import generate_migration_operations
from .editor import CollectingSchemaEditor  # Import the new editor
from .schema import get_introspector
from mikiorm.backends.base.dialect import Dialect
from mikiorm.backends.base.schema_editor import field_to_sql_type, _safe_default_literal

logger = logging.getLogger(__name__)


class MigrationEngine:
    """Engine for generating and applying migrations."""

    def __init__(self, migrations_path: str = "migrations") -> None:
        self.migrations_path = migrations_path
        self._discovered = False

    def _ensure_migrations_table(self, connection: Any) -> None:
        """Ensure the migrations tracking table exists."""
        from ..backends.base.dialect import get_safe_builder
        from ..settings import settings

        db_config = settings.get_database("default")
        builder = get_safe_builder(db_config.engine)

        quoted_table = builder.quote_table("_mikiorm_migrations")

        if db_config.engine == "postgresql":
            sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        else:
            # SQLite / MySQL
            auto_inc = (
                "AUTOINCREMENT" if db_config.engine == "sqlite" else "AUTO_INCREMENT"
            )
            sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} (id INTEGER PRIMARY KEY {auto_inc}, name VARCHAR(255) UNIQUE NOT NULL, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"

        connection.execute(sql, ())

    def get_applied_migrations(self, connection: Any) -> list[str]:
        """Return a list of applied migration names from the database."""
        from ..backends.base.dialect import get_safe_builder
        from ..settings import settings

        db_config = settings.get_database("default")
        builder = get_safe_builder(db_config.engine)

        quoted_table = builder.quote_table("_mikiorm_migrations")
        sql = f"SELECT name FROM {quoted_table} ORDER BY id ASC"
        rows = connection.fetchall(sql, ())
        return [row[0] for row in rows]

    def get_unapplied_migrations(self, connection: Any) -> list[str]:
        """Return a list of migration files that exist on disk but are not in the DB."""
        applied = self.get_applied_migrations(connection)
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
                logger.warning("No registered models found. Use @register or check your imports.")
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
        """Scan configured model paths and import them to trigger registration."""
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
                        rel_path = os.relpath(module_path, abs_path)
                        module_name = rel_path[:-3].replace(os.sep, ".")
                        try:
                            importlib.import_module(module_name)
                        except Exception as e:
                            logger.debug(f"Failed to import discovered module {module_name}: {e}")
        self._discovered = True

    def get_missing_migration_operations(self, connection: Any) -> list[operations.MigrationOperation]:
        """Generate operations for model changes not yet captured in migration files."""
        self.discover_models()
        from ..settings import settings
        db_config = settings.get_database("default")
        return generate_migration_operations(connection, db_config.engine)

    def _save_migration(self, ops: list[operations.MigrationOperation]) -> list[operations.MigrationOperation]:
            os.makedirs(self.migrations_path, exist_ok=True) 
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_auto.py"
            filepath = os.path.join(self.migrations_path, filename)
            self._write_migration_file(filepath, ops)

            logger.info(f"Generated migration: {filename}")
            return ops

    def _apply_operations_internally(
        self, operations: list[operations.MigrationOperation], connection: Any = None
    ) -> None:
        """Internal helper to apply operations without a migration file."""
        backend_editor = self._get_backend_editor(connection)
        schema_editor = _MigrationSchemaEditor(backend_editor)
        self._apply_migration_operations(operations, connection)

    def _write_migration_file(
        self, filepath: str, ops: list[operations.MigrationOperation]
    ) -> None:
        """Write a migration Python file with forward and reverse operations."""
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



        elif op_type == "add_field":
            model = _FakeModel(payload["model_name"])
            field = payload["field"]
            self.backend_editor.add_field(model, field)

        elif op_type == "alter_field":
            model = _FakeModel(payload["model_name"])
            field = payload["field"]
            # Note: backend.alter_field might need old_field; using current field as shim.
            self.backend_editor.alter_field(model, field, field) 

        elif op_type == "remove_field":
            model = _FakeModel(payload["model_name"])
            # Create a dummy field with the right column name for the editor
            field = type('Field', (), {'column': payload['field_name']})
            self.backend_editor.remove_field(model, field)

        elif op_type in ("create_index", "add_index"):
            idx = payload["index"]
            model = _FakeModel(payload["model_name"])
            # Reconstruct dummy field objects for the editor
            fields = [type('Field', (), {'name': c}) for c in idx['columns']]
            self.backend_editor.create_index(model, fields, idx['name'], idx.get('unique', False))

        elif op_type == "drop_index":
            model = _FakeModel(payload["model_name"])
            self.backend_editor.drop_index(model, payload["index_name"])

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

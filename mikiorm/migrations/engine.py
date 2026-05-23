"""Migration runner and management utilities - production-ready implementation."""

from __future__ import annotations

import argparse
import importlib.util
import importlib
import os
import sys
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import operations
from .operations import MigrationOperation
from .history import MigrationHistory
from .diff import generate_migration_operations
from .editor import CollectingSchemaEditor
from .retry import RetryConfig
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
        history = self._build_migration_map().keys()
        return [m for m in history if m not in applied]

    def _resolve_app_label(self, entry: Any) -> str | None:
        """Normalize a model/app entry to the configured app label."""
        if isinstance(entry, str):
            return entry.split(".")[-1]

        from ..models.base import Model

        if isinstance(entry, type) and issubclass(entry, Model):
            app_label = getattr(entry._meta, "app_label", None)
            if app_label:
                return app_label
            qualified = getattr(entry, "__module__", None)
            if qualified and "." in qualified:
                return qualified.split(".")[-1]

        if hasattr(entry, "_meta"):
            app_label = getattr(entry._meta, "app_label", None)
            if app_label:
                return app_label

        if hasattr(entry, "label"):
            return getattr(entry, "label")
        if hasattr(entry, "app_name"):
            return getattr(entry, "app_name")
        return None

    def _get_migration_locations(
        self, app_label: str | None = None
    ) -> list[tuple[str | None, Path]]:
        from ..conf.settings import settings
        from ..models.register import get_default_registry

        locations: list[tuple[str | None, Path]] = []
        for app in settings.installed_apps:
            label = getattr(app, "label", None) or getattr(app, "app_name", None)
            if not label:
                continue
            if app_label and label != app_label:
                continue

            app_path = getattr(app, "path", None) or getattr(app, "base_path", None)
            if app_path:
                candidate = Path(app_path) / "migrations"
                locations.append((label, candidate))
            else:
                locations.append((label, Path(self.migrations_path) / label))

        if not settings.installed_apps:
            registry = get_default_registry()
            for app in registry.get_apps():
                label = getattr(app, "label", None) or getattr(app, "app_name", None)
                if not label:
                    continue
                if app_label and label != app_label:
                    continue

                app_path = getattr(app, "path", None) or getattr(app, "base_path", None)
                if app_path:
                    candidate = Path(app_path) / "migrations"
                    locations.append((label, candidate))
                else:
                    locations.append((label, Path(self.migrations_path) / label))

        if app_label and not any(label == app_label for label, _ in locations):
            locations.append((app_label, Path(self.migrations_path) / app_label))

        locations.append((None, Path(self.migrations_path)))

        unique: list[tuple[str | None, Path]] = []
        seen = set()
        for label, path in locations:
            key = (label, str(path))
            if key in seen:
                continue
            seen.add(key)
            unique.append((label, path))
        return unique

    def _build_migration_map(self, app_label: str | None = None) -> dict[str, Path]:
        locations = self._get_migration_locations(app_label=app_label)
        history = MigrationHistory.load_history(locations)
        mapping: dict[str, Path] = {}
        for prefix, path in locations:
            if not path.exists():
                continue
            for p in sorted(path.iterdir()):
                if p.is_file() and p.suffix == ".py" and p.name != "__init__.py":
                    name = p.name if prefix is None else f"{prefix}/{p.name}"
                    mapping[name] = p
        return mapping

    # ------------------------------------------------------------------
    # Migration generation - schema diff based
    # ------------------------------------------------------------------

    def makemigrations(
        self,
        app_labels: str | type | list[str | type] | None = None,
    ) -> list[operations.MigrationOperation]:
        """
        Generate migration operations grouped by app.
        """
        from ..settings import settings
        from ..models.base import Model
        from ..models.register import get_default_registry

        registry = get_default_registry()
        self.discover_models()

        db_config = settings.get_database("default")
        adapter = db_config.get_adapter()
        connection = adapter.connect(db_config.get_connection_config())

        all_ops = []
        try:
            target_apps: list[str] = []
            requested = app_labels
            if requested is None:
                target_apps = [app.app_name for app in registry.get_apps()]
            else:
                candidates = (
                    requested if isinstance(requested, (list, tuple)) else [requested]
                )
                for entry in candidates:
                    if isinstance(entry, str):
                        target_apps.append(entry.split(".")[-1])
                        continue

                    app_label = self._resolve_app_label(entry)
                    if app_label:
                        target_apps.append(app_label)
                        continue

                    raise TypeError(
                        "makemigrations() accepts app labels, model classes, "
                        f"or instances. Got {type(entry).__name__}."
                    )

            seen_apps = set()
            for app_name in target_apps:
                if app_name in seen_apps:
                    continue
                seen_apps.add(app_name)

                normalized_app_name = app_name.split(".")[-1]
                app_config = registry.get_app(normalized_app_name)
                if not app_config or not app_config.models:
                    continue

                # Generate diff specifically for this app's models
                app_models = list(app_config.models.values())
                ops = generate_migration_operations(
                    connection, db_config.engine, app_models
                )

                if ops:
                    logger.info(f"App '{app_name}': Detected changes.")
                    self._save_migration(app_config, ops)
                    all_ops.extend(ops)

            if not all_ops:
                logger.info("No changes detected in any app.")

            return all_ops
        finally:
            connection.close()

    def discover_models(self) -> None:
        """Discover models using the ``AppRegistry`` / legacy model-paths.

        Route order:
        1. If ``settings.installed_apps`` is non-empty, discover through
           the central :class:`~mikiorm.models.register.AppRegistry` — this
           is the primary path for Django-style projects.
        2. Otherwise fall back to the legacy ``settings.model_paths`` walk.
        """
        if self._discovered:
            return

        from ..conf.settings import settings

        # ── Primary path: AppRegistry / INSTALLED_APPS ──────────────────
        if settings.installed_apps:
            from ..models.register import get_default_registry

            registry = get_default_registry()
            try:
                registry.auto_discover_apps_from_settings()
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(" INSTALLED_APPS discovery raised: %s", exc)
                # Fall through to legacy path below

        # ── Legacy fallback: model_paths walk ───────────────────────────
        elif settings.model_paths:
            for path in settings.model_paths:
                abs_path = os.path.abspath(path)
                if not os.path.exists(abs_path):
                    logger.warning("Model path does not exist: %s", abs_path)
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
                                logger.debug(
                                    "Failed to import discovered module %s: %s",
                                    module_name,
                                    e,
                                )

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

    def _save_migration(
        self, app_config: Any, ops: list[operations.MigrationOperation]
    ) -> None:
        """Save migration to the central migrations folder."""
        migrations_dir = self._get_migration_directory(app_config)

        os.makedirs(migrations_dir, exist_ok=True)
        init_file = migrations_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()

        existing = sorted(
            [
                f.name
                for f in migrations_dir.iterdir()
                if f.is_file()
                and f.name.startswith(tuple("0123456789"))
                and f.suffix == ".py"
            ]
        )
        next_num = 1
        if existing:
            last_name = existing[-1]
            next_num = int(last_name.split("_")[0]) + 1

        prefix = f"{next_num:04}"
        filename = f"{prefix}_initial.py" if next_num == 1 else f"{prefix}_auto.py"
        filepath = migrations_dir / filename

        self._write_migration_file(filepath, ops)
        logger.info(f"Generated migration: {filename}")

    def _get_migration_directory(self, app_config: Any) -> Path:
        """Return the directory where migrations should be written for an app."""
        app_label = getattr(app_config, "label", None) or getattr(
            app_config, "app_name", None
        )
        app_path = getattr(app_config, "path", None) or getattr(
            app_config, "base_path", None
        )

        if app_path:
            candidate = Path(app_path) / "migrations"
            return candidate

        if app_label:
            return Path(self.migrations_path) / app_label

        return Path(self.migrations_path)

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
            items = []
            if op.operation_type == "create_table":
                cols = op.payload.get("columns", [])
                items = list(cols) if isinstance(cols, list) else []
                if "old_field_type" in op.payload:
                    items.append({"field_type": op.payload["old_field_type"]})
            elif op.operation_type in ("add_field", "alter_field"):
                items = [op.payload]
                if "old_field_type" in op.payload:
                    items.append({"field_type": op.payload["old_field_type"]})
            # No field type import needed for indexes or other operations

            for item in items:
                ftype = item.get("field_type", "")
                if ftype:
                    short = ftype.rsplit(".", 1)[-1]
                    field_types.add((short, ftype))

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
            lines.append("    schema_editor.execute_operation(operations.CreateTable(")
            lines.append(f"        name=\"{table_name}\",")
            lines.append("        columns=[")
            for col in cols_data:
                fname = col["name"]
                ftype = col["field_type"]
                short = ftype.rsplit(".", 1)[-1]
                attrs = {k: v for k, v in col.items() if k not in ("name", "field_type", "type")}
                attr_parts = [f"{k}={repr(v)}" for k, v in attrs.items()]
                attr_str = ", ".join(attr_parts)
                lines.append(f"            ({short}({attr_str}), '{fname}'),")
            lines.append("        ],")
            if not forward:
                lines.append(f"        reverse_op=operations.DeleteTable('{table_name}'),")
            lines.append("    )")
            lines.append("    )")
        elif op_type == "add_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            field_kwargs = op.payload.get("field_kwargs", {})
            short = field_type.rsplit(".", 1)[-1]
            mod = field_type.rsplit(".", 1)[0]
            kw_str = ", ".join(f"{k}={v!r}" for k, v in field_kwargs.items())
            if forward:
                lines.append(f"    schema_editor.execute_operation(operations.AddField(model_name='{model}', field={short}({kw_str})))")
            else:
                field_name = op.payload.get("field_name", "")
                lines.append(f"    schema_editor.execute_operation(operations.RemoveField(model_name='{model}', field_name='{field_name}'))")

        elif op_type == "alter_field":
            model = op.payload["model_name"]
            field_type = op.payload["field_type"]
            field_kwargs = op.payload.get("field_kwargs", {})
            short = field_type.rsplit(".", 1)[-1]
            kw_str = ", ".join(f"{k}={v!r}" for k, v in field_kwargs.items())

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
                    lines.append(
                        "    # AlterField reverse requires saved old field definition"
                    )

        elif op_type == "drop_field":
            model = op.payload["model_name"]
            field_name = op.payload["field_name"]
            if forward:
                lines.append(f"    schema_editor.execute_operation(operations.RemoveField(model_name='{model}', field_name='{field_name}'))")
            if not forward:
                # Reverse: add field back - would need saved field definition
                lines.append("    # DropField reverse requires saved field definition")

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
                lines.append("    # DropIndex reverse requires saved index definition")

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
                history_map = self._build_migration_map()
                pending = [m for m in history_map if m not in applied]

                if not pending:
                    logger.info("No migrations to apply.")
                    return

                # SQLite Safety: backup file before destructive changes
                if is_sqlite:
                    has_destructive = any(
                        self._is_destructive(history_map[m]) for m in pending
                    )
                    if has_destructive:
                        db_path = db_config.get_connection_config().get("name")
                        if db_path and db_path != ":memory:":
                            self._create_sqlite_backup(db_path)

                builder = get_safe_builder(db_config.engine)
                quoted_table = builder.quote_table("_mikiorm_migrations")
                ph = builder.get_placeholder(1)

                # Apply each migration atomically
                for migration_file in pending:
                    filepath = history_map[migration_file]
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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS _mikiorm_migration_lock (id INTEGER PRIMARY KEY, locked_at TIMESTAMP)",
                (),
            )
            if db_config.engine == "mysql":
                sql = "INSERT IGNORE INTO _mikiorm_migration_lock (id, locked_at) VALUES (1, CURRENT_TIMESTAMP)"
            else:
                sql = "INSERT OR IGNORE INTO _mikiorm_migration_lock (id, locked_at) VALUES (1, CURRENT_TIMESTAMP)"

            cursor = connection.execute(sql, ())
            if cursor.rowcount == 1:
                return 1
            return None
        except Exception:
            return None

    def _release_lock(self, connection: Any, lock_id: int, target: str = "default") -> None:
        """Release migration lock."""
        from ..conf.settings import settings
        from ..backends.base.dialect import get_safe_builder

        db_config = settings.get_database(target)
        builder = get_safe_builder(db_config.engine)
        ph = builder.get_placeholder(1)

        if db_config.engine == "postgresql" and lock_id == 1337:
            connection.execute("SELECT pg_advisory_unlock(1337)", ())
            return

        try:
            connection.execute(
                f"DELETE FROM _mikiorm_migration_lock WHERE id = {ph}", (lock_id,)
            )
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

                history_map = self._build_migration_map()
                applied_set = set(applied)
                applied_history = [name for name in history_map if name in applied_set]
                to_rollback = (
                    applied_history[-steps:]
                    if steps <= len(applied_history)
                    else applied_history
                )

                # Rollback each migration in reverse order, each in its own transaction
                for migration_file in reversed(to_rollback):
                    filepath = history_map.get(migration_file)
                    if filepath is None:
                        logger.warning(
                            f"Migration file missing for rollback: {migration_file}"
                        )
                        continue
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
        return list(self._build_migration_map().keys())

    def migrate_direct(self, filepath: str, connection: Any, target: str = "default") -> None:
        """Apply a migration file directly (backward compatibility)."""
        self._apply_migration_direct(filepath, connection, target)

    def _get_squash_directory(self, app_label: str | None = None) -> Path:
        if app_label:
            locations = self._get_migration_locations(app_label=app_label)
            for label, path in locations:
                if label == app_label:
                    return path
            return Path(self.migrations_path) / app_label
        return Path(self.migrations_path)

    def squash_migrations(self, app_label: str | None = None) -> str | None:
        """Squash multiple migration files into a single one."""
        history_map = self._build_migration_map(app_label=app_label)
        if not history_map:
            logger.info("No migrations found to squash.")
            return None

        collected_ops = []
        collecting_schema_editor = CollectingSchemaEditor()

        for migration_name, filepath in history_map.items():
            spec = importlib.util.spec_from_file_location("migration", str(filepath))
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules["migration"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "apply_migration"):
                module.apply_migration(None, collecting_schema_editor)
                logger.debug("Collected operations from %s", migration_name)

        if not collecting_schema_editor.collected_operations:
            logger.info("No operations collected from existing migrations.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        squashed_filename = f"{timestamp}_squashed_{app_label or 'all'}.py"
        squash_dir = self._get_squash_directory(app_label)
        os.makedirs(squash_dir, exist_ok=True)
        squashed_filepath = squash_dir / squashed_filename
        self._write_migration_file(
            squashed_filepath, collecting_schema_editor.collected_operations
        )

        from ..conf.settings import settings
        from ..backends.base.dialect import get_safe_builder

        db_config = settings.get_database("default")
        adapter = db_config.get_adapter()
        connection = adapter.connect(db_config.get_connection_config())
        try:
            self._ensure_migrations_table(connection)
            applied = set(self.get_applied_migrations(connection))
            if any(name in applied for name in history_map):
                builder = get_safe_builder(db_config.engine)
                quoted_table = builder.quote_table("_mikiorm_migrations")
                ph = builder.get_placeholder(1)
                if db_config.engine == "postgresql":
                    sql = (
                        f"INSERT INTO {quoted_table} (name, status) VALUES ({ph}, 'applied') "
                        "ON CONFLICT (name) DO NOTHING"
                    )
                elif db_config.engine == "mysql":
                    sql = f"INSERT IGNORE INTO {quoted_table} (name, status) VALUES ({ph}, 'applied')"
                else:
                    sql = f"INSERT OR IGNORE INTO {quoted_table} (name, status) VALUES ({ph}, 'applied')"
                connection.execute(sql, (squashed_filename,))
        finally:
            connection.close()

        for migration_name, filepath in history_map.items():
            try:
                if filepath.exists():
                    os.remove(filepath)
                    logger.info("Deleted old migration file: %s", migration_name)
            except Exception as exc:
                logger.warning(
                    "Failed to delete squashed migration file %s: %s",
                    migration_name,
                    exc,
                )

        logger.info("Created squashed migration: %s", squashed_filename)
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

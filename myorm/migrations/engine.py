"""Migration runner and management utilities.

Mirrors django.db.migrations for generating and applying schema changes.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime
from typing import Any

from . import operations
from .history import MigrationHistory


class MigrationEngine:
    """Engine for generating and applying migrations.

    Inspects registered models, generates migration operations, and
    can write them to migration files or apply them directly.
    """

    def __init__(self, migrations_path: str = "migrations") -> None:
        self.migrations_path = migrations_path

    # ------------------------------------------------------------------
    # Field introspection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_field_attrs(field: Any) -> dict[str, Any]:
        from ..models.fields import (
            AutoField, BooleanField, CharField, DateField, DateTimeField,
            DecimalField, DurationField, EmailField, FloatField,
            GenericIPAddressField, IntegerField, JSONField, SlugField,
            TextField, TimeField, URLField, UUIDField,
        )

        kwargs: dict[str, Any] = {}

        if field.primary_key:
            kwargs["primary_key"] = True
        if field.null:
            kwargs["null"] = True
        if field.blank and not field.primary_key:
            kwargs["blank"] = True
        if field.unique:
            kwargs["unique"] = True
        if field.db_index:
            kwargs["db_index"] = True
        if field.help_text:
            kwargs["help_text"] = field.help_text
        if field.default is not None:
            kwargs["default"] = field.default
        if field.choices:
            kwargs["choices"] = field.choices
        if field.db_column:
            kwargs["db_column"] = field.db_column
        if field.verbose_name is not None:
            kwargs["verbose_name"] = field.verbose_name
        if field.db_default is not None:
            kwargs["db_default"] = field.db_default
        if getattr(field, "auto_increment", False):
            kwargs["auto_increment"] = True

        if isinstance(field, CharField):
            if field.max_length is not None:
                kwargs["max_length"] = field.max_length
        if isinstance(field, (DateTimeField, DateField, TimeField)):
            if field.auto_now:
                kwargs["auto_now"] = True
            if field.auto_now_add:
                kwargs["auto_now_add"] = True
        if isinstance(field, DecimalField):
            kwargs["max_digits"] = field.max_digits
            kwargs["decimal_places"] = field.decimal_places
        if isinstance(field, EmailField) and field.max_length != 254:
            kwargs["max_length"] = field.max_length
        if isinstance(field, URLField) and field.max_length != 200:
            kwargs["max_length"] = field.max_length
        if isinstance(field, SlugField):
            if field.max_length != 50:
                kwargs["max_length"] = field.max_length
            if field.allow_unicode:
                kwargs["allow_unicode"] = True

        return kwargs

    @staticmethod
    def _get_internal_type(field: Any) -> str:
        return f"{field.__class__.__module__}.{field.__class__.__qualname__}"

    @staticmethod
    def _build_column_def(fname: str, field: Any) -> dict[str, Any]:
        attrs = MigrationEngine._collect_field_attrs(field)
        return {
            "name": fname,
            "field_type": MigrationEngine._get_internal_type(field),
            **attrs,
        }

    # ------------------------------------------------------------------
    # Migration generation
    # ------------------------------------------------------------------

    def _build_operations(self, model_classes: list[type[Any]]) -> list[operations.MigrationOperation]:
        ops: list[operations.MigrationOperation] = []
        for model_cls in model_classes:
            table_name = getattr(model_cls._meta, "table_name", None)
            if table_name is None:
                table_name = model_cls.__name__.lower() + "s"

            columns: list[dict[str, Any]] = []
            for fname, field_obj in model_cls._meta.fields.items():
                columns.append(self._build_column_def(fname, field_obj))
            ops.append(operations.CreateTable(name=table_name, columns=columns))
        return ops

    def makemigrations(
        self,
        app_label: str | list[type[Any]] | None = None,
    ) -> list[operations.MigrationOperation]:
        from ..models.registry import ModelRegistry

        if isinstance(app_label, list):
            models_to_migrate = app_label
        elif isinstance(app_label, str):
            models_to_migrate = []
            for model in ModelRegistry.all_models():
                mod = model.__module__
                if app_label in mod or model.__name__ == app_label:
                    models_to_migrate.append(model)
        else:
            models_to_migrate = list(ModelRegistry.all_models())

        if not models_to_migrate:
            return []

        ops = self._build_operations(models_to_migrate)

        os.makedirs(self.migrations_path, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_auto.py"
        filepath = os.path.join(self.migrations_path, filename)
        self._write_migration_file(filepath, ops)

        return ops

    def _write_migration_file(
        self, filepath: str, ops: list[operations.MigrationOperation]
    ) -> None:
        field_types: set[str] = set()
        for op in ops:
            if op.operation_type == "create_table":
                for col in op.payload.get("columns", []):
                    ftype = col.get("field_type", "")
                    short = ftype.rsplit(".", 1)[-1]
                    field_types.add((short, ftype))

        lines: list[str] = []
        lines.append("# Auto-generated migration")
        lines.append(f"# Generated: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("from myorm.migrations import operations")
        for short, full in sorted(field_types):
            lines.append(f"from {full.rsplit('.', 1)[0]} import {short}")
        lines.append("")
        lines.append("")
        lines.append("def apply_migration(apps, schema_editor):")

        for op in ops:
            if op.operation_type == "create_table":
                cols_data = op.payload.get("columns", [])
                table_name = op.payload.get("name", "unknown")
                lines.append(f'    operations.CreateTable(')
                lines.append(f'        name="{table_name}",')
                lines.append(f'        columns=[')
                for col in cols_data:
                    fname = col.pop("name")
                    ftype = col.pop("field_type")
                    short = ftype.rsplit(".", 1)[-1]
                    attr_parts = [f"{k}={v!r}" for k, v in col.items()]
                    attr_str = ", ".join(attr_parts)
                    lines.append(f"            ({short}({attr_str}), '{fname}'),")
                lines.append(f'        ],')
                lines.append(f'    )')
                lines.append("")
                col["name"] = fname
                col["field_type"] = ftype

        lines.append("")
        lines.append("")
        lines.append("class Migration:")
        lines.append("    dependencies = []")
        lines.append("")
        lines.append("    operations = [apply_migration]")

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

    # ------------------------------------------------------------------
    # Migration application
    # ------------------------------------------------------------------

    @staticmethod
    def _sql_type_for_field(field_obj: Any) -> str:
        """Return the SQL column type string for a field."""
        from ..models.fields import (
            IntegerField, BigIntegerField, SmallIntegerField,
            PositiveIntegerField, PositiveSmallIntegerField,
            AutoField, BigAutoField, SmallAutoField,
            CharField, TextField, BooleanField,
            DecimalField, FloatField, DurationField,
            DateTimeField, DateField, TimeField,
            UUIDField, JSONField, BinaryField,
        )

        if isinstance(field_obj, (IntegerField, AutoField, SmallAutoField,
                                   PositiveIntegerField, PositiveSmallIntegerField)):
            return "INTEGER"
        if isinstance(field_obj, BigIntegerField):
            return "BIGINT"
        if isinstance(field_obj, BigAutoField):
            return "BIGINT"
        if isinstance(field_obj, CharField):
            ml = field_obj.max_length or 255
            return f"VARCHAR({ml})"
        if isinstance(field_obj, TextField):
            return "TEXT"
        if isinstance(field_obj, BooleanField):
            return "BOOLEAN"
        if isinstance(field_obj, DecimalField):
            return f"DECIMAL({field_obj.max_digits}, {field_obj.decimal_places})"
        if isinstance(field_obj, FloatField):
            return "FLOAT"
        if isinstance(field_obj, DurationField):
            return "BIGINT"
        if isinstance(field_obj, DateTimeField):
            return "DATETIME"
        if isinstance(field_obj, DateField):
            return "DATE"
        if isinstance(field_obj, TimeField):
            return "TIME"
        if isinstance(field_obj, UUIDField):
            return "VARCHAR(36)"
        if isinstance(field_obj, JSONField):
            return "TEXT"
        if isinstance(field_obj, BinaryField):
            return "BLOB"

        return "TEXT"  # fallback

    def _build_create_table_sql(self, operation: operations.CreateTable) -> tuple[str, list[Any]]:
        """Build a CREATE TABLE SQL statement from a CreateTable operation."""
        table_name = operation.payload["name"]
        columns = operation.payload["columns"]

        col_defs: list[str] = []
        params: list[Any] = []

        for col in columns:
            cname = col["name"]
            # Reconstruct field from saved kwargs
            ftype_path = col["field_type"]
            kwargs = {k: v for k, v in col.items() if k not in ("name", "field_type")}

            # Determine SQL type
            # Import the actual field class to use its SQL type mapping
            parts = ftype_path.rsplit(".", 1)
            if len(parts) == 2:
                mod_path, class_name = parts
                import importlib
                try:
                    mod = importlib.import_module(mod_path)
                    field_cls = getattr(mod, class_name, None)
                except (ImportError, AttributeError):
                    field_cls = None
            else:
                field_cls = None

            if field_cls:
                # Instantiate field to get SQL type
                try:
                    inst = field_cls(**kwargs)
                    sql_type = self._sql_type_for_field(inst)
                except Exception:
                    sql_type = "TEXT"
            else:
                sql_type = "TEXT"

            constraints = []
            if kwargs.get("primary_key"):
                constraints.append("PRIMARY KEY")
                if kwargs.get("auto_increment", False) or sql_type == "INTEGER":
                    constraints.append("AUTOINCREMENT")
            if kwargs.get("null"):
                constraints.append("NULL")
            else:
                constraints.append("NOT NULL")
            if kwargs.get("unique"):
                constraints.append("UNIQUE")

            param_default = None
            if kwargs.get("default") is not None:
                param_default = kwargs["default"]

            col_def = f"    {cname} {sql_type} {' '.join(constraints)}"
            if param_default is not None:
                col_def += " DEFAULT ?"
                params.append(param_default)

            col_defs.append(col_def)

        sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n{',\n'.join(col_defs)}\n)"
        return sql, params

    def migrate(self, connection: Any | None = None, target: str | None = None) -> None:
        if connection is None:
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database(target)
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())
        history = MigrationHistory.load_history(self.migrations_path)
        for migration_file in history:
            filepath = os.path.join(self.migrations_path, migration_file)
            self._apply_migration(filepath, connection)

    def _apply_migration(self, filepath: str, connection: Any) -> None:
        spec = importlib.util.spec_from_file_location("migration", filepath)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules["migration"] = module
        spec.loader.exec_module(module)

        if hasattr(module, "apply_migration"):
            module.apply_migration(None, connection)

    def migrate_direct(self, operations: list[operations.MigrationOperation], connection: Any = None) -> None:
        """Directly apply operations to a connection without writing migration files.

        This bypasses the file-based migration system for simpler use cases.
        """
        if connection is None:
            from ..settings import settings as myorm_settings
            db_config = myorm_settings.get_database("default")
            adapter = db_config.get_adapter()
            connection = adapter.connect(db_config.get_connection_config())

        for op in operations:
            if op.operation_type == "create_table":
                sql, params = self._build_create_table_sql(op)
                connection.execute(sql, params)

        connection.commit()

    def rollback(self, connection: Any, steps: int = 1) -> None:
        history = MigrationHistory.load_history(self.migrations_path)
        for _ in range(min(steps, len(history))):
            migration_file = history.pop()
            filepath = os.path.join(self.migrations_path, migration_file)
            if os.path.exists(filepath):
                os.remove(filepath)

    def show_history(self) -> list[str]:
        return MigrationHistory.load_history(self.migrations_path)


def main() -> None:
    parser = argparse.ArgumentParser(prog="miki-orm-migrate")
    parser.add_argument("command", choices=["makemigrations", "migrate", "rollback", "history"])
    parser.add_argument("target", nargs="?", help="Migration target or rollback steps")
    args = parser.parse_args()

    engine = MigrationEngine()
    if args.command == "makemigrations":
        print("Generating migration stubs...")
        ops = engine.makemigrations(args.target)
        for op in ops:
            print(f"  Created migration: {op.payload.get('name')}")
    elif args.command == "migrate":
        print("Applying migrations...")
        engine.migrate(None, target=args.target)
        print("  Done.")
    elif args.command == "rollback":
        steps = int(args.target or "1")
        print(f"Rolling back {steps} migration(s)...")
        engine.rollback(None, steps=steps)
    elif args.command == "history":
        print("Migration history:")
        for name in engine.show_history():
            print(f"  {name}")


if __name__ == "__main__":
    main()
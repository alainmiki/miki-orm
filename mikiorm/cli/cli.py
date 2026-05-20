#!/usr/bin/env python3
"""
miki-orm CLI Tool.

Configuration is sourced exclusively from a Python ``settings.py`` module
passed via ``--settings`` or the ``MIKI_ORM_SETTINGS_MODULE`` environment
variable.  No YAML / TOML / pyproject.toml config files are supported.

New-project flow::

    python -m mikiorm startproject conf .          # ./conf/settings.py
    python -m mikiorm startapp  users apps/         # ./apps/users/
    python -m mikiorm --settings=conf.settings makemigrations

Every migrate- or check- command honours ``--settings`` as before.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("miki-orm.cli")


# ---------------------------------------------------------------------------
# Boilerplate generators (startapp / startproject)
# ---------------------------------------------------------------------------

#: Written to ``<app>/app.py`` by the ``startapp`` command.
_APP_PY = '''\
# app.py — App configuration for {app_name}
from mikiorm.conf.settings import AppConfig


class AppConfig(AppConfig):
    """Application configuration for the '{app_name}' app."""

    name = "{app_name}"
    label = "{app_name}"


__all__ = ["AppConfig"]
'''

#: Written to ``<app>/models.py`` by the ``startapp`` command.
_MODELS_PY = """\
# models.py — Database models for the '{app_name}' app
from mikiorm.models import Model, CharField, IntegerField, DateTimeField

# ─── Register your models below ────────────────────────────────────────────
#
# To create a model:
#
#     from mikiorm.models import register
#
#     @register(app="{app_name}")
#     class MyModel(Model):
#         name = CharField(max_length=100)
#
#         class Meta:
#             table_name = "{app_name}_mymodel"
#             verbose_name = "My Model"
"""


def _generate_settings_scaffold(
    project_name: str = "myproject",
    *,
    as_package: bool = False,
) -> str:
    """Return the content string for a new ``settings.py`` file.

    Args:
        project_name: Used for the header comment.
        as_package:   When *True* the settings file is inside a package
                      directory so ``BASE_DIR`` is one level higher.

    Returns:
        Ready-to-write settings.py source.
    """
    base_dir_line = "BASE_DIR = Path(__file__).parent.parent  # project root"

    return f'''\
"""
{project_name} settings — configure your miki-orm application here.
"""

from pathlib import Path

from mikiorm import configure

# ─── Filesystem ────────────────────────────────────────────────────────────
BASE_DIR = {base_dir_line}


# ─── Database (SQLite example) ─────────────────────────────────────────────
DATABASES = {{
    # "default": {{
    #     "ENGINE": "sqlite",
    #     "NAME":   BASE_DIR / "db.sqlite3",
    # }},
}}
DEFAULT_DATABASE = "default"


# ─── Installed apps ────────────────────────────────────────────────────────
INSTALLED_APPS: list[str] = [
    # "users",
    # "products",
]


# ─── Migrations & model discovery ─────────────────────────────────────────
MIGRATION_PATH = "migrations"
MODEL_PATHS: list[str] = []


# ─── Runtime ───────────────────────────────────────────────────────────────
SECRET_KEY  = "change-me"
DEBUG       = False
ALLOWED_HOSTS: list[str] = []
USE_TZ      = True


def configure_project() -> None:
    """Configure the ORM from this settings module.

    Call this once at application startup so that database connections,
    app registration, and model discovery are all wired up.
    """
    configure(
        databases=DATABASES,
        default_database=DEFAULT_DATABASE,
        migration_path=MIGRATION_PATH,
        model_paths=MODEL_PATHS,
        installed_apps=INSTALLED_APPS,
    )
'''


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def load_settings(settings_module: str) -> None:
    """Import the named settings module and configure miki-orm from it."""
    try:
        mod = importlib.import_module(settings_module)
        logger.info("Using settings from: %s", settings_module)
        from mikiorm.conf.settings import configure

        if hasattr(mod, "configure_project") and callable(mod.configure_project):
            mod.configure_project()
        else:
            configure(
                databases=getattr(mod, "DATABASES", None),
                default_database=getattr(mod, "DEFAULT_DATABASE", "default"),
                migration_path=getattr(mod, "MIGRATION_PATH", "migrations"),
                model_paths=getattr(mod, "MODEL_PATHS", None),
                installed_apps=getattr(mod, "INSTALLED_APPS", []),
                logging_config=getattr(mod, "LOGGING", None),
            )
    except ImportError as exc:
        logger.error("Could not find settings module '%s'.", settings_module)
        logger.error("Details: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Error loading settings from '%s': %s", settings_module, exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Command: startproject
# ---------------------------------------------------------------------------


def _handle_startproject(args: Any) -> None:
    """Create a new miki-orm project scaffold containing ``settings.py``."""
    project_name = args.project_name
    target = Path(args.target_dir).resolve()
    project_dir = target / project_name

    if project_dir.exists() and any(project_dir.iterdir()):
        print(
            f"Error: directory '{project_dir}' already exists and is not empty.",
            file=sys.stderr,
        )
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)
    settings_file = project_dir / "settings.py"

    settings_file.write_text(
        _generate_settings_scaffold(project_name=project_name),
        encoding="utf-8",
    )

    print(f"Created project:\n  {settings_file.relative_to(Path.cwd())}")
    print("\nNext steps:")
    print("  1. Edit the settings.py to configure DATABASES and INSTALLED_APPS")
    print("  2. Call configure_project() at startup, or:")
    print("       python -m mikiorm --settings=conf.settings makemigrations")


# ---------------------------------------------------------------------------
# Command: startapp
# ---------------------------------------------------------------------------


def _handle_startapp(args: Any) -> None:
    """Scaffold a new app with ``app.py`` and ``models.py`` boilerplate files.

    Layouts:
    - ``mikiorm startapp users``              → ``./users/app.py`` + ``models.py``
    - ``mikiorm startapp users apps/``        → ``./apps/users/app.py`` + ``models.py``
    - ``mikiorm startapp users apps/products`` → ``./apps/products/app.py`` + ``models.py``
    """
    app_name = args.app_name
    cwd = Path.cwd().resolve()

    if args.target_dir:
        app_dir = Path(args.target_dir).resolve() / app_name
    else:
        app_dir = cwd / app_name

    app_dir.mkdir(parents=True, exist_ok=True)

    (app_dir / "app.py").write_text(_APP_PY.format(app_name=app_name), encoding="utf-8")
    (app_dir / "models.py").write_text(
        _MODELS_PY.format(app_name=app_name), encoding="utf-8"
    )

    try:
        display = str(app_dir.relative_to(cwd))
    except ValueError:
        display = str(app_dir)

    print(f"Created app: {app_name!r} at: {display}")
    print("  app.py")
    print("  models.py")


# ---------------------------------------------------------------------------
# Command: main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``mikiorm`` management CLI."""
    parser = argparse.ArgumentParser(
        prog="miki-orm",
        description="miki-orm management CLI (settings.py only — no YAML/TOML config).",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help=(
            "Python path to a settings module (e.g. 'conf.settings'). "
            "Falls back to the MIKI_ORM_SETTINGS_MODULE environment variable."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) output.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, title="Commands")

    # ── Core migration commands ──────────────────────────────────────────

    subparsers.add_parser(
        "makemigrations",
        help="Scan models and generate new migration files.",
    ).add_argument(
        "app_labels",
        nargs="*",
        help="Restrict to specific app labels (optional).",
    )

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply pending migrations to the configured database.",
    )
    migrate_parser.add_argument(
        "database",
        nargs="?",
        default="default",
        help="Database alias to migrate (default: 'default').",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL without executing it.",
    )

    subparsers.add_parser(
        "rollback",
        help="Roll back applied migrations.",
    ).add_argument(
        "steps",
        nargs="?",
        type=int,
        default=1,
        help="Number of migrations to roll back (default: 1).",
    )

    subparsers.add_parser("history", help="List all discovered migration files.")
    subparsers.add_parser("status", help="Show applied / pending migration status.")

    subparsers.add_parser(
        "check",
        help="Validate model definitions, database settings, and migration state.",
    )

    subparsers.add_parser(
        "dbcheck",
        help="Verify the database connection and list existing tables.",
    )

    inspect_parser = subparsers.add_parser(
        "inspectdb",
        help="Introspect the database and emit miki-orm model definitions.",
    )
    inspect_parser.add_argument(
        "database",
        nargs="?",
        default="default",
        help="Database alias to inspect (default: 'default').",
    )

    squash_parser = subparsers.add_parser(
        "squashmigrations",
        help="Compress multiple migration files into a single one.",
    )
    squash_parser.add_argument(
        "app_label",
        nargs="?",
        help="App label to restrict squashing (optional).",
    )
    squash_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do not prompt for confirmation.",
    )

    subparsers.add_parser(
        "sqlflush",
        help="Print DELETE statements for every table.",
    ).add_argument(
        "--no-input",
        action="store_true",
        help="Do not prompt for confirmation.",
    )

    show_diff_parser = subparsers.add_parser(
        "show_sqldiff",
        help="Preview the SQL that pending migrations would execute.",
    )
    show_diff_parser.add_argument(
        "database",
        nargs="?",
        default="default",
        help="Database alias to preview migrations for (default: 'default').",
    )

    subparsers.add_parser(
        "shell",
        help="Open an interactive Python shell with all models pre-imported.",
    )

    # ── Scaffold commands ─────────────────────────────────────────────────

    subparsers.add_parser(
        "startproject",
        help="Create a new miki-orm project with a settings.py scaffold.",
    ).add_argument(
        "project_name",
        help="Name for the project folder / settings module (e.g. 'conf').",
    )

    startapp_parser = subparsers.add_parser(
        "startapp",
        help="Scaffold a new app with boilerplate app.py and models.py.",
    )
    startapp_parser.add_argument(
        "app_name",
        help="Name for the app (e.g. 'users').",
    )
    startapp_parser.add_argument(
        "target_dir",
        nargs="?",
        default=None,
        help=(
            "Directory to create the app in. "
            "Omit to create in the current working directory; "
            "provide a path to nest under it."
        ),
    )

    # ── Parse ─────────────────────────────────────────────────────────────

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # ── Scaffold commands run without needing a settings module ────────────
    if args.command == "startproject":
        _handle_startproject(args)
        return
    if args.command == "startapp":
        _handle_startapp(args)
        return

    # ── All other commands require a settings module ──────────────────────
    settings_module = args.settings or os.environ.get("MIKI_ORM_SETTINGS_MODULE")
    if settings_module:
        load_settings(settings_module)
    elif os.path.exists("settings.py"):
        load_settings("settings")
    else:
        logger.error(
            "No settings module found. Pass --settings=<module> or place a "
            "settings.py in the current directory."
        )
        sys.exit(1)

    # ── Dispatch ───────────────────────────────────────────────────────────
    try:
        from mikiorm.migrations.engine import MigrationEngine
        from mikiorm.models.register import ModelRegistry
        from mikiorm.conf.settings import connection_manager, settings
        from mikiorm.backends.base.dialect import get_safe_builder

        if args.command == "makemigrations":
            logger.info("Scanning for model changes...")
            ops = MigrationEngine().makemigrations(
                args.app_labels if args.app_labels else None
            )
            logger.info(
                (
                    "Success: Generated %d migration operation(s)."
                    if ops
                    else "No changes detected."
                ),
                len(ops) if ops else 0,
            )

        elif args.command == "migrate":
            engine = MigrationEngine()
            if args.dry_run:
                logger.info("Dry run — SQL for database '%s':", args.database)
                history = engine.show_history()
                if not history:
                    logger.info("No migrations found.")
                    return
                print("\n-- miki-orm SQL Migration Dry Run")
                print(f"-- Target Database: {args.database}")

                class _SQLCapturer:
                    def execute(self, sql, params=()):
                        s = sql
                        for p in params or ():
                            s = s.replace("?", f"'{p}'", 1)
                            s = s.replace("%s", f"'{p}'", 1)
                        print(f"{s.strip()};")
                        return self

                    def fetchall(self, *a, **kw):
                        return []

                    def fetchone(self, *a, **kw):
                        return None

                    def commit(self):
                        pass

                    def rollback(self):
                        pass

                cap = _SQLCapturer()
                for fname in history:
                    path = os.path.join(engine.migrations_path, fname)
                    print(f"\n-- --- Migration: {fname} ---")
                    engine._apply_migration_direct(path, cap)
                print("\n-- End of Dry Run")
            else:
                logger.info("Applying migrations to database '%s'...", args.database)
                engine.migrate(target=args.database)
                logger.info("Success: Database is up to date.")

        elif args.command == "check":
            logger.info("Performing system checks...")
            engine = MigrationEngine()
            engine.discover_models()

            models = ModelRegistry.all_models()
            if not models:
                logger.warning(
                    "  [WARN] No models found. Ensure modules calling @register are imported."
                )
            else:
                logger.info("  [OK] %d model(s) registered.", len(models))

            if connection_manager.validate_connection():
                logger.info("  [OK] Database settings and connection validated.")
                with connection_manager.get_connection() as conn:
                    unapplied = engine.get_unapplied_migrations(conn)
                    if unapplied:
                        logger.error(
                            "  [FAIL] %d migration(s) are pending.", len(unapplied)
                        )
                        for m in unapplied:
                            logger.error("         - %s", m)
                    else:
                        logger.info("  [OK] Database is up to date with migration files.")

                    missing_ops = engine.get_missing_migration_operations(conn)
                    if missing_ops:
                        logger.error(
                            "  [FAIL] Changes in models not yet in migration files."
                        )
                    else:
                        logger.info("  [OK] All models have corresponding migration files.")

                    if unapplied or missing_ops:
                        sys.exit(1)
            else:
                logger.error("  [FAIL] Database connection check failed.")
                sys.exit(1)

            logger.info("System check identified no issues.")

        elif args.command == "dbcheck":
            logger.info("Performing database health check...")
            if connection_manager.validate_connection():
                logger.info("  [OK] Database connection is alive.")
                from mikiorm.migrations.schema import get_introspector
                db_config = settings.get_database("default")
                with connection_manager.get_connection() as conn:
                    introspector = get_introspector(conn, db_config.engine)
                    tables = introspector.get_tables()
                logger.info("  [OK] Found %d table(s) in schema.", len(tables))
            else:
                logger.error("  [FAIL] Database connection could not be established.")
                sys.exit(1)

        elif args.command == "show_sqldiff":
            logger.info("Generating SQL preview...")
            engine = MigrationEngine()
            history_map = engine._build_migration_map()
            if not history_map:
                logger.info("No migrations found in the migrations directory.")
                return
            db_config = settings.get_database(args.database)
            builder = get_safe_builder(db_config.engine)
            print("\n-- miki-orm SQL Migration Preview")
            for fname, path in history_map.items():
                print(f"\n-- --- Migration: {fname} ---")

                class _Cap:
                    def execute(self, sql, params=()):
                        s = sql
                        for p in params or ():
                            s = s.replace(builder.get_placeholder(), f"'{p}'", 1)
                        print(f"{s.strip()};")
                        return self

                    def fetchall(self, *a, **kw):
                        return []

                    def fetchone(self, *a, **kw):
                        return None

                    def commit(self):
                        pass

                    def rollback(self):
                        pass

                engine._apply_migration_direct(path, _Cap())
            print("\n-- End of Preview")

        elif args.command == "shell":
            import code as _code

            logger.info("Opening interactive shell...")
            engine = MigrationEngine()
            engine.discover_models()
            models = ModelRegistry.all_models()
            namespace: dict[str, Any] = {"mikiorm": __import__("mikiorm")}
            for model_cls in models:
                namespace[model_cls.__name__] = model_cls
            banner = (
                f"miki-orm shell (Python {sys.version})\n"
                f"Models pre-imported: "
                f"{', '.join(m.__name__ for m in models) if models else 'None'}\n"
                f"The 'mikiorm' package is also available."
            )
            _code.interact(banner=banner, local=namespace)

        elif args.command == "status":
            engine = MigrationEngine()
            history = engine.show_history()
            with connection_manager.get_connection() as conn:
                applied = {
                    r[0]
                    for r in conn.fetchall("SELECT name FROM _mikiorm_migrations", ())
                }
            print()
            print(f"{'Status':<12} | {'Migration Name'}")
            print("-" * 50)
            for mig in history:
                tag = "[X] Applied" if mig in applied else "[ ] Pending"
                print(f"{tag:<12} | {mig}")

        elif args.command == "rollback":
            engine = MigrationEngine()
            engine.rollback(None, steps=args.steps)
            logger.info("Success: Rolled back %d migration(s).", args.steps)

        elif args.command == "history":
            engine = MigrationEngine()
            for item in engine.show_history():
                print(f"  [X] {item}")

        elif args.command == "inspectdb":
            from mikiorm.migrations.schema import get_introspector

            db_config = settings.get_database(args.database)
            with connection_manager.get_connection(args.database) as engine:
                introspector = get_introspector(engine, db_config.engine)
                tables = introspector.get_tables()

            print("# Auto-generated miki-orm model module.")
            print("# Verify generated models before using.")
            print("from mikiorm import models\n")

            for table_name in tables:
                if table_name.startswith("_migration"):
                    continue
                class_name = "".join(w.capitalize() for w in table_name.split("_"))
                if class_name.endswith("s") and len(class_name) > 1:
                    class_name = class_name[:-1]

                print(f"class {class_name}(models.Model):")
                cols = introspector.get_columns(table_name)
                for col in cols:
                    field_name = col["name"]
                    db_type = col["type"].upper()
                    is_pk = col.get("primary_key", False)
                    is_null = col.get("null", True)
                    is_unique = col.get("unique", False)

                    field_type = "TextField"
                    field_params: list[str] = []

                    if "INT" in db_type:
                        field_type = "AutoField" if is_pk else "IntegerField"
                    elif "VARCHAR" in db_type or "CHAR" in db_type:
                        field_type = "CharField"
                        m = __import__("re").search(r"\((\d+)\)", db_type)
                        field_params.append(
                            f"max_length={m.group(1)}" if m else "max_length=255"
                        )
                    elif "TEXT" in db_type:
                        field_type = "TextField"
                    elif "BOOL" in db_type:
                        field_type = "BooleanField"
                    elif "DECIMAL" in db_type or "NUMERIC" in db_type:
                        field_type = "DecimalField"
                        m = __import__("re").search(r"\((\d+),\s*(\d+)\)", db_type)
                        if m:
                            field_params += [
                                f"max_digits={m.group(1)}",
                                f"decimal_places={m.group(2)}",
                            ]
                        else:
                            field_params += ["max_digits=10", "decimal_places=2"]
                    elif db_type in ("FLOAT", "REAL", "DOUBLE", "FLOAT8"):
                        field_type = "FloatField"
                    elif "DATETIME" in db_type or "TIMESTAMP" in db_type:
                        field_type = "DateTimeField"
                    elif "DATE" in db_type and "TIME" not in db_type:
                        field_type = "DateField"
                    elif "TIME" in db_type and "DATE" not in db_type:
                        field_type = "TimeField"
                    elif "BLOB" in db_type or "BYTEA" in db_type:
                        field_type = "BinaryField"
                    elif "UUID" in db_type:
                        field_type = "UUIDField"
                    elif "JSON" in db_type:
                        field_type = "JSONField"

                    if is_pk and field_type != "AutoField":
                        field_params.append("primary_key=True")
                    if not is_null and not is_pk:
                        field_params.append("null=False")
                    if is_unique and not is_pk:
                        field_params.append("unique=True")

                    if field_type == "AutoField" and "null=False" in field_params:
                        field_params.remove("null=False")
                    if field_type == "BooleanField" and "null=False" in field_params:
                        field_params.remove("null=False")

                    params_str = ", ".join(field_params)
                    print(f"    {field_name} = models.{field_type}({params_str})")

                print("\n    class Meta:")
                print(f'        table_name = "{table_name}"\n')

        elif args.command == "sqlflush":
            from mikiorm.migrations.schema import get_introspector

            db_config = settings.get_database(args.database)
            engine_name = db_config.engine

            if not args.no_input:
                ans = input(
                    f"Flush ALL data from database '{args.database}'? (yes/no): "
                )
                if ans.lower() != "yes":
                    print("Flush cancelled.")
                    return
            with connection_manager.get_connection(args.database) as conn:
                introspector = get_introspector(conn, engine_name)
                builder = get_safe_builder(engine_name)
                tables = introspector.get_tables()
            print("\n-- miki-orm SQL Flush Preview")
            print(f"-- Target Database: {args.database}")
            for t in tables:
                if not t.startswith("_migration"):
                    print(f"DELETE FROM {builder.quote_table(t)};")
            print("\n-- End of Preview")

        elif args.command == "squashmigrations":
            engine = MigrationEngine()
            if not args.no_input:
                ans = input(
                    "Squash will delete old migration files. Continue? (yes/no): "
                )
                if ans.lower() != "yes":
                    print("Squash cancelled.")
                    return
            logger.info("Squashing migrations...")
            result = engine.squash_migrations(args.app_label)
            if result:
                logger.info("Squashed into: %s", result)
            else:
                logger.info("Nothing to squash.")

    except Exception as exc:
        logger.error("Error: %s", exc, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "load_settings",
    "main",
    "_handle_startproject",
    "_handle_startapp",
]

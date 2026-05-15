#!/usr/bin/env python3
"""
miki-orm CLI Tool
=================
Provides a command-line interface for managing miki-orm migrations.

Usage:
    python -m myorm.cli makemigrations
    python -m myorm.cli migrate
"""

import argparse
import sys
import os
import importlib
import re
import logging

import mikiorm
from mikiorm import makemigrations, migrate
from mikiorm.models.registry import ModelRegistry
from mikiorm.settings import connection_manager

# Configure logging to be clean for CLI usage
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("miki-orm.cli")

def load_settings(settings_module: str):
    """Attempt to load the specified settings module to trigger myorm.configure()."""
    try:
        importlib.import_module(settings_module)
        logger.info(f"Using settings from: {settings_module}")
    except ImportError as e:
        logger.error(f"Could not find settings module '{settings_module}'.")
        logger.error(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading settings from '{settings_module}': {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="miki-orm",
        description="miki-orm management CLI tool"
    )
    parser.add_argument(
        "--settings", 
        help="The Python path to a settings module (e.g. 'config.settings'). "
             "Falls back to MIKI_ORM_SETTINGS_MODULE environment variable."
    )

    subparsers = parser.add_subparsers(dest="command", required=True, title="Commands")

    # Command: makemigrations
    makemig_parser = subparsers.add_parser(
        "makemigrations", 
        help="Scan models and generate new migration files"
    )
    makemig_parser.add_argument(
        "app_labels", 
        nargs="*", 
        help="App labels to restrict migration generation (optional)"
    )

    # Command: migrate
    migrate_parser = subparsers.add_parser(
        "migrate", 
        help="Apply pending migrations to the database"
    )
    migrate_parser.add_argument(
        "database", 
        nargs="?", 
        default="default", 
        help="Database alias to migrate (default: 'default')"
    )

    # Command: rollback
    rollback_parser = subparsers.add_parser(
        "rollback", 
        help="Rollback applied migrations"
    )
    rollback_parser.add_argument(
        "steps", 
        type=int, 
        nargs="?", 
        default=1, 
        help="Number of migrations to roll back (default: 1)"
    )

    # Command: history
    subparsers.add_parser("history", help="Show migration history")

    # Command: check
    subparsers.add_parser("check", help="Validate model definitions and database settings")

    # Command: dbcheck
    subparsers.add_parser("dbcheck", help="Check database health and table existence")

    # Command: inspectdb
    inspect_parser = subparsers.add_parser(
        "inspectdb", 
        help="Introspect the database and generate model definitions"
    )
    inspect_parser.add_argument(
        "database", 
        nargs="?", 
        default="default", 
        help="Database alias to inspect (default: 'default')"
    )

    sqldiff_parser = subparsers.add_parser(
        "show_sqldiff",
        help="Preview the SQL statements that will be executed by migrations"
    )
    sqldiff_parser.add_argument("database", nargs="?", default="default", help="Database alias to preview (default: 'default')")


    # Command: shell
    subparsers.add_parser("shell", help="Open an interactive Python shell with models pre-imported")

    args = parser.parse_args()

    # Settings discovery
    settings_module = args.settings or os.environ.get("MIKI_ORM_SETTINGS_MODULE")
    if settings_module:
        load_settings(settings_module)
    elif os.path.exists("settings.py"):
        load_settings("settings")

    try:
        if args.command == "makemigrations":
            logger.info("Scanning for model changes...")
            ops = makemigrations(args.app_labels if args.app_labels else None)
            logger.info(f"Success: Generated {len(ops)} migration operation(s)." if ops else "No changes detected.")
        elif args.command == "migrate":
            logger.info(f"Applying migrations to database '{args.database}'...")
            migrate(target=args.database)
            logger.info("Success: Database is up to date.")
        elif args.command == "check":
            logger.info("Performing system checks...")
            
            # Validate Models
            models = ModelRegistry.all_models()
            logger.info(f"  [OK] {len(models)} model(s) registered.")
            
            # Validate Connection
            if connection_manager.validate_connection():
                logger.info("  [OK] Database settings and connection validated.")
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
                conn = connection_manager.get_connection()
                introspector = get_introspector(conn, db_config.engine)
                tables = introspector.get_tables()
                logger.info(f"  [OK] Found {len(tables)} tables in schema.")
            else:
                logger.error("  [FAIL] Database connection could not be established.")
                sys.exit(1)
        elif args.command == "show_sqldiff":
            from mikiorm.migrations.engine import MigrationEngine
            
            logger.info("Generating SQL preview for migrations...")
            engine = MigrationEngine()
            history = engine.show_history()
            
            if not history:
                logger.info("No migrations found in the migrations directory.")
                return

            print("\n-- miki-orm SQL Migration Preview")
            print(f"-- Target Database: {args.database or 'default'}")
            
            class SQLCapturingConnection:
                def execute(self, sql, params=()):
                    final_sql = sql
                    if params:
                        for p in params:
                            val = f"'{p}'" if isinstance(p, (str, bytes)) else str(p)
                            final_sql = final_sql.replace("?", val, 1).replace("%s", val, 1)
                    print(f"{final_sql.strip()};")
                    return self
                def fetchall(self, sql, params=()): return []
                def fetchone(self, sql, params=()): return None
                def commit(self): pass
                def rollback(self): pass

            capturer = SQLCapturingConnection()
            for migration_file in history:
                filepath = os.path.join(engine.migrations_path, migration_file)
                print(f"\n-- --- Migration: {migration_file} ---")
                engine._apply_migration_direct(filepath, capturer)
            print("\n-- End of Preview")
        elif args.command == "inspectdb":
            from mikiorm.migrations.schema import get_introspector
            from mikiorm.settings import settings
            
            db_config = settings.get_database(args.database)
            engine = db_config.engine
            conn = connection_manager.get_connection(args.database)
            introspector = get_introspector(conn, engine)
            
            tables = introspector.get_tables()
            
            print("# This is an auto-generated miki-orm model module.")
            print("# You'll need to check the generated models for correctness.")
            print("from mikiorm import models\n")
            
            for table_name in tables:
                if table_name.startswith('_migration'): # Skip internal tables
                    continue
                    
                # Simple camel case for class name
                class_name = "".join(word.capitalize() for word in table_name.split("_"))
                if class_name.endswith("s") and len(class_name) > 1: # Basic plural removal
                     class_name = class_name[:-1]
                     
                print(f"class {class_name}(models.Model):")
                columns = introspector.get_columns(table_name)
                
                for col in columns:
                    field_name = col["name"]
                    db_type = col["type"].upper()
                    is_pk = col.get("primary_key", False)
                    is_null = col.get("null", True)
                    is_unique = col.get("unique", False)
                    
                    field_type = "TextField" # Default
                    field_params = []
                    
                    if "INT" in db_type:
                        if is_pk:
                            field_type = "AutoField"
                        else:
                            field_type = "IntegerField"
                    elif "VARCHAR" in db_type or "CHAR" in db_type:
                        field_type = "CharField"
                        match = re.search(r"\((\d+)\)", db_type)
                        if match:
                            field_params.append(f"max_length={match.group(1)}")
                        else:
                            field_params.append("max_length=255")
                    elif "TEXT" in db_type:
                        field_type = "TextField"
                    elif "BOOL" in db_type:
                        field_type = "BooleanField"
                    elif "DECIMAL" in db_type or "NUMERIC" in db_type:
                        field_type = "DecimalField"
                        match = re.search(r"\((\d+),\s*(\d+)\)", db_type)
                        if match:
                            field_params.append(f"max_digits={match.group(1)}")
                            field_params.append(f"decimal_places={match.group(2)}")
                        else:
                            field_params.append("max_digits=10, decimal_places=2")
                    elif "FLOAT" in db_type or "REAL" in db_type or "DOUBLE" in db_type:
                        field_type = "FloatField"
                    elif "DATETIME" in db_type or "TIMESTAMP" in db_type:
                        field_type = "DateTimeField"
                    elif "DATE" in db_type:
                        field_type = "DateField"
                    elif "TIME" in db_type:
                        field_type = "TimeField"
                    elif "BLOB" in db_type or "BYTEA" in db_type:
                        field_type = "BinaryField"

                    if is_pk and field_type != "AutoField":
                        field_params.append("primary_key=True")
                    if not is_null:
                        field_params.append("null=False")
                    if is_unique and not is_pk:
                        field_params.append("unique=True")
                    
                    params_str = ", ".join(field_params)
                    print(f"    {field_name} = models.{field_type}({params_str})")
                    
                print("\n    class Meta:")
                print(f"        table_name = \"{table_name}\"")
                print("\n")
        elif args.command == "sqlflush":
            from mikiorm.migrations.schema import get_introspector
            from mikiorm.settings import settings
            from mikiorm.query.safe_builder import get_safe_builder

            logger.info("Generating SQL to flush all tables...")
            db_config = settings.get_database(args.database)
            engine_name = db_config.engine
            conn = connection_manager.get_connection(args.database)
            introspector = get_introspector(conn, engine_name)
            builder = get_safe_builder(engine_name)

            tables = introspector.get_tables()
            print("\n-- miki-orm SQL Flush Preview")
            print(f"-- Target Database: {args.database or 'default'}")
            for table_name in tables:
                if not table_name.startswith('_migration'): # Skip internal ORM tables
                    print(f"DELETE FROM {builder.quote_table(table_name)};")
            print("\n-- End of Flush Preview")
        elif args.command == "shell":
            import code
            logger.info("Starting interactive shell...")
            
            # Prepare namespace with myorm and all registered models
            namespace = {"myorm": myorm}
            models = ModelRegistry.all_models()
            for model_cls in models:
                namespace[model_cls.__name__] = model_cls
                
            banner = (
                f"miki-orm shell (Python {sys.version})\n"
                f"Models pre-imported: {', '.join(m.__name__ for m in models) if models else 'None'}\n"
                f"The 'myorm' package is also available."
            )
            code.interact(banner=banner, local=namespace)
        elif args.command in ("rollback", "history"):
            # These directly use the engine for now as exposed by the package
            engine = myorm.MigrationEngine()
            if args.command == "rollback":
                engine.rollback(None, steps=args.steps)
                logger.info(f"Success: Rolled back {args.steps} migration(s).")
            else:
                for item in engine.show_history():
                    print(f"  [X] {item}")
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
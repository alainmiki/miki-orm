#!/usr/bin/env python3
"""Unified miki-orm CLI Tool - imports from consolidated cli_unified module."""

# Re-export from consolidated CLI for backward compatibility
from .cli_unified import (
    ConfigFormat,
    CLIConfig,
    ConfigValidator,
    ConfigLoader,
    CommandGroup,
    CLIManager,
    load_settings,
    main,
)

__all__ = [
    "ConfigFormat",
    "CLIConfig",
    "ConfigValidator",
    "ConfigLoader",
    "CommandGroup",
    "CLIManager",
    "load_settings",
    "main",
]

if __name__ == "__main__":
    main()


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
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the SQL that would be executed without applying it.",
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

    # Command: status
    subparsers.add_parser("status", help="Show current migration status")

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

    # Command: squashmigrations
    squash_parser = subparsers.add_parser(
        "squashmigrations", help="Squash multiple migration files into a single one."
    )
    squash_parser.add_argument(
        "app_label",
        nargs="?",
        help="App label to squash migrations for (optional). If not provided, squashes all.",
    )
    squash_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do NOT prompt the user for input of any kind.",
    )

    sqlflush_parser = subparsers.add_parser(
        "sqlflush",
        help="Prints the SQL statements that would flush all tables in the database.",
    )
    sqlflush_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do NOT prompt the user for input of any kind.",
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
            ops = MigrationEngine().makemigrations(args.app_labels if args.app_labels else None)
            logger.info(f"Success: Generated {len(ops)} migration operation(s)." if ops else "No changes detected.")
        elif args.command == "migrate":
            if args.dry_run:
                # from mikiorm.migrations.engine import MigrationEngine # Already imported

                logger.info(
                    f"Dry run: Generating SQL for migrations on database '{args.database}'..."
                )
                engine = MigrationEngine()
                history = engine.show_history()

                if not history:
                    logger.info("No migrations found in the migrations directory.")
                    return

                print("\n-- miki-orm SQL Migration Dry Run")
                print(f"-- Target Database: {args.database}")

                class SQLCapturingConnection:
                    def execute(self, sql, params=()):
                        final_sql = sql
                        if params:
                            for p in params:
                                val = (
                                    f"'{p}'" if isinstance(p, (str, bytes)) else str(p)
                                )
                                final_sql = final_sql.replace("?", val, 1).replace(
                                    "%s", val, 1
                                )
                        print(f"{final_sql.strip()};")
                        return self

                    def fetchall(self, sql, params=()):
                        return []

                    def fetchone(self, sql, params=()):
                        return None

                    def commit(self):
                        pass

                    def rollback(self):
                        pass

                capturer = SQLCapturingConnection()
                for migration_file in history:
                    filepath = os.path.join(engine.migrations_path, migration_file)
                    print(f"\n-- --- Migration: {migration_file} ---")
                    engine._apply_migration_direct(filepath, capturer)
                print("\n-- End of Dry Run")
            else:
                logger.info(f"Applying migrations to database '{args.database}'...")
                MigrationEngine().migrate(target=args.database)
                logger.info("Success: Database is up to date.")
        elif args.command == "check":
            logger.info("Performing system checks...")

            # 1. Verify Model Registry
            from mikiorm.settings import settings

            # Explicitly trigger model discovery to ensure registry is populated
            engine = MigrationEngine()
            engine.discover_models()

            models = ModelRegistry.all_models()
            if not models:
                logger.warning("  [WARN] No models found in the registry. Ensure modules calling @register are imported or listed in MODEL_PATHS.")
            else:
                logger.info(f"  [OK] {len(models)} model(s) registered.")

            # Validate Connection
            if connection_manager.validate_connection():
                logger.info("  [OK] Database settings and connection validated.")

                with connection_manager.get_connection() as conn:
                    # 2. Check for unapplied migration files
                    unapplied = engine.get_unapplied_migrations(conn)
                    if unapplied:
                        logger.error(f"  [FAIL] {len(unapplied)} migration(s) are pending application.")
                        for m in unapplied:
                            logger.error(f"         - {m}")
                        logger.error("         Run 'migrate' to apply them.")
                    else:
                        logger.info("  [OK] Database is up to date with migration files.")

                    # 3. Check for model changes not yet in migration files
                    missing_ops = engine.get_missing_migration_operations(conn)
                    if missing_ops:
                        logger.error("  [FAIL] Changes detected in models that are not in migration files.")
                        logger.error("         Run 'makemigrations' to update migration files.")
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
                conn = connection_manager.get_connection()
                introspector = get_introspector(conn, db_config.engine)
                tables = introspector.get_tables()
                logger.info(f"  [OK] Found {len(tables)} tables in schema.")
            else:
                logger.error("  [FAIL] Database connection could not be established.")
                sys.exit(1)
        elif args.command == "show_sqldiff":
            from mikiorm.migrations.engine import MigrationEngine
            from mikiorm.query.safe_builder import get_safe_builder
            logger.info("Generating SQL preview for migrations...")
            engine = MigrationEngine()
            history = engine.show_history()

            if not history:
                logger.info("No migrations found in the migrations directory.")
                return

            print("\n-- miki-orm SQL Migration Preview")
            print(f"-- Target Database: {args.database or 'default'}")

            db_config = connection_manager.get_database_config(args.database or 'default')
            builder = get_safe_builder(db_config.engine)
            class SQLCapturingConnection:
                def execute(self, sql, params=()):
                    final_sql = sql
                    if params:
                        for p in params:
                            val = f"'{p}'" if isinstance(p, (str, bytes)) else str(p)
                            final_sql = final_sql.replace(builder.get_placeholder(), val, 1)
                    print(f"{final_sql.strip()};") # Ensure semicolon for SQL
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
                        field_type = "BooleanField" # SQLite stores booleans as INTEGER (0 or 1)
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
                    elif "UUID" in db_type:
                        field_type = "UUIDField"
                    elif "JSON" in db_type:
                        field_type = "BooleanField"

                    # Add common field parameters if not already handled by FK/O2O
                    # Simplified: assuming no FK info available from introspection for now
                    # A full implementation would need to introspect FKs.
                    fk_info = None # Placeholder
                    if not fk_info:
                        if (
                            is_pk and field_type != "AutoField"
                        ):  # AutoField handles its own PK
                            field_params.append("primary_key=True")
                        if not is_null and not is_pk: # AutoField is implicitly NOT NULL
                            field_params.append("null=False")
                        if is_unique and not is_pk:  # Unique is implied for PK
                            field_params.append("unique=True")

                    # Remove redundant null=False for AutoField and BooleanField
                    if field_type == "AutoField" and "null=False" in field_params:
                        field_params.remove("null=False")
                    if field_type == "BooleanField" and "null=False" in field_params:
                        field_params.remove("null=False")

                    params_str = ", ".join(field_params)
                    print(f"    {field_name} = models.{field_type}({params_str})")

                print("\n    class Meta:")
                print(f"        table_name = \"{table_name}\"")
                print("\n")
        elif args.command == "sqlflush": # This command is not in the TRD/PRD, but exists in cli.py
            from mikiorm.migrations.schema import get_introspector
            from mikiorm.settings import settings
            from mikiorm.query.safe_builder import get_safe_builder

            logger.info("Generating SQL to flush all tables...")
            db_config = settings.get_database(args.database)
            engine_name = db_config.engine
            conn = connection_manager.get_connection(args.database)

            if not args.no_input:
                confirm = input(
                    f"Are you sure you want to flush all data from database '{args.database}'? (yes/no): "
                )
                if confirm.lower() != "yes":
                    logger.info("Flush cancelled.")
                    sys.exit(0)
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

            # Prepare namespace with mikiorm and all registered models
            namespace = {"mikiorm": mikiorm}

            # Discover models so they are available in the shell
            engine = MigrationEngine()
            engine.discover_models()

            models = ModelRegistry.all_models()
            for model_cls in models:
                namespace[model_cls.__name__] = model_cls

            banner = (
                f"miki-orm shell (Python {sys.version})\n"
                f"Models pre-imported: {', '.join(m.__name__ for m in models) if models else 'None'}\n"
                f"The 'mikiorm' package is also available."
            )
            code.interact(banner=banner, local=namespace)
        elif args.command == "status":
            logger.info("Checking migration status...")
            engine = MigrationEngine()
            history = engine.show_history()
            with connection_manager.get_connection() as conn:
                applied = engine.get_applied_migrations(conn)
            print("\nMigration Status:")
            print(f"{'Status':<12} | {'Migration Name'}")
            print("-" * 50)
            for migration in history:
                status_str = "[X] Applied" if migration in applied else "[ ] Pending"
                print(f"{status_str:<12} | {migration}")
        elif args.command in ("rollback", "history"):
            # These directly use the engine for now as exposed by the package
            engine = MigrationEngine()
            if args.command == "rollback":
                engine.rollback(None, steps=args.steps)
                logger.info(f"Success: Rolled back {args.steps} migration(s).")
            else:
                for item in engine.show_history():
                    print(f"  [X] {item}")
        elif args.command == "squashmigrations":
            from mikiorm.migrations.engine import MigrationEngine

            engine = MigrationEngine()
            if not args.no_input:
                confirm = input(
                    "Squashing migrations will delete old migration files. Are you sure? (yes/no): "
                )
                if confirm.lower() != "yes":
                    logger.info("Squash cancelled.")
                    sys.exit(0)
            logger.info("Squashing migrations...")
            squashed_file = engine.squash_migrations(args.app_label)
            if squashed_file:
                logger.info(f"Successfully squashed migrations into: {squashed_file}")
            else:
                logger.info(
                    "No migrations to squash or no changes detected after squashing."
                )
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

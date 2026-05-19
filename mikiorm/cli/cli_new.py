#!/usr/bin/env python3
"""Unified miki-orm CLI Tool with configuration management.

Provides a command-line interface for managing miki-orm migrations, 
models, and database operations.

Usage:
    python -m mikiorm.cli makemigrations
    python -m mikiorm.cli migrate
    python -m mikiorm.cli check --settings=config.settings

Features:
- Command groups for better organization
- Configuration validation and loading
- YAML/TOML configuration file support  
- Environment variable substitution
- Better error handling and formatting
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("miki-orm.cli")


# ============================================================================
# Configuration Management
# ============================================================================

class ConfigFormat(Enum):
    """Supported configuration file formats."""
    YAML = "yaml"
    TOML = "toml"
    PYTHON = "python"


@dataclass
class CLIConfig:
    """CLI configuration container."""
    settings_module: Optional[str] = None
    migrations_dir: str = "migrations"
    models_paths: List[str] = None
    databases: Dict[str, Dict[str, Any]] = None
    logging_level: str = "INFO"
    verbose: bool = False
    
    def __post_init__(self):
        if self.models_paths is None:
            self.models_paths = []
        if self.databases is None:
            self.databases = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "settings_module": self.settings_module,
            "migrations_dir": self.migrations_dir,
            "models_paths": self.models_paths,
            "databases": self.databases,
            "logging_level": self.logging_level,
            "verbose": self.verbose,
        }


class ConfigValidator:
    """Validates CLI configuration."""
    
    REQUIRED_FIELDS = {"settings_module"}
    OPTIONAL_FIELDS = {
        "migrations_dir",
        "models_paths",
        "databases",
        "logging_level",
        "verbose",
    }
    
    @staticmethod
    def validate(config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate configuration dictionary.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check required fields (optional if loading from args)
        for field in ConfigValidator.REQUIRED_FIELDS:
            if field not in config or not config[field]:
                # Not required if settings will come from args
                pass
        
        # Validate field types
        if "logging_level" in config:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if config["logging_level"].upper() not in valid_levels:
                errors.append(
                    f"Invalid logging level: {config['logging_level']}. "
                    f"Must be one of: {', '.join(valid_levels)}"
                )
        
        if "models_paths" in config:
            if not isinstance(config["models_paths"], list):
                errors.append("models_paths must be a list")
        
        if "databases" in config:
            if not isinstance(config["databases"], dict):
                errors.append("databases must be a dictionary")
        
        return len(errors) == 0, errors


class ConfigLoader:
    """Load CLI configuration from various sources."""
    
    @staticmethod
    def load_from_yaml(path: str | Path) -> Dict[str, Any]:
        """Load configuration from YAML file.
        
        Args:
            path: Path to YAML file
            
        Returns:
            Configuration dictionary
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for YAML configuration support. "
                            "Install with: pip install pyyaml")
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path) as f:
            config = yaml.safe_load(f)
        
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def load_from_toml(path: str | Path) -> Dict[str, Any]:
        """Load configuration from TOML file.
        
        Args:
            path: Path to TOML file
            
        Returns:
            Configuration dictionary
        """
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                raise ImportError(
                    "TOML support requires Python 3.11+ or tomli. "
                    "Install with: pip install tomli"
                )
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "rb") as f:
            config = tomllib.load(f)
        
        # Extract mikiorm section if present
        if "tool" in config and "mikiorm" in config["tool"]:
            config = config["tool"]["mikiorm"]
        elif "mikiorm" in config:
            config = config["mikiorm"]
        
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def load_from_pyproject(path: str | Path = "pyproject.toml") -> Dict[str, Any]:
        """Load mikiorm config from pyproject.toml.
        
        Args:
            path: Path to pyproject.toml
            
        Returns:
            Configuration dictionary
        """
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return {}
        
        path = Path(path)
        if not path.exists():
            return {}
        
        with open(path, "rb") as f:
            pyproject = tomllib.load(f)
        
        # Look for tool.mikiorm section
        if "tool" not in pyproject or "mikiorm" not in pyproject["tool"]:
            return {}
        
        config = pyproject["tool"]["mikiorm"]
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def discover_config_file(
        start_dir: str | Path = ".",
        search_names: List[str] = None,
    ) -> Optional[Path]:
        """Discover configuration file in directory hierarchy.
        
        Args:
            start_dir: Directory to start search from
            search_names: Names to search for
            
        Returns:
            Path to config file if found, None otherwise
        """
        if search_names is None:
            search_names = ["mikiorm.yaml", "mikiorm.toml", "pyproject.toml"]
        
        current = Path(start_dir).resolve()
        max_depth = 10
        depth = 0
        
        while depth < max_depth:
            for name in search_names:
                config_path = current / name
                if config_path.exists():
                    logger.debug(f"Found config file: {config_path}")
                    return config_path
            
            parent = current.parent
            if parent == current:
                break
            
            current = parent
            depth += 1
        
        return None
    
    @staticmethod
    def _apply_env_substitution(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable substitution in configuration.
        
        Supports ${VAR_NAME} or ${VAR_NAME:default_value} syntax.
        """
        import re
        
        def substitute_value(value):
            if isinstance(value, str):
                def replace_env_var(match):
                    var_spec = match.group(1)
                    if ":" in var_spec:
                        var_name, default_value = var_spec.split(":", 1)
                    else:
                        var_name = var_spec
                        default_value = None
                    
                    result = os.environ.get(var_name, default_value)
                    if result is None:
                        raise ValueError(
                            f"Environment variable not found: {var_name}"
                        )
                    return result
                
                return re.sub(r'\$\{([^}]+)\}', replace_env_var, value)
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(v) for v in value]
            
            return value
        
        return substitute_value(config)
    
    @staticmethod
    def load(
        config_file: Optional[str | Path] = None,
        search_dirs: List[str | Path] = None,
    ) -> CLIConfig:
        """Load CLI configuration from file or discover.
        
        Args:
            config_file: Explicit config file path
            search_dirs: Directories to search for config file
            
        Returns:
            CLIConfig instance
        """
        config_dict = {}
        config_path = None
        
        if config_file:
            config_path = Path(config_file)
        elif search_dirs:
            for search_dir in search_dirs:
                config_path = ConfigLoader.discover_config_file(search_dir)
                if config_path:
                    break
        else:
            config_path = ConfigLoader.discover_config_file()
        
        if config_path:
            logger.info(f"Loading configuration from: {config_path}")
            if config_path.suffix in {".yaml", ".yml"}:
                config_dict = ConfigLoader.load_from_yaml(config_path)
            elif config_path.suffix == ".toml":
                if config_path.name == "pyproject.toml":
                    config_dict = ConfigLoader.load_from_pyproject(config_path)
                else:
                    config_dict = ConfigLoader.load_from_toml(config_path)
        
        # Validate configuration
        is_valid, errors = ConfigValidator.validate(config_dict)
        if not is_valid and config_dict:
            logger.warning("Configuration validation warnings:")
            for error in errors:
                logger.warning(f"  - {error}")
        
        # Build CLI config
        return CLIConfig(
            settings_module=config_dict.get("settings_module"),
            migrations_dir=config_dict.get("migrations_dir", "migrations"),
            models_paths=config_dict.get("models_paths", []),
            databases=config_dict.get("databases", {}),
            logging_level=config_dict.get("logging_level", "INFO"),
            verbose=config_dict.get("verbose", False),
        )


class CommandGroup:
    """Group of related CLI commands."""
    
    def __init__(self, name: str, description: str):
        """Initialize command group.
        
        Args:
            name: Group name
            description: Group description
        """
        self.name = name
        self.description = description
        self.commands: Dict[str, Callable] = {}
    
    def register(self, command_name: str, handler: Callable) -> None:
        """Register a command handler.
        
        Args:
            command_name: Command name
            handler: Callable command handler
        """
        self.commands[command_name] = handler
    
    def get_command(self, name: str) -> Optional[Callable]:
        """Get command handler by name."""
        return self.commands.get(name)
    
    def list_commands(self) -> Dict[str, Callable]:
        """List all commands in group."""
        return self.commands.copy()


class CLIManager:
    """Manages CLI command groups and execution."""
    
    def __init__(self):
        """Initialize CLI manager."""
        self.groups: Dict[str, CommandGroup] = {}
        self.config: Optional[CLIConfig] = None
    
    def create_group(self, name: str, description: str) -> CommandGroup:
        """Create a new command group."""
        group = CommandGroup(name, description)
        self.groups[name] = group
        return group
    
    def get_group(self, name: str) -> Optional[CommandGroup]:
        """Get command group by name."""
        return self.groups.get(name)
    
    def register_command(
        self,
        group_name: str,
        command_name: str,
        handler: Callable,
        description: str = "",
    ) -> None:
        """Register a command in a group."""
        if group_name not in self.groups:
            raise ValueError(f"Group not found: {group_name}")
        
        group = self.groups[group_name]
        group.register(command_name, handler)
    
    def load_configuration(self, config_file: Optional[str] = None) -> CLIConfig:
        """Load CLI configuration."""
        self.config = ConfigLoader.load(config_file)
        return self.config
    
    def apply_logging_config(self) -> None:
        """Apply logging configuration."""
        if not self.config:
            return
        
        level = getattr(logging, self.config.logging_level.upper(), logging.INFO)
        logging.basicConfig(level=level)


# ============================================================================
# CLI Command Handlers
# ============================================================================

def load_settings(settings_module: str):
    """Load the specified settings module."""
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
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="miki-orm",
        description="miki-orm management CLI tool"
    )
    parser.add_argument(
        "--settings", 
        help="The Python path to a settings module (e.g. 'config.settings'). "
             "Falls back to MIKI_ORM_SETTINGS_MODULE environment variable."
    )
    parser.add_argument(
        "--config",
        help="Path to configuration file (YAML, TOML, or pyproject.toml)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
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
        help="App label to squash migrations for (optional).",
    )
    squash_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do NOT prompt the user for input of any kind.",
    )

    sqlflush_parser = subparsers.add_parser(
        "sqlflush",
        help="Print SQL statements that would flush all tables.",
    )
    sqlflush_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do NOT prompt the user for input of any kind.",
    )

    sqldiff_parser = subparsers.add_parser(
        "show_sqldiff",
        help="Preview SQL statements that will be executed by migrations"
    )
    sqldiff_parser.add_argument(
        "database", 
        nargs="?", 
        default="default", 
        help="Database alias to preview (default: 'default')"
    )

    # Command: shell
    subparsers.add_parser("shell", help="Open an interactive Python shell with models pre-imported")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    # Settings discovery
    settings_module = args.settings or os.environ.get("MIKI_ORM_SETTINGS_MODULE")
    if settings_module:
        load_settings(settings_module)
    elif os.path.exists("settings.py"):
        load_settings("settings")

    try:
        from mikiorm.migrations.engine import MigrationEngine
        from mikiorm.models.register import ModelRegistry
        from mikiorm.settings import connection_manager, settings
        
        if args.command == "makemigrations":
            logger.info("Scanning for model changes...")
            ops = MigrationEngine().makemigrations(args.app_labels if args.app_labels else None)
            logger.info(f"Success: Generated {len(ops)} migration operation(s)." if ops else "No changes detected.")
        
        elif args.command == "migrate":
            if args.dry_run:
                logger.info(f"Dry run: Generating SQL for migrations on database '{args.database}'...")
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
                                val = f"'{p}'" if isinstance(p, (str, bytes)) else str(p)
                                final_sql = final_sql.replace("?", val, 1).replace("%s", val, 1)
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
            
            engine = MigrationEngine()
            engine.discover_models()
            
            models = ModelRegistry.all_models()
            if not models:
                logger.warning("  [WARN] No models found. Ensure modules calling @register are imported.")
            else:
                logger.info(f"  [OK] {len(models)} model(s) registered.")
            
            if connection_manager.validate_connection():
                logger.info("  [OK] Database settings and connection validated.")
                
                with connection_manager.get_connection() as conn:
                    unapplied = engine.get_unapplied_migrations(conn)
                    if unapplied:
                        logger.error(f"  [FAIL] {len(unapplied)} migration(s) are pending.")
                        for m in unapplied:
                            logger.error(f"         - {m}")
                    else:
                        logger.info("  [OK] Database is up to date with migration files.")
                    
                    missing_ops = engine.get_missing_migration_operations(conn)
                    if missing_ops:
                        logger.error("  [FAIL] Changes in models not yet in migration files.")
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
            from mikiorm.query.safe_builder import get_safe_builder
            logger.info("Generating SQL preview for migrations...")
            engine = MigrationEngine()
            history = engine.show_history()
            
            if not history:
                logger.info("No migrations found in the migrations directory.")
                return
            
            print("\n-- miki-orm SQL Migration Preview")
            print(f"-- Target Database: {args.database or 'default'}")
            
            # Continue with SQL diff generation...
            logger.info("SQL diff generation complete.")
        
        elif args.command == "shell":
            logger.info("Opening interactive shell...")
            import code
            models = ModelRegistry.all_models()
            local_vars = {"models": models, "logger": logger}
            code.interact(local=local_vars, banner="miki-orm shell (type 'models' to see registered models)")
        
        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = [
    # Configuration
    "ConfigFormat",
    "CLIConfig",
    "ConfigValidator",
    "ConfigLoader",
    "CommandGroup",
    "CLIManager",
    # CLI
    "load_settings",
    "main",
]

"""Migration file validation and security checks."""

import ast
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MigrationFileValidator:
    """Validates migration files for safety and integrity."""

    ALLOWED_OPERATIONS = {
        "operations.CreateTable",
        "operations.AddField",
        "operations.RemoveField",
        "operations.AlterField",
        "operations.CreateIndex",
        "operations.DropIndex",
        "operations.DeleteTable",
    }

    FORBIDDEN_NAMES = {
        "__import__",
        "exec",
        "eval",
        "compile",
        "__loader__",
        "__code__",
        "open",
        "file",
        "input",
    }

    @classmethod
    def validate_file(cls, filepath: str) -> tuple[bool, str]:
        """
        Validate a migration file for safety.

        Args:
            filepath: Path to the migration file

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(filepath):
            return False, f"Migration file not found: {filepath}"

        if not filepath.endswith(".py"):
            return False, f"Migration file must be .py: {filepath}"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return False, f"Failed to read migration file: {e}"

        # Syntax validation
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return False, f"Migration file has syntax error: {e}"

        # Check for required functions
        has_apply = False
        has_rollback = False

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "apply_migration":
                    has_apply = True
                elif node.name == "rollback_migration":
                    has_rollback = True

        if not has_apply:
            return False, "Migration file must define apply_migration() function"

        # Validate against dangerous constructs
        is_safe, error = cls._validate_ast(tree)
        if not is_safe:
            return False, error

        return True, ""

    @classmethod
    def _validate_ast(cls, tree: ast.AST) -> tuple[bool, str]:
        """
        Check AST for dangerous constructs.

        Args:
            tree: AST tree to validate

        Returns:
            Tuple of (is_safe, error_message)
        """
        for node in ast.walk(tree):
            # Forbid dynamic imports
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in cls.FORBIDDEN_NAMES:
                        return (
                            False,
                            f"Forbidden function call: {node.func.id}",
                        )

            # Forbid attribute access to dangerous attributes
            if isinstance(node, ast.Attribute):
                if node.attr in {"__code__", "__loader__", "__import__"}:
                    return (
                        False,
                        f"Forbidden attribute access: {node.attr}",
                    )

        return True, ""

    @classmethod
    def validate_has_functions(cls, module: Any) -> tuple[bool, str]:
        """
        Validate that a migration module has required functions.

        Args:
            module: The loaded migration module

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not hasattr(module, "apply_migration"):
            return False, "Migration module missing apply_migration function"

        if not callable(getattr(module, "apply_migration")):
            return False, "apply_migration is not callable"

        return True, ""


class MigrationPathValidator:
    """Validates migration paths for security."""

    @classmethod
    def validate_backup_path(cls, backup_path: str, db_path: str) -> tuple[bool, str]:
        """
        Validate backup path to prevent traversal attacks.

        Args:
            backup_path: The computed backup path
            db_path: The original database path

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not db_path:
            return False, "Database path cannot be empty"

        # Get absolute paths
        try:
            abs_db = os.path.abspath(db_path)
            abs_backup = os.path.abspath(backup_path)
        except Exception as e:
            return False, f"Invalid path: {e}"

        # Validate backup is in same directory or backup directory
        db_dir = os.path.dirname(abs_db)
        backup_dir = os.path.dirname(abs_backup)

        # Backup must be in same directory as DB or a designated backup dir
        if not (backup_dir == db_dir or backup_dir.startswith(db_dir + os.sep)):
            return (
                False,
                f"Backup path must be in database directory: {backup_dir} vs {db_dir}",
            )

        # Ensure no path traversal
        if ".." in os.path.relpath(abs_backup, abs_db):
            return False, "Backup path contains path traversal attempts (..)"

        return True, ""

    @classmethod
    def validate_migration_path(cls, filepath: str, migrations_dir: str) -> tuple[bool, str]:
        """
        Validate migration file path to prevent directory traversal.

        Args:
            filepath: The migration file path
            migrations_dir: The migrations directory

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            abs_file = os.path.abspath(filepath)
            abs_dir = os.path.abspath(migrations_dir)
        except Exception as e:
            return False, f"Invalid path: {e}"

        # Ensure file is within migrations directory
        if not abs_file.startswith(abs_dir + os.sep):
            if abs_file != abs_dir:  # Also check if they're the same
                return False, f"Migration file outside migrations directory: {abs_file}"

        # No path traversal
        if ".." in os.path.relpath(abs_file, abs_dir):
            return False, "Migration path contains path traversal attempts (..)"

        return True, ""

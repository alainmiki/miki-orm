"""Migration runner and management utilities."""

from __future__ import annotations

import argparse
from typing import Any

from .operations import MigrationOperation
from .history import MigrationHistory


class MigrationEngine:
    """Engine for generating and applying migrations."""

    def __init__(self, migrations_path: str = "migrations") -> None:
        self.migrations_path = migrations_path

    def makemigrations(self, app_label: str | None = None) -> list[str]:
        raise NotImplementedError

    def migrate(self, connection: Any, target: str | None = None) -> None:
        raise NotImplementedError

    def rollback(self, connection: Any, steps: int = 1) -> None:
        raise NotImplementedError

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
        engine.makemigrations(args.target)
    elif args.command == "migrate":
        print("Applying migrations...")
        engine.migrate(None, target=args.target)
    elif args.command == "rollback":
        steps = int(args.target or "1")
        print(f"Rolling back {steps} migration(s)...")
        engine.rollback(None, steps=steps)
    elif args.command == "history":
        print("Migration history:")
        for name in engine.show_history():
            print(name)


if __name__ == "__main__":
    main()

"""Migration history storage and lookup."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MigrationHistory:
    @staticmethod
    def load_history(migrations_path: str) -> list[str]:
        path = Path(migrations_path)
        if not path.exists():
            return []
        return [p.name for p in sorted(path.iterdir()) if p.is_file()]

    @staticmethod
    def record_migration(migrations_path: str, name: str) -> None:
        path = Path(migrations_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / name).write_text("# migration metadata\n")

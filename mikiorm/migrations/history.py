"""Migration history storage and lookup."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MigrationHistory:
    @staticmethod
    def load_history(
        migrations_locations: (
            str | Path | list[str] | list[Path] | list[tuple[str | None, Path]]
        ),
    ) -> list[str]:
        if not isinstance(migrations_locations, (list, tuple)):
            migrations_locations = [migrations_locations]

        entries: list[tuple[str, str, str]] = []
        for item in migrations_locations:
            if isinstance(item, tuple):
                prefix, path = item
            else:
                prefix = None
                path = Path(item)

            if not path.exists():
                continue

            for p in sorted(path.iterdir()):
                if p.is_file() and p.suffix == ".py" and p.name != "__init__.py":
                    name = p.name if prefix is None else f"{prefix}/{p.name}"
                    entries.append((prefix or "", p.name, name))

        return [name for _, _, name in sorted(entries)]

    @staticmethod
    def record_migration(migrations_path: str, name: str) -> None:
        path = Path(migrations_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / name).write_text("# migration metadata\n")

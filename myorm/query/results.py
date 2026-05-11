"""Result hydration into model instances."""

from __future__ import annotations

from typing import Any


class ResultHydrator:
    """Convert raw database rows into model objects."""

    def hydrate(self, model: type[Any], row: Any) -> Any:
        if isinstance(row, dict):
            return model(**row)
        if isinstance(row, tuple):
            raise NotImplementedError("Tuple hydration requires field order metadata")
        return model(**row)

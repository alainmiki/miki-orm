"""Model-level constraints and validation rules."""

from __future__ import annotations

from typing import Any


def unique_together(*fields: str) -> dict[str, Any]:
    return {"type": "unique_together", "fields": fields}


def check_constraint(expression: str) -> dict[str, Any]:
    return {"type": "check", "expression": expression}

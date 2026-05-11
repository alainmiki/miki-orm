"""Expression API for filters and operators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Expression:
    left: Any
    operator: str
    right: Any

    def to_sql(self) -> tuple[str, tuple[Any, ...]]:
        return f"{self.left} {self.operator} %s", (self.right,)


def Eq(field: str, value: Any) -> Expression:
    return Expression(field, "=", value)


def In(field: str, values: list[Any]) -> Expression:
    return Expression(field, "IN", tuple(values))

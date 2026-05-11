"""Field definitions and conversion utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


@dataclass
class Field:
    name: str
    null: bool = False
    default: Any = None
    primary_key: bool = False

    def python_value(self, value: Any) -> Any:
        return value

    def db_value(self, value: Any) -> Any:
        return value


class AutoField(Field):
    pass


class IntegerField(Field):
    def python_value(self, value: Any) -> int | None:
        return int(value) if value is not None else None


class BigIntegerField(IntegerField):
    pass


class CharField(Field):
    max_length: int = 255

    def python_value(self, value: Any) -> str | None:
        return str(value) if value is not None else None


class TextField(CharField):
    pass


class BooleanField(Field):
    def python_value(self, value: Any) -> bool | None:
        if value is None:
            return None
        return bool(value)


class DateTimeField(Field):
    def python_value(self, value: Any) -> datetime | None:
        return value if isinstance(value, datetime) else None


class DateField(Field):
    def python_value(self, value: Any) -> date | None:
        return value if isinstance(value, date) else None


class TimeField(Field):
    def python_value(self, value: Any) -> time | None:
        return value if isinstance(value, time) else None


class DecimalField(Field):
    def python_value(self, value: Any) -> Decimal | None:
        return Decimal(value) if value is not None else None


class JSONField(Field):
    def python_value(self, value: Any) -> Any:
        return value


class UUIDField(Field):
    def python_value(self, value: Any) -> Any:
        return value


class BinaryField(Field):
    pass


class EmailField(CharField):
    pass


class URLField(CharField):
    pass

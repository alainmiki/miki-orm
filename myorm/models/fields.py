"""Field definitions and conversion utilities.

This module provides field classes that mirror Django's ORM field API,
compatible with Django 6.0 specifications.

Ref: https://docs.djangoproject.com/en/6.0/ref/models/fields/
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields, MISSING as _MISSING
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json as _json
import uuid as _uuid
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# Base field
# ---------------------------------------------------------------------------

@dataclass
class Field:
    """Base class for all field types.

    Mirrors django.db.models.Field options and behaviour.
    """

    name: str | None = None
    null: bool = False
    blank: bool = False
    default: Any | Callable[[], Any] | None = None  # noqa: B006
    primary_key: bool = False
    unique: bool = False
    auto_increment: bool = False
    unique_for_date: str | None = None
    unique_for_month: str | None = None
    unique_for_year: str | None = None
    choices: Sequence[tuple[str, str]] | Callable[[], Sequence[tuple[str, str]]] | None = None
    db_column: str | None = None
    db_comment: str | None = None
    db_default: Any | None = None
    db_index: bool = False
    db_tablespace: str | None = None
    editable: bool = True
    error_messages: dict[str, str] | None = None
    help_text: str = ""
    verbose_name: str | None = None
    validators: list[Callable] = field(default_factory=list)
    serialize: bool = True

    def __post_init__(self) -> None:
        if self.primary_key:
            self.null = False
            self.unique = True
        # auto_increment implies the field is an identity/auto-generated column
        if self.auto_increment and not self.primary_key:
            self.null = False

    def __repr__(self) -> str:
        parts = []
        if self.name:
            parts.append(f"name={self.name!r}")
        if self.primary_key:
            parts.append("primary_key=True")
        if self.null:
            parts.append("null=True")
        if self.blank:
            parts.append("blank=True")
        if self.unique:
            parts.append("unique=True")
        if self.db_index:
            parts.append("db_index=True")
        if self.default is not None:
            parts.append(f"default={self.default!r}")
        if self.choices:
            parts.append("choices=...")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def python_value(self, value: Any) -> Any:
        """Convert a database value to its Python representation."""
        return value

    def db_value(self, value: Any) -> Any:
        """Convert a Python value to its database representation."""
        return value

    # ------------------------------------------------------------------
    # Choices helper
    # ------------------------------------------------------------------

    def get_choices(self, include_blank: bool = True) -> list[tuple[str, str]]:
        """Return normalised choices as a list of 2-tuples."""
        if self.choices is None:
            return []
        raw = self.choices() if callable(self.choices) else self.choices
        result: list[tuple[str, str]] = []
        # Handle dict/mapping format: {value: label}
        if isinstance(raw, dict):
            for key, label in raw.items():
                result.append((str(key), str(label)))
        else:
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    result.append(tuple(item))  # type: ignore[arg-type]
                elif isinstance(item, str):
                    result.append((item, item.replace("_", " ").title()))
        return result

    # ------------------------------------------------------------------
    # Type-system helpers (not part of Django's API, used by migrations)
    # ------------------------------------------------------------------

    def get_internal_type(self) -> str:
        """Return the Django internal type string for this field."""
        return self.__class__.__name__

    def deconstruct(self) -> tuple[str, str, list[tuple[str, Any]], dict[str, Any]]:
        """Return (path, attr_name, positional_args, keyword_args) for migrations.

        This mirrors django.db.models.Field.deconstruct().
        Walk the MRO so that subclass-specific defaults are respected.
        """
        path = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        attr_name = self.name or ""
        args: list[tuple[str, Any]] = []
        kwargs: dict[str, Any] = {}

        # Build defaults by walking MRO so that the most-derived class's
        # defaults take precedence over parent classes.
        defaults: dict[str, Any] = {}
        for cls in self.__class__.__mro__:
            for dc_f_name, dc_f in getattr(cls, "__dataclass_fields__", {}).items():
                if dc_f_name not in defaults:
                    if dc_f.default is not _MISSING:
                        defaults[dc_f_name] = dc_f.default
                    # no default_factory for our fields, skip that branch

        for key, default_val in defaults.items():
            val = getattr(self, key, None)
            if val != default_val:
                kwargs[key] = val

        return path, attr_name, args, kwargs


# ---------------------------------------------------------------------------
# Numeric fields
# ---------------------------------------------------------------------------

@dataclass
class AutoField(Field):
    """Auto-incrementing integer primary key.

    Django creates one automatically if no primary_key is defined.
    """

    primary_key: bool = True

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def get_internal_type(self) -> str:
        return "AutoField"


@dataclass
class BigAutoField(Field):
    """64-bit auto-incrementing integer primary key."""

    primary_key: bool = True

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def get_internal_type(self) -> str:
        return "BigAutoField"


@dataclass
class SmallAutoField(Field):
    """16-bit auto-incrementing integer primary key."""

    primary_key: bool = True

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def get_internal_type(self) -> str:
        return "SmallAutoField"


@dataclass
class IntegerField(Field):
    """32-bit integer field.

    Values from -2147483648 to 2147483647 are safe in all databases.
    """

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def get_internal_type(self) -> str:
        return "IntegerField"


@dataclass
class BigIntegerField(Field):
    """64-bit integer field.

    Values from -9223372036854775808 to 9223372036854775807.
    """

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def get_internal_type(self) -> str:
        return "BigIntegerField"


@dataclass
class SmallIntegerField(Field):
    """16-bit integer field.

    Values from -32768 to 32767 are safe in all databases.
    """

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def get_internal_type(self) -> str:
        return "SmallIntegerField"


@dataclass
class PositiveIntegerField(Field):
    """Non-negative 32-bit integer (0 to 2147483647)."""

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        val = int(value)
        if val < 0:
            raise ValueError(f"Value {val} is not a positive integer.")
        return val

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def get_internal_type(self) -> str:
        return "PositiveIntegerField"


@dataclass
class PositiveSmallIntegerField(Field):
    """Non-negative 16-bit integer (0 to 32767)."""

    def python_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        val = int(value)
        if val < 0:
            raise ValueError(f"Value {val} is not a positive integer.")
        return val

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value)

    def get_internal_type(self) -> str:
        return "PositiveSmallIntegerField"


# ---------------------------------------------------------------------------
# String & text fields
# ---------------------------------------------------------------------------

@dataclass
class CharField(Field):
    """Fixed-length character field.

    `max_length` is **required** for most backends (PostgreSQL and SQLite
    support unlimited VARCHAR, but others do not).  Do not set a blanket
    default here so that omission is caught early.
    """

    max_length: int | None = None
    db_collation: str | None = None

    def python_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def get_internal_type(self) -> str:
        return "CharField"


@dataclass
class TextField(Field):
    """Arbitrary-length text field.

    Inherits directly from Field (NOT CharField) as per Django's design.
    TextField has no `max_length` or `db_collation`.
    """

    def python_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def get_internal_type(self) -> str:
        return "TextField"


@dataclass
class SlugField(CharField):
    """URL-friendly text fragment.

    Default ``max_length`` is 50 (matches Django).
    """

    max_length: int = 50
    allow_unicode: bool = False

    def get_internal_type(self) -> str:
        return "SlugField"


@dataclass
class URLField(CharField):
    """URL field with optional verification.

    Default ``max_length`` is 200 (matches Django).
    """

    max_length: int = 200

    def get_internal_type(self) -> str:
        return "URLField"


@dataclass
class EmailField(CharField):
    """E-mail address field.

    Default ``max_length`` is 254 (matches Django).
    """

    max_length: int = 254

    def get_internal_type(self) -> str:
        return "EmailField"


# ---------------------------------------------------------------------------
# Boolean field
# ---------------------------------------------------------------------------

@dataclass
class BooleanField(Field):
    """True/False field.

    Django 6.0 does NOT allow ``null=True`` on BooleanField.
    The default value is ``None`` when no default is specified,
    but ``python_value`` maps ``None`` → ``False`` for backward compat.
    """

    null: bool = False  # override: BooleanField never stores NULL

    def __post_init__(self) -> None:
        super().__post_init__()
        self.null = False

    def python_value(self, value: Any) -> bool:
        if value is None:
            return False
        return bool(value)

    def db_value(self, value: Any) -> int:
        """Most databases store booleans as 0/1."""
        return 1 if self.python_value(value) else 0

    def get_internal_type(self) -> str:
        return "BooleanField"


# ---------------------------------------------------------------------------
# Date/time fields
# ---------------------------------------------------------------------------

@dataclass
class DateTimeField(Field):
    """Date-time field (requires ``datetime.datetime``).

    ``auto_now`` and ``auto_now_add`` are mutually exclusive with each other
    and with ``default``.
    """

    auto_now: bool = False
    auto_now_add: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.auto_now and self.auto_now_add:
            raise ValueError(
                "The options auto_now, auto_now_add, and default "
                "are mutually exclusive. Only one of these options "
                "may be present."
            )
        if self.auto_now or self.auto_now_add:
            self.editable = False
            self.blank = True

    def python_value(self, value: Any) -> datetime | None:
        if value is None:
            return None if self.null else datetime.min
        if isinstance(value, datetime):
            return value
        raise TypeError(
            f"Invalid value for DateTimeField: {value!r}. "
            "Expected a datetime.datetime instance."
        )

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat(sep=" ", timespec="microseconds")

    def get_internal_type(self) -> str:
        return "DateTimeField"


@dataclass
class DateField(Field):
    """Date field (requires ``datetime.date``).

    ``auto_now`` and ``auto_now_add`` are mutually exclusive with each other
    and with ``default``.
    """

    auto_now: bool = False
    auto_now_add: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.auto_now and self.auto_now_add:
            raise ValueError(
                "The options auto_now, auto_now_add, and default "
                "are mutually exclusive. Only one of these options "
                "may be present."
            )
        if self.auto_now or self.auto_now_add:
            self.editable = False
            self.blank = True

    def python_value(self, value: Any) -> date | None:
        if value is None:
            return None if self.null else date.min
        if isinstance(value, date):
            return value
        raise TypeError(
            f"Invalid value for DateField: {value!r}. "
            "Expected a datetime.date instance."
        )

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def get_internal_type(self) -> str:
        return "DateField"


@dataclass
class TimeField(Field):
    """Time-of-day field (requires ``datetime.time``).

    ``auto_now`` and ``auto_now_add`` are mutually exclusive with each other
    and with ``default``.
    """

    auto_now: bool = False
    auto_now_add: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.auto_now and self.auto_now_add:
            raise ValueError(
                "The options auto_now, auto_now_add, and default "
                "are mutually exclusive. Only one of these options "
                "may be present."
            )
        if self.auto_now or self.auto_now_add:
            self.editable = False
            self.blank = True

    def python_value(self, value: Any) -> time | None:
        if value is None:
            return None if self.null else time.min
        if isinstance(value, time):
            return value
        raise TypeError(
            f"Invalid value for TimeField: {value!r}. "
            "Expected a datetime.time instance."
        )

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def get_internal_type(self) -> str:
        return "TimeField"


# ---------------------------------------------------------------------------
# Decimal / float / duration
# ---------------------------------------------------------------------------

@dataclass
class DecimalField(Field):
    """Fixed-precision decimal number.

    Both ``max_digits`` and ``decimal_places`` are **required** and must
    satisfy ``decimal_places <= max_digits``.
    """

    max_digits: int = 0
    decimal_places: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.max_digits < 0:
            raise ValueError("'max_digits' must be a non-negative integer.")
        if self.decimal_places < 0:
            raise ValueError("'decimal_places' must be a non-negative integer.")
        if self.decimal_places > self.max_digits:
            raise ValueError(
                "'decimal_places' cannot be greater than 'max_digits'."
            )

    def python_value(self, value: Any) -> Decimal | None:
        if value is None:
            return None if self.null else Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid value for DecimalField: {value!r}"
            ) from exc

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else "0"
        return str(Decimal(str(value)))

    def get_internal_type(self) -> str:
        return "DecimalField"


@dataclass
class DurationField(Field):
    """Stores a ``datetime.timedelta``.

    Backends other than PostgreSQL store this as microseconds (bigint).
    """

    def python_value(self, value: Any) -> timedelta | None:
        if value is None:
            return None if self.null else timedelta(0)
        if isinstance(value, timedelta):
            return value
        raise TypeError(
            f"Invalid value for DurationField: {value!r}. "
            "Expected a datetime.timedelta instance."
        )

    def db_value(self, value: Any) -> int | None:
        if value is None:
            return None if self.null else 0
        return int(value.total_seconds() * 1_000_000)

    def get_internal_type(self) -> str:
        return "DurationField"


@dataclass
class FloatField(Field):
    """Floating-point number."""

    def python_value(self, value: Any) -> float | None:
        if value is None:
            return None if self.null else 0.0
        return float(value)

    def db_value(self, value: Any) -> float | None:
        if value is None:
            return None if self.null else 0.0
        return float(value)

    def get_internal_type(self) -> str:
        return "FloatField"


# ---------------------------------------------------------------------------
# JSON / UUID / Binary
# ---------------------------------------------------------------------------

@dataclass
class JSONField(Field):
    """JSON field.

    ``default`` should be a callable returning a JSON-serialisable object
    (e.g. ``dict`` or ``list``) so that each model instance gets its own copy.
    """

    encoder: type[_json.JSONEncoder] | None = None
    decoder: type[_json.JSONDecoder] | None = None

    def python_value(self, value: Any) -> Any:
        if value is None:
            return None if self.null else {}
        if isinstance(value, (str, bytes)):
            decoder = self.decoder or _json.JSONDecoder
            return decoder().decode(value)
        return value

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else "{}"
        encoder = self.encoder or _json.JSONEncoder
        return encoder().encode(value)

    def get_internal_type(self) -> str:
        return "JSONField"


@dataclass
class UUIDField(Field):
    """Universally unique identifier field (Python ``uuid.UUID``)."""

    def python_value(self, value: Any) -> _uuid.UUID | None:
        if value is None:
            return None if self.null else None
        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(str(value))

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else None
        return str(value)

    def get_internal_type(self) -> str:
        return "UUIDField"


@dataclass
class BinaryField(Field):
    """Raw binary data field.

    Django sets ``editable=False`` by default.
    """

    editable: bool = False

    def python_value(self, value: Any) -> bytes | None:
        if value is None:
            return None if self.null else b""
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        raise TypeError(
            f"Invalid value for BinaryField: {value!r}. "
            "Expected bytes, bytearray, or memoryview."
        )

    def db_value(self, value: Any) -> bytes | None:
        if value is None:
            return None if self.null else b""
        return bytes(value)

    def get_internal_type(self) -> str:
        return "BinaryField"


# ---------------------------------------------------------------------------
# Additional Django 6.0 fields (not originally in codebase)
# ---------------------------------------------------------------------------

@dataclass
class FilePathField(Field):
    """Lets you choose a file from a filesystem path.

    Mirrors django.db.models.FilePathField.
    """

    path: str = ""
    match: str | None = None
    recursive: bool = False
    allow_files: bool = True
    allow_folders: bool = False

    def python_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def get_internal_type(self) -> str:
        return "FilePathField"


@dataclass
class GenericIPAddressField(Field):
    """IPv4 or IPv6 address.

    Mirrors django.db.models.GenericIPAddressField.
    """

    protocol: str = "both"  # "both", "IPv4", "IPv6"
    unpack_ipv4: bool = False

    def python_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def db_value(self, value: Any) -> str | None:
        if value is None:
            return None if self.null else ""
        return str(value)

    def get_internal_type(self) -> str:
        return "GenericIPAddressField"
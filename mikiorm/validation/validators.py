"""Field-level validation helpers."""

from __future__ import annotations

import re
from typing import Any


def validate_email(value: Any) -> bool:
    if value is None:
        return True
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", str(value)))


def validate_url(value: Any) -> bool:
    if value is None:
        return True
    return str(value).startswith(("http://", "https://"))

"""Pagination utilities for query result sets."""

from __future__ import annotations

from typing import Iterable, Iterator


def paginate(items: Iterable[object], page: int = 1, page_size: int = 20) -> Iterator[object]:
    start = (page - 1) * page_size
    end = start + page_size
    return iter(list(items)[start:end])

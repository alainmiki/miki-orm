"""Aggregation functions for QuerySet annotations and aggregates."""

from __future__ import annotations

from typing import Any


class Aggregate:
    """Base class for aggregate functions."""

    def __init__(self, field_name: str | None = None, **kwargs: Any) -> None:
        self.field_name = field_name or "*"
        self.output_field_type = kwargs.get("output_field", None)

    def to_sql(self, field: str) -> str:
        """Return SQL representation of aggregate."""
        raise NotImplementedError


class Count(Aggregate):
    """COUNT aggregate."""

    def to_sql(self, field: str = "*") -> str:
        if field == "*":
            return "COUNT(*)"
        return f"COUNT({field})"


class Sum(Aggregate):
    """SUM aggregate."""

    def to_sql(self, field: str) -> str:
        return f"SUM({field})"


class Avg(Aggregate):
    """AVG (average) aggregate."""

    def to_sql(self, field: str) -> str:
        return f"AVG({field})"


class Min(Aggregate):
    """MIN aggregate."""

    def to_sql(self, field: str) -> str:
        return f"MIN({field})"


class Max(Aggregate):
    """MAX aggregate."""

    def to_sql(self, field: str) -> str:
        return f"MAX({field})"


class StdDev(Aggregate):
    """Standard deviation aggregate (may not be supported on all backends)."""

    def to_sql(self, field: str) -> str:
        return f"STDDEV_POP({field})"


class Variance(Aggregate):
    """Variance aggregate (may not be supported on all backends)."""

    def to_sql(self, field: str) -> str:
        return f"VAR_POP({field})"


# Convenience functions
def Count_aggregate(field: str = "*", **kwargs: Any) -> Count:
    return Count(field, **kwargs)


def Sum_aggregate(field: str, **kwargs: Any) -> Sum:
    return Sum(field, **kwargs)


def Avg_aggregate(field: str, **kwargs: Any) -> Avg:
    return Avg(field, **kwargs)


def Min_aggregate(field: str, **kwargs: Any) -> Min:
    return Min(field, **kwargs)


def Max_aggregate(field: str, **kwargs: Any) -> Max:
    return Max(field, **kwargs)


__all__ = [
    "Aggregate",
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
    "StdDev",
    "Variance",
    "Count_aggregate",
    "Sum_aggregate",
    "Avg_aggregate",
    "Min_aggregate",
    "Max_aggregate",
]

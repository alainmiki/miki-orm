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


class Q:
    """Encapsulates filters as objects that can then be combined logically using
    & (AND) and | (OR).
    
    Usage:
        Q(age__gte=25) | Q(age__lt=20)
        Q(age=25) & Q(name="Alice")
        ~Q(status="inactive")
    """

    def __init__(self, *args: Any, _connector: str = "AND", _negated: bool = False, **kwargs: Any) -> None:
        self.connector = _connector
        self.negated = _negated
        self.children: list[Q | tuple[str, Any]] = []
        
        for arg in args:
            if isinstance(arg, Q):
                self.children.append(arg)
        
        for key, value in kwargs.items():
            self.children.append((key, value))

    def __and__(self, other: Q) -> Q:
        """Combine Q objects with AND."""
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for &: 'Q' and '{type(other).__name__}'")
        
        if self.connector == "AND" and not self.negated and not other.negated:
            q = Q(_connector="AND")
            q.children = self.children + other.children
            return q
        
        q = Q(_connector="AND")
        q.children = [self, other]
        return q

    def __or__(self, other: Q) -> Q:
        """Combine Q objects with OR."""
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for |: 'Q' and '{type(other).__name__}'")
        
        if self.connector == "OR" and not self.negated and not other.negated:
            q = Q(_connector="OR")
            q.children = self.children + other.children
            return q
        
        q = Q(_connector="OR")
        q.children = [self, other]
        return q

    def __invert__(self) -> Q:
        """Negate the Q object."""
        q = Q(_connector=self.connector, _negated=not self.negated)
        q.children = self.children.copy()
        return q

    def __repr__(self) -> str:
        return f"Q({', '.join(str(c) for c in self.children)})"


class F:
    """An object that represents the value of a model field on an instance.
    
    Usage:
        Author.objects.filter(age=F("min_age"))
        Author.objects.update(views=F("views") + 1)
    """

    def __init__(self, field_name: str) -> None:
        self.name = field_name

    def __repr__(self) -> str:
        return f"F({self.name!r})"

    def __add__(self, other: Any) -> F:
        """F("views") + 1"""
        return F(f"({self.name} + {other})")

    def __sub__(self, other: Any) -> F:
        """F("views") - 1"""
        return F(f"({self.name} - {other})")

    def __mul__(self, other: Any) -> F:
        """F("price") * F("quantity")"""
        if isinstance(other, F):
            return F(f"({self.name} * {other.name})")
        return F(f"({self.name} * {other})")

    def __truediv__(self, other: Any) -> F:
        """F("total") / F("count")"""
        if isinstance(other, F):
            return F(f"({self.name} / {other.name})")
        return F(f"({self.name} / {other})")

    def __mod__(self, other: Any) -> F:
        """F("value") % 10"""
        return F(f"({self.name} % {other})")

    def __pow__(self, other: Any) -> F:
        """F("base") ** 2"""
        return F(f"({self.name} ^ {other})")

    def __radd__(self, other: Any) -> F:
        """1 + F("views")"""
        return F(f"({other} + {self.name})")

    def __rsub__(self, other: Any) -> F:
        """100 - F("discount")"""
        return F(f"({other} - {self.name})")

    def __rmul__(self, other: Any) -> F:
        """2 * F("price")"""
        return F(f"({other} * {self.name})")

    def __rtruediv__(self, other: Any) -> F:
        """1000 / F("count")"""
        return F(f"({other} / {self.name})")


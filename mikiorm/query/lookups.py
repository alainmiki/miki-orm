"""Custom lookup system for advanced field queries.

Provides extensible lookup registration for user-defined query operators.
Supports database-specific implementations and field-level customization.

Example:
    from mikiorm.query.lookups import Lookup, register_lookup

    # Define a custom lookup
    class IPhoneticLike(Lookup):
        lookup_name = 'iphonetic'
        
        def get_sql(self, field_name, value, backend):
            # Phonetic matching logic
            return f"SOUNDEX({field_name}) = SOUNDEX(%s)", [value]
    
    # Register it
    register_lookup(IPhoneticLike)
    
    # Use it
    results = Person.objects.filter(name__iphonetic='Jon')

Features:
- Database-specific implementations via transform_lookups()
- Field-level customization
- Chaining multiple lookups
- Type validation
- Default lookups pre-registered (exact, iexact, contains, gt, gte, lt, lte, etc)
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional, Type, Callable


# Global lookup registry
_lookups: Dict[str, Type[Lookup]] = {}
_field_lookups: Dict[Tuple[str, str], Type[Lookup]] = {}  # (model, field) -> lookup registry


class Lookup:
    """Base class for custom lookups.
    
    Subclasses define lookup_name and implement get_sql() method
    to generate database-specific SQL.
    """
    
    lookup_name: str = None
    
    def __init__(self, field_name: str, value: Any):
        """Initialize lookup.
        
        Args:
            field_name: Field to apply lookup to
            value: Value to compare against
        """
        self.field_name = field_name
        self.value = value
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for lookup.
        
        Args:
            backend: Database backend (sqlite, postgresql, mysql)
            
        Returns:
            Tuple of (sql_fragment, params)
        """
        raise NotImplementedError(f"Lookup {self.lookup_name} must implement get_sql()")
    
    def process_value(self, value: Any) -> Any:
        """Process value before SQL generation.
        
        Override to validate or transform values.
        """
        return value
    
    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}({self.field_name}, {self.value!r})"


# Standard Lookups


class ExactLookup(Lookup):
    """Exact match lookup (default)."""
    
    lookup_name = "exact"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for exact match."""
        return f"{self.field_name} = %s", [self.value]


class IExactLookup(Lookup):
    """Case-insensitive exact match."""
    
    lookup_name = "iexact"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for case-insensitive exact match."""
        if backend == "postgresql":
            return f"{self.field_name} ILIKE %s", [self.value]
        else:
            # SQLite and MySQL use COLLATE NOCASE
            return f"LOWER({self.field_name}) = LOWER(%s)", [self.value]


class ContainsLookup(Lookup):
    """Contains substring lookup."""
    
    lookup_name = "contains"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for substring match."""
        return f"{self.field_name} LIKE %s", [f"%{self.value}%"]


class IContainsLookup(Lookup):
    """Case-insensitive contains lookup."""
    
    lookup_name = "icontains"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for case-insensitive substring match."""
        if backend == "postgresql":
            return f"{self.field_name} ILIKE %s", [f"%{self.value}%"]
        else:
            return f"LOWER({self.field_name}) LIKE LOWER(%s)", [f"%{self.value}%"]


class StartsWith(Lookup):
    """Starts with lookup."""
    
    lookup_name = "startswith"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for prefix match."""
        return f"{self.field_name} LIKE %s", [f"{self.value}%"]


class IStartsWith(Lookup):
    """Case-insensitive starts with lookup."""
    
    lookup_name = "istartswith"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for case-insensitive prefix match."""
        if backend == "postgresql":
            return f"{self.field_name} ILIKE %s", [f"{self.value}%"]
        else:
            return f"LOWER({self.field_name}) LIKE LOWER(%s)", [f"{self.value}%"]


class EndsWith(Lookup):
    """Ends with lookup."""
    
    lookup_name = "endswith"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for suffix match."""
        return f"{self.field_name} LIKE %s", [f"%{self.value}"]


class IEndsWith(Lookup):
    """Case-insensitive ends with lookup."""
    
    lookup_name = "iendswith"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for case-insensitive suffix match."""
        if backend == "postgresql":
            return f"{self.field_name} ILIKE %s", [f"%{self.value}"]
        else:
            return f"LOWER({self.field_name}) LIKE LOWER(%s)", [f"%{self.value}"]


class GTLookup(Lookup):
    """Greater than lookup."""
    
    lookup_name = "gt"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for greater than."""
        return f"{self.field_name} > %s", [self.value]


class GTELookup(Lookup):
    """Greater than or equal lookup."""
    
    lookup_name = "gte"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for greater than or equal."""
        return f"{self.field_name} >= %s", [self.value]


class LTLookup(Lookup):
    """Less than lookup."""
    
    lookup_name = "lt"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for less than."""
        return f"{self.field_name} < %s", [self.value]


class LTELookup(Lookup):
    """Less than or equal lookup."""
    
    lookup_name = "lte"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for less than or equal."""
        return f"{self.field_name} <= %s", [self.value]


class InLookup(Lookup):
    """IN lookup."""
    
    lookup_name = "in"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for IN operator."""
        if not self.value:
            # Empty list - no matches
            return "1 = 0", []
        
        placeholders = ", ".join(["%s"] * len(self.value))
        return f"{self.field_name} IN ({placeholders})", list(self.value)


class RangeLookup(Lookup):
    """Range lookup (between)."""
    
    lookup_name = "range"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for BETWEEN operator."""
        start, end = self.value
        return f"{self.field_name} BETWEEN %s AND %s", [start, end]


class IsNullLookup(Lookup):
    """NULL check lookup."""
    
    lookup_name = "isnull"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for NULL check."""
        if self.value:
            return f"{self.field_name} IS NULL", []
        else:
            return f"{self.field_name} IS NOT NULL", []


class RegexLookup(Lookup):
    """Regex matching lookup."""
    
    lookup_name = "regex"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for regex matching."""
        if backend == "postgresql":
            return f"{self.field_name} ~ %s", [self.value]
        elif backend == "mysql":
            return f"{self.field_name} REGEXP %s", [self.value]
        else:
            # SQLite doesn't have native regex, would need custom function
            raise NotImplementedError(
                "Regex lookup not supported on SQLite without custom function"
            )


class IRegexLookup(Lookup):
    """Case-insensitive regex matching lookup."""
    
    lookup_name = "iregex"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for case-insensitive regex matching."""
        if backend == "postgresql":
            return f"{self.field_name} ~* %s", [self.value]
        elif backend == "mysql":
            # MySQL REGEXP is case-insensitive by default
            return f"{self.field_name} REGEXP %s", [self.value]
        else:
            raise NotImplementedError(
                "Regex lookup not supported on SQLite without custom function"
            )


# Advanced Lookups


class JSONContainsLookup(Lookup):
    """JSON field contains lookup."""
    
    lookup_name = "json_contains"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for JSON contains check."""
        if backend == "postgresql":
            return f"{self.field_name} @> %s", [self.value]
        elif backend == "mysql":
            # MySQL 5.7+
            return f"JSON_CONTAINS({self.field_name}, %s)", [self.value]
        else:
            # SQLite json1 extension
            return f"json_extract({self.field_name}, %s) IS NOT NULL", [self.value]


class ArrayContainsLookup(Lookup):
    """Array field contains lookup."""
    
    lookup_name = "array_contains"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for array contains check."""
        if backend == "postgresql":
            return f"%s = ANY({self.field_name})", [self.value]
        else:
            raise NotImplementedError("Array lookup only supported on PostgreSQL")


class DistanceLookup(Lookup):
    """Geographic distance lookup."""
    
    lookup_name = "distance_lt"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for distance comparison."""
        lat, lon, distance = self.value
        
        if backend == "postgresql":
            # Using PostGIS
            return (
                f"ST_Distance_Sphere({self.field_name}, "
                f"ST_MakePoint(%s, %s)) < %s",
                [lon, lat, distance]
            )
        else:
            raise NotImplementedError(
                "Distance lookup requires PostGIS on PostgreSQL"
            )


class FullTextSearchLookup(Lookup):
    """Full-text search lookup."""
    
    lookup_name = "search"
    
    def get_sql(self, backend: str = "sqlite") -> Tuple[str, List[Any]]:
        """Generate SQL for full-text search."""
        if backend == "postgresql":
            return f"{self.field_name} @@ plainto_tsquery(%s)", [self.value]
        elif backend == "mysql":
            return (
                f"MATCH({self.field_name}) AGAINST(%s IN BOOLEAN MODE)",
                [self.value]
            )
        else:
            # SQLite FTS5
            raise NotImplementedError("FTS lookup requires FTS5 module on SQLite")


# Lookup Registration


def register_lookup(lookup_class: Type[Lookup]) -> None:
    """Register a custom lookup globally.
    
    Args:
        lookup_class: Lookup class to register
        
    Raises:
        ValueError: If lookup_name not defined or already registered
    """
    if not lookup_class.lookup_name:
        raise ValueError(f"{lookup_class.__name__} must define lookup_name")
    
    if lookup_class.lookup_name in _lookups:
        raise ValueError(
            f"Lookup '{lookup_class.lookup_name}' already registered. "
            f"Use unregister_lookup() first if replacing."
        )
    
    _lookups[lookup_class.lookup_name] = lookup_class


def unregister_lookup(lookup_name: str) -> None:
    """Unregister a custom lookup.
    
    Args:
        lookup_name: Name of lookup to unregister
    """
    if lookup_name in _lookups:
        del _lookups[lookup_name]


def register_field_lookup(
    field_path: Tuple[str, str], lookup_class: Type[Lookup]
) -> None:
    """Register a lookup for a specific field.
    
    Args:
        field_path: Tuple of (model_name, field_name)
        lookup_class: Lookup class to register
    """
    if not lookup_class.lookup_name:
        raise ValueError(f"{lookup_class.__name__} must define lookup_name")
    
    _field_lookups[field_path] = lookup_class


def get_lookup(lookup_name: str) -> Optional[Type[Lookup]]:
    """Get a registered lookup by name.
    
    Args:
        lookup_name: Name of lookup
        
    Returns:
        Lookup class or None if not found
    """
    return _lookups.get(lookup_name)


def get_field_lookup(
    model_name: str, field_name: str, lookup_name: str
) -> Optional[Type[Lookup]]:
    """Get a field-specific lookup.
    
    Args:
        model_name: Name of model
        field_name: Name of field
        lookup_name: Name of lookup
        
    Returns:
        Lookup class or None if not found
    """
    key = (model_name, field_name)
    if key in _field_lookups:
        return _field_lookups.get(key)
    return _lookups.get(lookup_name)


def list_lookups() -> List[str]:
    """List all registered lookup names.
    
    Returns:
        List of lookup names
    """
    return sorted(_lookups.keys())


# Register standard lookups
_STANDARD_LOOKUPS = [
    ExactLookup,
    IExactLookup,
    ContainsLookup,
    IContainsLookup,
    StartsWith,
    IStartsWith,
    EndsWith,
    IEndsWith,
    GTLookup,
    GTELookup,
    LTLookup,
    LTELookup,
    InLookup,
    RangeLookup,
    IsNullLookup,
    RegexLookup,
    IRegexLookup,
    JSONContainsLookup,
    ArrayContainsLookup,
    DistanceLookup,
    FullTextSearchLookup,
]

for _lookup in _STANDARD_LOOKUPS:
    register_lookup(_lookup)


__all__ = [
    "Lookup",
    "ExactLookup",
    "IExactLookup",
    "ContainsLookup",
    "IContainsLookup",
    "StartsWith",
    "IStartsWith",
    "EndsWith",
    "IEndsWith",
    "GTLookup",
    "GTELookup",
    "LTLookup",
    "LTELookup",
    "InLookup",
    "RangeLookup",
    "IsNullLookup",
    "RegexLookup",
    "IRegexLookup",
    "JSONContainsLookup",
    "ArrayContainsLookup",
    "DistanceLookup",
    "FullTextSearchLookup",
    "register_lookup",
    "unregister_lookup",
    "register_field_lookup",
    "get_lookup",
    "get_field_lookup",
    "list_lookups",
]

"""Window function expressions for advanced SQL window operations.

Supports RANK, ROW_NUMBER, LAG, LEAD, FIRST_VALUE, LAST_VALUE, NTH_VALUE, 
and aggregate window functions with full frame specification support.

Example:
    from mikiorm.query.window import RowNumber, Rank, LAG

    # ROW_NUMBER with partition and order
    result = Employee.objects.annotate(
        row_num=RowNumber().partition_by('department_id').order_by('salary')
    )

    # LAG/LEAD for accessing previous/next rows
    result = Transaction.objects.annotate(
        prev_amount=LAG('amount', offset=1, default=0)
            .partition_by('account_id')
            .order_by('date'),
        next_amount=LEAD('amount', offset=1)
            .partition_by('account_id')
            .order_by('date')
    )

    # Aggregate window functions with frame
    result = Sale.objects.annotate(
        running_total=Sum('amount').over(
            partition_by='region',
            order_by='date',
            frame='ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW'
        )
    )
"""

from __future__ import annotations

from typing import Any, Optional, List


class FrameSpec:
    """Frame specification for window functions."""
    
    # Frame types
    ROWS = "ROWS"
    RANGE = "RANGE"
    GROUPS = "GROUPS"
    
    # Frame boundaries
    UNBOUNDED_PRECEDING = "UNBOUNDED PRECEDING"
    UNBOUNDED_FOLLOWING = "UNBOUNDED FOLLOWING"
    CURRENT_ROW = "CURRENT ROW"
    
    def __init__(self, frame_type: str = "ROWS", start: str = None, end: str = None):
        """Initialize frame specification.
        
        Args:
            frame_type: ROWS, RANGE, or GROUPS
            start: Start boundary (e.g., "UNBOUNDED PRECEDING", "1 PRECEDING")
            end: End boundary (e.g., "CURRENT ROW", "1 FOLLOWING")
        """
        self.frame_type = frame_type
        self.start = start or self.UNBOUNDED_PRECEDING
        self.end = end or self.CURRENT_ROW
    
    def to_sql(self) -> str:
        """Generate SQL frame specification."""
        return f"{self.frame_type} BETWEEN {self.start} AND {self.end}"
    
    @classmethod
    def unbounded(cls) -> FrameSpec:
        """Create unbounded frame (entire partition)."""
        return cls(start=cls.UNBOUNDED_PRECEDING, end=cls.UNBOUNDED_FOLLOWING)
    
    @classmethod
    def current_row_only(cls) -> FrameSpec:
        """Create frame for current row only."""
        return cls(start=cls.CURRENT_ROW, end=cls.CURRENT_ROW)


class WindowFunction:
    """Base class for window functions."""
    
    function_name: str = None
    
    def __init__(self, field_name: Optional[str] = None, **kwargs):
        """Initialize window function.
        
        Args:
            field_name: Field to apply function to (None for COUNT(*))
            **kwargs: Additional arguments (offset, default, etc.)
        """
        self.field_name = field_name
        self.kwargs = kwargs
        self._partition_by: List[str] = []
        self._order_by: List[str] = []
        self._frame: Optional[FrameSpec] = None
    
    def partition_by(self, *fields: str) -> WindowFunction:
        """Add PARTITION BY clause.
        
        Args:
            *fields: Field names to partition by
            
        Returns:
            Self for chaining
        """
        self._partition_by.extend(fields)
        return self
    
    def order_by(self, *fields: str) -> WindowFunction:
        """Add ORDER BY clause.
        
        Args:
            *fields: Field names to order by (use '-' prefix for DESC)
            
        Returns:
            Self for chaining
        """
        self._order_by.extend(fields)
        return self
    
    def frame(self, frame_spec: FrameSpec) -> WindowFunction:
        """Set frame specification.
        
        Args:
            frame_spec: Frame specification object
            
        Returns:
            Self for chaining
        """
        self._frame = frame_spec
        return self
    
    def get_partition_by_sql(self) -> str:
        """Get SQL for PARTITION BY clause."""
        if not self._partition_by:
            return ""
        fields = ", ".join(self._partition_by)
        return f"PARTITION BY {fields}"
    
    def get_order_by_sql(self) -> str:
        """Get SQL for ORDER BY clause."""
        if not self._order_by:
            return ""
        
        order_parts = []
        for field in self._order_by:
            if field.startswith("-"):
                order_parts.append(f"{field[1:]} DESC")
            else:
                order_parts.append(f"{field} ASC")
        
        return "ORDER BY " + ", ".join(order_parts)
    
    def get_frame_sql(self) -> str:
        """Get SQL for frame specification."""
        if not self._frame:
            return ""
        return self._frame.to_sql()
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for window function.
        
        Args:
            backend: Database backend (sqlite, postgresql, mysql)
            
        Returns:
            SQL string for window function
        """
        raise NotImplementedError
    
    def __repr__(self) -> str:
        """String representation."""
        parts = [self.function_name]
        if self.field_name:
            parts.append(f"({self.field_name})")
        if self._partition_by:
            parts.append(f" OVER (PARTITION BY {', '.join(self._partition_by)})")
        if self._order_by:
            parts.append(f" ORDER BY {', '.join(self._order_by)}")
        return "".join(parts)


# Ranking Functions


class RowNumber(WindowFunction):
    """ROW_NUMBER() window function.
    
    Assigns a unique sequential integer to each row within partition.
    """
    
    function_name = "ROW_NUMBER"
    
    def __init__(self):
        """Initialize ROW_NUMBER window function."""
        super().__init__(field_name=None)
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for ROW_NUMBER()."""
        parts = ["ROW_NUMBER() OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


class Rank(WindowFunction):
    """RANK() window function.
    
    Assigns rank with gaps for ties within partition.
    """
    
    function_name = "RANK"
    
    def __init__(self):
        """Initialize RANK window function."""
        super().__init__(field_name=None)
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for RANK()."""
        parts = ["RANK() OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


class DenseRank(WindowFunction):
    """DENSE_RANK() window function.
    
    Assigns rank without gaps for ties within partition.
    """
    
    function_name = "DENSE_RANK"
    
    def __init__(self):
        """Initialize DENSE_RANK window function."""
        super().__init__(field_name=None)
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for DENSE_RANK()."""
        parts = ["DENSE_RANK() OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


class NTile(WindowFunction):
    """NTILE(num_buckets) window function.
    
    Divides partition into specified number of buckets.
    """
    
    function_name = "NTILE"
    
    def __init__(self, num_buckets: int):
        """Initialize NTILE window function.
        
        Args:
            num_buckets: Number of buckets to divide partition into
        """
        super().__init__(field_name=None)
        self.num_buckets = num_buckets
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for NTILE(n)."""
        parts = [f"NTILE({self.num_buckets}) OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


# Offset Functions


class LAG(WindowFunction):
    """LAG(column, offset, default) window function.
    
    Access data from previous row within partition.
    """
    
    function_name = "LAG"
    
    def __init__(self, field_name: str, offset: int = 1, default: Any = None):
        """Initialize LAG window function.
        
        Args:
            field_name: Field to access from previous row
            offset: Number of rows to look back (default: 1)
            default: Default value if row doesn't exist (default: None)
        """
        super().__init__(field_name=field_name)
        self.offset = offset
        self.default = default
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for LAG()."""
        parts = [f"LAG({self.field_name}, {self.offset}"]
        
        if self.default is not None:
            parts.append(f", {repr(self.default)}")
        
        parts.append(") OVER (")
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


class LEAD(WindowFunction):
    """LEAD(column, offset, default) window function.
    
    Access data from next row within partition.
    """
    
    function_name = "LEAD"
    
    def __init__(self, field_name: str, offset: int = 1, default: Any = None):
        """Initialize LEAD window function.
        
        Args:
            field_name: Field to access from next row
            offset: Number of rows to look ahead (default: 1)
            default: Default value if row doesn't exist (default: None)
        """
        super().__init__(field_name=field_name)
        self.offset = offset
        self.default = default
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for LEAD()."""
        parts = [f"LEAD({self.field_name}, {self.offset}"]
        
        if self.default is not None:
            parts.append(f", {repr(self.default)}")
        
        parts.append(") OVER (")
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        parts.append(")")
        return "".join(parts)


class FirstValue(WindowFunction):
    """FIRST_VALUE(column) window function.
    
    Get first value in frame.
    """
    
    function_name = "FIRST_VALUE"
    
    def __init__(self, field_name: str):
        """Initialize FIRST_VALUE window function.
        
        Args:
            field_name: Field to get first value of
        """
        super().__init__(field_name=field_name)
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for FIRST_VALUE()."""
        parts = [f"FIRST_VALUE({self.field_name}) OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        frame_sql = self.get_frame_sql()
        if frame_sql:
            if partition_sql or order_sql:
                parts.append(" ")
            parts.append(frame_sql)
        
        parts.append(")")
        return "".join(parts)


class LastValue(WindowFunction):
    """LAST_VALUE(column) window function.
    
    Get last value in frame.
    """
    
    function_name = "LAST_VALUE"
    
    def __init__(self, field_name: str):
        """Initialize LAST_VALUE window function.
        
        Args:
            field_name: Field to get last value of
        """
        super().__init__(field_name=field_name)
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for LAST_VALUE()."""
        parts = [f"LAST_VALUE({self.field_name}) OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        frame_sql = self.get_frame_sql()
        if frame_sql:
            if partition_sql or order_sql:
                parts.append(" ")
            parts.append(frame_sql)
        
        parts.append(")")
        return "".join(parts)


class NthValue(WindowFunction):
    """NTH_VALUE(column, n) window function.
    
    Get nth value in frame.
    """
    
    function_name = "NTH_VALUE"
    
    def __init__(self, field_name: str, n: int):
        """Initialize NTH_VALUE window function.
        
        Args:
            field_name: Field to get nth value of
            n: Position in frame (1-based)
        """
        super().__init__(field_name=field_name)
        self.n = n
    
    def to_sql(self, backend: str = "sqlite") -> str:
        """Generate SQL for NTH_VALUE()."""
        parts = [f"NTH_VALUE({self.field_name}, {self.n}) OVER ("]
        
        partition_sql = self.get_partition_by_sql()
        if partition_sql:
            parts.append(partition_sql)
        
        order_sql = self.get_order_by_sql()
        if order_sql:
            if partition_sql:
                parts.append(" ")
            parts.append(order_sql)
        
        frame_sql = self.get_frame_sql()
        if frame_sql:
            if partition_sql or order_sql:
                parts.append(" ")
            parts.append(frame_sql)
        
        parts.append(")")
        return "".join(parts)


__all__ = [
    "FrameSpec",
    "WindowFunction",
    "RowNumber",
    "Rank",
    "DenseRank",
    "NTile",
    "LAG",
    "LEAD",
    "FirstValue",
    "LastValue",
    "NthValue",
]

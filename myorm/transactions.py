"""Transaction management and unit of work integration.

Provides :func:`atomic` and :func:`async_atomic` context managers, and
:func:`get_current_transaction` to access the active transaction manager.

Public API mirrors Django's atomic transaction handling with async support.
"""

from __future__ import annotations

# Re-export the public API from unit_of_work.transaction
from .unit_of_work.transaction import (
    atomic,
    async_atomic,
    get_current_transaction,
    TransactionManager,
)

__all__ = [
    "atomic",
    "async_atomic",
    "get_current_transaction",
    "TransactionManager",
]

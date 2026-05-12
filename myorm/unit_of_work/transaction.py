"""Transaction management and unit of work using context variables.

Provides atomic() sync context manager and async_atomic() async context manager.
Both integrate with the unit of work tracker to batch changes and enforce
referential integrity on commit.
"""

from __future__ import annotations

import contextvars
from typing import Any, Optional

from .tracker import UnitOfWorkTracker
from .commit import CommitManager, AsyncCommitManager

# Sync context variable for TransactionManager
_active_transaction = contextvars.ContextVar('myorm_active_transaction', default=None)


class TransactionManager:
    """Synchronous transaction manager with unit-of-work tracking."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.tracker = UnitOfWorkTracker()
        self.commit_manager = CommitManager(self.tracker)
        self._token: Optional[Any] = None

    def __enter__(self) -> Any:
        self._token = _active_transaction.set(self)
        if hasattr(self.connection, 'begin'):
            self.connection.begin()
        return self.connection

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        if exc_type:
            try:
                self.commit_manager.rollback(self.connection)
            finally:
                _active_transaction.reset(self._token)
            return
        try:
            self.commit_manager.commit(self.connection)
        finally:
            _active_transaction.reset(self._token)

    @classmethod
    def get_current(cls) -> Optional['TransactionManager']:
        """Return the currently active synchronous TransactionManager (or None)."""
        return _active_transaction.get()


# Async context variable for AsyncTransactionManager
_active_async_transaction = contextvars.ContextVar('myorm_active_async_transaction', default=None)


class AsyncTransactionManager:
    """Asynchronous transaction manager with unit-of-work tracking."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.tracker = UnitOfWorkTracker()
        self.commit_manager = AsyncCommitManager(self.tracker)
        self._token: Optional[Any] = None

    async def __aenter__(self) -> 'AsyncTransactionManager':
        if self.connection is None:
            from ..settings import async_connection_manager
            self.connection = await async_connection_manager.get_connection()
        self._token = _active_async_transaction.set(self)
        if hasattr(self.connection, 'begin'):
            await self.connection.begin()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        if exc_type:
            try:
                await self.commit_manager.rollback(self.connection)
            finally:
                _active_async_transaction.reset(self._token)
            return
        try:
            await self.commit_manager.commit(self.connection)
        finally:
            _active_async_transaction.reset(self._token)

    @classmethod
    def get_current(cls) -> Optional['AsyncTransactionManager']:
        """Return the currently active asynchronous TransactionManager (or None)."""
        return _active_async_transaction.get()


def atomic(connection: Optional[Any] = None) -> TransactionManager:
    """Return a synchronous atomic transaction context manager."""
    if connection is None:
        from ..settings import connection_manager
        connection = connection_manager.get_connection()
    return TransactionManager(connection)


def async_atomic(connection: Optional[Any] = None) -> AsyncTransactionManager:
    """Return an asynchronous atomic transaction context manager."""
    if connection is None:
        return AsyncTransactionManager(None)
    return AsyncTransactionManager(connection)


def get_current_transaction() -> TransactionManager | AsyncTransactionManager | None:
    """Return the currently active transaction manager (sync or async)."""
    tx = _active_transaction.get()
    if tx is not None:
        return tx
    return _active_async_transaction.get()

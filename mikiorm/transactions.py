"""Low-level ACID transaction management.

Provides Transaction and Savepoint context managers for direct transaction
control, complementing the higher-level atomic() / async_atomic() API.

Example (Sync)::

    from mikiorm.transactions import Transaction
    from mikiorm import settings

    with Transaction(using='default') as txn:
        conn = txn.connection
        conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
        # Commits on __exit__ success, rolls back on exception

    # Nested transactions use savepoints
    with Transaction() as txn:
        with Savepoint() as sp:
            conn = sp.connection
            conn.execute("INSERT INTO users (name) VALUES (?)", ("Bob",))
            sp.release()  # Release savepoint

Example (Async)::

    from mikiorm.transactions import Transaction
    from mikiorm import settings

    async with Transaction(using='default') as txn:
        conn = txn.connection
        await conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
        # Commits on __aexit__ success, rolls back on exception
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator, Optional

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Base exception for transaction-related errors."""
    pass


class Transaction:
    """Context manager for low-level synchronous transaction control.

    Acquires a connection from the pool, starts a transaction, and commits
    or rolls back on exit. Supports nested transactions via savepoints.

    Parameters
    ----------
    using : str
        Database alias (default: 'default')

    Attributes
    ----------
    connection : PooledConnection
        The database connection for this transaction

    Example::

        from mikiorm.transactions import Transaction

        with Transaction(using='default') as txn:
            conn = txn.connection
            conn.execute("INSERT INTO items (name) VALUES (?)", ("item1",))
            # Auto-commits on success

        # On exception, auto-rolls back
        try:
            with Transaction() as txn:
                txn.connection.execute(...)
                raise ValueError("simulate error")
        except ValueError:
            pass  # Transaction already rolled back
    """

    def __init__(self, using: str = "default") -> None:
        """Initialize transaction.

        Parameters
        ----------
        using : str
            Database alias to use (default: 'default')
        """
        self.using = using
        self.connection: Optional[Any] = None
        self._started = False

    def __enter__(self) -> "Transaction":
        """Start transaction.

        Acquires a connection from the pool and begins a transaction.

        Returns
        -------
        Transaction
            Self, for use in with-statement
        """
        from .conf.settings import connection_manager

        try:
            self.connection = connection_manager.get_connection(self.using)
            self.connection.begin()
            self._started = True
            logger.debug("Transaction started on database '%s'", self.using)
            return self
        except Exception as exc:
            logger.error("Failed to start transaction: %s", exc)
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
            raise TransactionError(f"Failed to start transaction: {exc}") from exc

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Commit or rollback transaction.

        Commits on success, rolls back if an exception occurred.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type if an exception occurred
        exc_val : BaseException | None
            Exception instance if an exception occurred
        exc_tb : TracebackType | None
            Traceback if an exception occurred
        """
        if not self.connection or not self._started:
            return

        try:
            if exc_type is not None:
                # Exception occurred - rollback
                logger.debug(
                    "Rolling back transaction due to %s: %s",
                    exc_type.__name__,
                    exc_val
                )
                self.connection.rollback()
            else:
                # Success - commit
                logger.debug("Committing transaction on database '%s'", self.using)
                self.connection.commit()
        except Exception as exc:
            logger.error("Error during transaction finalization: %s", exc)
            try:
                self.connection.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                self.connection.close()
            except Exception:
                pass
            self._started = False


class AsyncTransaction:
    """Context manager for low-level asynchronous transaction control.

    Async version of Transaction. Acquires a connection from the async pool,
    starts a transaction, and commits or rolls back on exit.

    Parameters
    ----------
    using : str
        Database alias (default: 'default')

    Attributes
    ----------
    connection : PooledAsyncConnection
        The async database connection for this transaction

    Example::

        from mikiorm.transactions import AsyncTransaction

        async with AsyncTransaction(using='default') as txn:
            conn = txn.connection
            await conn.execute("INSERT INTO items (name) VALUES (?)", ("item1",))
            # Auto-commits on success
    """

    def __init__(self, using: str = "default") -> None:
        """Initialize async transaction.

        Parameters
        ----------
        using : str
            Database alias to use (default: 'default')
        """
        self.using = using
        self.connection: Optional[Any] = None
        self._started = False

    async def __aenter__(self) -> "AsyncTransaction":
        """Start async transaction.

        Acquires a connection from the async pool and begins a transaction.

        Returns
        -------
        AsyncTransaction
            Self, for use in async with-statement
        """
        from .conf.settings import async_connection_manager

        try:
            self.connection = await async_connection_manager.get_connection(self.using)
            if hasattr(self.connection, 'begin'):
                await self.connection.begin()
            self._started = True
            logger.debug("Async transaction started on database '%s'", self.using)
            return self
        except Exception as exc:
            logger.error("Failed to start async transaction: %s", exc)
            if self.connection:
                try:
                    await self.connection.close()
                except Exception:
                    pass
            raise TransactionError(f"Failed to start async transaction: {exc}") from exc

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Commit or rollback async transaction.

        Commits on success, rolls back if an exception occurred.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type if an exception occurred
        exc_val : BaseException | None
            Exception instance if an exception occurred
        exc_tb : TracebackType | None
            Traceback if an exception occurred
        """
        if not self.connection or not self._started:
            return

        try:
            if exc_type is not None:
                # Exception occurred - rollback
                logger.debug(
                    "Rolling back async transaction due to %s: %s",
                    exc_type.__name__,
                    exc_val
                )
                if hasattr(self.connection, 'rollback'):
                    await self.connection.rollback()
            else:
                # Success - commit
                logger.debug("Committing async transaction on database '%s'", self.using)
                if hasattr(self.connection, 'commit'):
                    await self.connection.commit()
        except Exception as exc:
            logger.error("Error during async transaction finalization: %s", exc)
            try:
                if hasattr(self.connection, 'rollback'):
                    await self.connection.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                await self.connection.close()
            except Exception:
                pass
            self._started = False


class Savepoint:
    """Context manager for synchronous savepoint (nested transaction) control.

    Creates a savepoint within an existing transaction, allowing rollback to
    that point without affecting the outer transaction. Savepoints enable
    nested transaction semantics.

    Parameters
    ----------
    name : str | None
        Optional savepoint name. Auto-generated if None.
    connection : PooledConnection | None
        Connection to use. If None, uses current transaction connection.

    Example::

        from mikiorm.transactions import Transaction, Savepoint

        with Transaction() as txn:
            txn.connection.execute("INSERT INTO items VALUES (1, 'a')")

            try:
                with Savepoint("my_sp") as sp:
                    sp.connection.execute("INSERT INTO items VALUES (2, 'b')")
                    raise RuntimeError("oops")
            except RuntimeError:
                pass  # Rolled back to savepoint, item 2 not inserted

            # Item 1 still exists when transaction commits
    """

    def __init__(
        self,
        name: Optional[str] = None,
        connection: Optional[Any] = None,
    ) -> None:
        """Initialize savepoint.

        Parameters
        ----------
        name : str | None
            Optional savepoint name (auto-generated if None)
        connection : PooledConnection | None
            Connection to use (auto-detected from transaction if None)
        """
        self.name = name or f"sp_{uuid.uuid4().hex[:12]}"
        self.connection = connection
        self._released = False

    def __enter__(self) -> "Savepoint":
        """Create savepoint.

        Creates a savepoint in the current transaction. If no connection is
        provided, attempts to use the active transaction connection.

        Returns
        -------
        Savepoint
            Self, for use in with-statement
        """
        if self.connection is None:
            from .unit_of_work.transaction import TransactionManager
            txn = TransactionManager.get_current()
            if txn is None:
                raise TransactionError(
                    "No active transaction. Use Savepoint inside a Transaction block."
                )
            self.connection = txn.connection

        try:
            # Create savepoint using SAVEPOINT SQL
            sql = f"SAVEPOINT {self.name}"
            self.connection.execute(sql, ())
            logger.debug("Savepoint '%s' created", self.name)
            return self
        except Exception as exc:
            logger.error("Failed to create savepoint '%s': %s", self.name, exc)
            raise TransactionError(f"Failed to create savepoint '{self.name}': {exc}") from exc

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Rollback or release savepoint.

        Rolls back to savepoint if an exception occurred, otherwise releases it.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type if an exception occurred
        exc_val : BaseException | None
            Exception instance if an exception occurred
        exc_tb : TracebackType | None
            Traceback if an exception occurred
        """
        if not self.connection or self._released:
            return

        try:
            if exc_type is not None:
                # Exception occurred - rollback to savepoint
                sql = f"ROLLBACK TO SAVEPOINT {self.name}"
                logger.debug("Rolling back to savepoint '%s'", self.name)
                self.connection.execute(sql, ())
            else:
                # Success - release savepoint
                sql = f"RELEASE SAVEPOINT {self.name}"
                logger.debug("Releasing savepoint '%s'", self.name)
                self.connection.execute(sql, ())
                self._released = True
        except Exception as exc:
            logger.error("Error handling savepoint '%s': %s", self.name, exc)
            raise

    def release(self) -> None:
        """Explicitly release the savepoint.

        Releases the savepoint immediately, committing any pending changes
        within the savepoint scope to the parent transaction.
        """
        if self.connection and not self._released:
            try:
                sql = f"RELEASE SAVEPOINT {self.name}"
                self.connection.execute(sql, ())
                self._released = True
                logger.debug("Explicitly released savepoint '%s'", self.name)
            except Exception as exc:
                logger.error("Failed to release savepoint '%s': %s", self.name, exc)
                raise TransactionError(
                    f"Failed to release savepoint '{self.name}': {exc}"
                ) from exc

    def rollback(self) -> None:
        """Explicitly rollback to the savepoint.

        Rolls back to this savepoint, reverting any changes made after its
        creation but within the parent transaction.
        """
        if self.connection:
            try:
                sql = f"ROLLBACK TO SAVEPOINT {self.name}"
                self.connection.execute(sql, ())
                self._released = True
                logger.debug("Explicitly rolled back to savepoint '%s'", self.name)
            except Exception as exc:
                logger.error("Failed to rollback savepoint '%s': %s", self.name, exc)
                raise TransactionError(
                    f"Failed to rollback savepoint '{self.name}': {exc}"
                ) from exc


class AsyncSavepoint:
    """Context manager for asynchronous savepoint (nested transaction) control.

    Async version of Savepoint. Creates a savepoint within an existing
    async transaction for nested transaction semantics.

    Parameters
    ----------
    name : str | None
        Optional savepoint name. Auto-generated if None.
    connection : PooledAsyncConnection | None
        Async connection to use. If None, uses current async transaction.

    Example::

        from mikiorm.transactions import AsyncTransaction, AsyncSavepoint

        async with AsyncTransaction() as txn:
            await txn.connection.execute("INSERT INTO items VALUES (1, 'a')")

            try:
                async with AsyncSavepoint("my_sp") as sp:
                    await sp.connection.execute("INSERT INTO items VALUES (2, 'b')")
                    raise RuntimeError("oops")
            except RuntimeError:
                pass  # Rolled back to savepoint, item 2 not inserted
    """

    def __init__(
        self,
        name: Optional[str] = None,
        connection: Optional[Any] = None,
    ) -> None:
        """Initialize async savepoint.

        Parameters
        ----------
        name : str | None
            Optional savepoint name (auto-generated if None)
        connection : PooledAsyncConnection | None
            Async connection to use (auto-detected if None)
        """
        self.name = name or f"sp_{uuid.uuid4().hex[:12]}"
        self.connection = connection
        self._released = False

    async def __aenter__(self) -> "AsyncSavepoint":
        """Create async savepoint.

        Creates a savepoint in the current async transaction.

        Returns
        -------
        AsyncSavepoint
            Self, for use in async with-statement
        """
        if self.connection is None:
            from .unit_of_work.transaction import AsyncTransactionManager
            txn = AsyncTransactionManager.get_current()
            if txn is None:
                raise TransactionError(
                    "No active async transaction. Use AsyncSavepoint inside AsyncTransaction."
                )
            self.connection = txn.connection

        try:
            sql = f"SAVEPOINT {self.name}"
            await self.connection.execute(sql, ())
            logger.debug("Async savepoint '%s' created", self.name)
            return self
        except Exception as exc:
            logger.error("Failed to create async savepoint '%s': %s", self.name, exc)
            raise TransactionError(
                f"Failed to create async savepoint '{self.name}': {exc}"
            ) from exc

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Rollback or release async savepoint.

        Rolls back to savepoint if an exception occurred, otherwise releases it.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type if an exception occurred
        exc_val : BaseException | None
            Exception instance if an exception occurred
        exc_tb : TracebackType | None
            Traceback if an exception occurred
        """
        if not self.connection or self._released:
            return

        try:
            if exc_type is not None:
                sql = f"ROLLBACK TO SAVEPOINT {self.name}"
                logger.debug("Rolling back to async savepoint '%s'", self.name)
                await self.connection.execute(sql, ())
            else:
                sql = f"RELEASE SAVEPOINT {self.name}"
                logger.debug("Releasing async savepoint '%s'", self.name)
                await self.connection.execute(sql, ())
                self._released = True
        except Exception as exc:
            logger.error("Error handling async savepoint '%s': %s", self.name, exc)
            raise

    async def release(self) -> None:
        """Explicitly release the async savepoint.

        Releases the savepoint immediately, committing pending changes
        within its scope to the parent transaction.
        """
        if self.connection and not self._released:
            try:
                sql = f"RELEASE SAVEPOINT {self.name}"
                await self.connection.execute(sql, ())
                self._released = True
                logger.debug("Explicitly released async savepoint '%s'", self.name)
            except Exception as exc:
                logger.error("Failed to release async savepoint '%s': %s", self.name, exc)
                raise TransactionError(
                    f"Failed to release async savepoint '{self.name}': {exc}"
                ) from exc

    async def rollback(self) -> None:
        """Explicitly rollback to the async savepoint.

        Rolls back to this savepoint, reverting changes made after its
        creation but within the parent transaction.
        """
        if self.connection:
            try:
                sql = f"ROLLBACK TO SAVEPOINT {self.name}"
                await self.connection.execute(sql, ())
                self._released = True
                logger.debug("Explicitly rolled back to async savepoint '%s'", self.name)
            except Exception as exc:
                logger.error("Failed to rollback async savepoint '%s': %s", self.name, exc)
                raise TransactionError(
                    f"Failed to rollback async savepoint '{self.name}': {exc}"
                ) from exc


__all__ = [
    "Transaction",
    "AsyncTransaction",
    "Savepoint",
    "AsyncSavepoint",
    "TransactionError",
]

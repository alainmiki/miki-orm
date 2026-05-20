"""Thread-safe sync pool and asyncio-aware async pool.

Both pools share the same surface area: ``acquire()``, ``close()``, ``size``,
and they yield ``PooledConnection`` / ``PooledAsyncConnection`` wrappers that
act as context managers.  Lifecycle features:

* Bounded ``min_size`` / ``max_size`` with lazy growth.
* ``timeout`` for blocking acquire.
* Optional ``max_lifetime`` and ``max_uses`` based recycling.
* Optional ``pre_ping`` validation on checkout.
* Connections returned to the pool via context-manager exit (or
  ``.release()`` / ``.close()``); call ``.destroy()`` to actually tear down.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections import deque
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional

if TYPE_CHECKING:
    from .adapter import BaseAdapter, BaseAsyncAdapter

logger = logging.getLogger(__name__)


class _PoolEntry:
    """Internal accounting record for a pooled connection."""

    __slots__ = ("conn", "created_at", "uses")

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.created_at = time.monotonic()
        self.uses = 0


# ---------------------------------------------------------------------------
# Pooled connection wrappers
# ---------------------------------------------------------------------------


class PooledConnection(AbstractContextManager):
    """Wrapper around a borrowed sync connection that proxies the API.

    ``close()`` returns the connection to the pool (pool semantics).
    ``destroy()`` actually tears it down.
    """

    def __init__(self, pool: "SyncConnectionPool", entry: _PoolEntry) -> None:
        self._pool = pool
        self._entry = entry
        self._released = False

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return self._entry.conn.execute(sql, params)

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        return self._entry.conn.fetchall(sql, params)

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
        return self._entry.conn.fetchone(sql, params)

    def commit(self) -> None:
        self._entry.conn.commit()

    def rollback(self) -> None:
        self._entry.conn.rollback()

    def begin(self) -> None:
        if hasattr(self._entry.conn, "begin"):
            self._entry.conn.begin()

    @property
    def param_placeholder(self) -> str:
        return getattr(self._entry.conn, "param_placeholder", "?")

    @property
    def raw(self) -> Any:
        return self._entry.conn

    def is_valid(self, timeout: float = 5.0) -> bool:
        """Check if the underlying connection is valid."""
        conn = self._entry.conn
        if hasattr(conn, "is_valid"):
            return conn.is_valid(timeout)
        if hasattr(conn, "ping"):
            try:
                conn.ping()
                return True
            except Exception:
                return False
        return True  # Assume valid if no ping method

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._pool._release(self._entry)

    def close(self) -> None:
        """Return the connection to the pool."""
        self.release()

    def destroy(self) -> None:
        if not self._released:
            self._released = True
            self._pool._discard(self._entry)

    def __enter__(self) -> "PooledConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            try:
                self.rollback()
            except Exception:
                pass
            self.destroy()
        else:
            self.release()


class PooledAsyncConnection(AbstractAsyncContextManager):
    """Async analogue of :class:`PooledConnection`."""

    def __init__(self, pool: "AsyncConnectionPool", entry: _PoolEntry) -> None:
        self._pool = pool
        self._entry = entry
        self._released = False

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return await self._entry.conn.execute(sql, params)

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        return await self._entry.conn.fetchall(sql, params)

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> tuple[Any, ...] | None:
        return await self._entry.conn.fetchone(sql, params)

    async def commit(self) -> None:
        await self._entry.conn.commit()

    async def rollback(self) -> None:
        await self._entry.conn.rollback()

    async def begin(self) -> None:
        if hasattr(self._entry.conn, "begin"):
            await self._entry.conn.begin()

    @property
    def param_placeholder(self) -> str:
        return getattr(self._entry.conn, "param_placeholder", "?")

    @property
    def raw(self) -> Any:
        return self._entry.conn

    async def release(self) -> None:
        if not self._released:
            self._released = True
            await self._pool._release(self._entry)

    async def close(self) -> None:
        await self.release()

    async def destroy(self) -> None:
        if not self._released:
            self._released = True
            await self._pool._discard(self._entry)

    async def __aenter__(self) -> "PooledAsyncConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            try:
                await self.rollback()
            except Exception:
                pass
            await self.destroy()
        else:
            await self.release()


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------


class ConnectionState(Enum):
    """Connection health states."""

    HEALTHY = "healthy"
    IDLE = "idle"
    IN_USE = "in_use"
    STALE = "stale"
    ERROR = "error"


@dataclass
class PoolStatistics:
    """Statistics for connection pool monitoring."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    queued_requests: int = 0
    total_acquisitions: int = 0
    total_releases: int = 0
    total_timeouts: int = 0
    total_errors: int = 0
    avg_wait_time_ms: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def uptime_seconds(self) -> float:
        """Get pool uptime in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    def utilization_percent(self) -> float:
        """Get pool utilization percentage."""
        if self.total_connections == 0:
            return 0.0
        return (self.active_connections / self.total_connections) * 100


@dataclass
class ConnectionMetadata:
    """Metadata about a pooled connection."""

    connection_id: str
    state: ConnectionState
    acquired_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    query_count: int = 0

    def is_stale(self, timeout_seconds: int = 900) -> bool:
        """Check if connection is stale (idle too long)."""
        if self.last_used_at is None:
            return False
        idle_seconds = (datetime.now() - self.last_used_at).total_seconds()
        return idle_seconds > timeout_seconds

    def acquire_duration_ms(self) -> Optional[float]:
        if self.acquired_at is None or self.released_at is None:
            return None
        return (self.released_at - self.acquired_at).total_seconds() * 1000

    def idle_duration_seconds(self) -> float:
        if self.state != ConnectionState.IDLE:
            return 0.0
        if self.released_at is None:
            return 0.0
        return (datetime.now() - self.released_at).total_seconds()


class DeadlockRetryPolicy:
    """Deadlock detection and retry policy."""

    MAX_RETRIES = 3
    INITIAL_BACKOFF_MS = 100
    MAX_BACKOFF_MS = 400
    BACKOFF_MULTIPLIER = 2
    DEADLOCK_ERRORS = {
        "OperationalError",
        "DatabaseError",
        "IntegrityError",
        "1213",
        "40P01",
    }

    @staticmethod
    def is_deadlock_error(error: Exception) -> bool:
        error_str = str(error).lower()
        return any(
            key.lower() in error_str for key in DeadlockRetryPolicy.DEADLOCK_ERRORS
        )

    @staticmethod
    def get_backoff_ms(attempt: int) -> int:
        backoff = DeadlockRetryPolicy.INITIAL_BACKOFF_MS
        for _ in range(attempt - 1):
            backoff = min(
                backoff * DeadlockRetryPolicy.BACKOFF_MULTIPLIER,
                DeadlockRetryPolicy.MAX_BACKOFF_MS,
            )
        return backoff


class _BasePool:
    """Common config validation/expiry logic shared between sync and async pools."""

    def __init__(
        self,
        *,
        min_size: int,
        max_size: int,
        timeout: float,
        max_lifetime: float,
        max_uses: int,
        pre_ping: bool,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if min_size < 0 or min_size > max_size:
            raise ValueError("0 <= min_size <= max_size required")
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout
        self.max_lifetime = max_lifetime
        self.max_uses = max_uses
        self.pre_ping = pre_ping
        self._total = 0
        self._closed = False

    def _expired(self, entry: _PoolEntry) -> bool:
        if self.max_uses and entry.uses >= self.max_uses:
            return True
        if self.max_lifetime and (time.monotonic() - entry.created_at) >= self.max_lifetime:
            return True
        return False

    @property
    def size(self) -> int:
        return self._total


class SyncConnectionPool(_BasePool):
    """Bounded, thread-safe pool of synchronous connections."""

    def __init__(
        self,
        adapter: "BaseAdapter",
        config: dict[str, Any],
        *,
        min_size: int = 1,
        max_size: int = 5,
        timeout: float = 30.0,
        max_lifetime: float = 0.0,
        max_uses: int = 0,
        pre_ping: bool = False,
    ) -> None:
        super().__init__(
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_lifetime=max_lifetime,
            max_uses=max_uses,
            pre_ping=pre_ping,
        )
        self._adapter = adapter
        self._config = config
        self._idle: queue.LifoQueue[_PoolEntry] = queue.LifoQueue(maxsize=max_size)
        self._lock = threading.Lock()
        self._prefill()

    def _prefill(self) -> None:
        for _ in range(self.min_size):
            try:
                self._idle.put_nowait(self._make_entry())
            except Exception as exc:
                logger.warning("Pool prefill failed: %s", exc)
                break

    def _make_entry(self) -> _PoolEntry:
        conn = self._adapter.connect(self._config)
        with self._lock:
            self._total += 1
        return _PoolEntry(conn)

    def acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        if self._closed:
            raise RuntimeError("Pool is closed")
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)

        while True:
            try:
                entry = self._idle.get_nowait()
            except queue.Empty:
                entry = None

            if entry is None:
                with self._lock:
                    if self._total < self.max_size:
                        entry = self._make_entry()
                if entry is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Timed out acquiring a connection after {self.timeout}s"
                        )
                    try:
                        entry = self._idle.get(timeout=remaining)
                    except queue.Empty:
                        continue

            if self._expired(entry):
                self._discard(entry)
                continue
            if self.pre_ping and not entry.conn.is_valid():
                self._discard(entry)
                continue

            entry.uses += 1
            return PooledConnection(self, entry)

    def _release(self, entry: _PoolEntry) -> None:
        if self._closed or self._expired(entry):
            self._discard(entry)
            return
        try:
            self._idle.put_nowait(entry)
        except queue.Full:
            self._discard(entry)

    def _discard(self, entry: _PoolEntry) -> None:
        try:
            entry.conn.close()
        except Exception:
            pass
        with self._lock:
            self._total = max(0, self._total - 1)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        while True:
            try:
                entry = self._idle.get_nowait()
            except queue.Empty:
                break
            self._discard(entry)

    def __enter__(self) -> "SyncConnectionPool":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


class AsyncConnectionPool(_BasePool):
    """Asyncio-aware bounded pool mirroring :class:`SyncConnectionPool`."""

    def __init__(
        self,
        adapter: "BaseAsyncAdapter",
        config: dict[str, Any],
        *,
        min_size: int = 1,
        max_size: int = 5,
        timeout: float = 30.0,
        max_lifetime: float = 0.0,
        max_uses: int = 0,
        pre_ping: bool = False,
    ) -> None:
        super().__init__(
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_lifetime=max_lifetime,
            max_uses=max_uses,
            pre_ping=pre_ping,
        )
        self._adapter = adapter
        self._config = config
        self._idle: asyncio.LifoQueue[_PoolEntry] = asyncio.LifoQueue(maxsize=max_size)
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        for _ in range(self.min_size):
            try:
                self._idle.put_nowait(await self._make_entry())
            except Exception as exc:
                logger.warning("Async pool prefill failed: %s", exc)
                break

    async def _make_entry(self) -> _PoolEntry:
        conn = await self._adapter.connect(self._config)
        async with self._lock:
            self._total += 1
        return _PoolEntry(conn)

    async def acquire(self, timeout: Optional[float] = None) -> PooledAsyncConnection:
        if self._closed:
            raise RuntimeError("Pool is closed")
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)

        while True:
            entry: Optional[_PoolEntry] = None
            try:
                entry = self._idle.get_nowait()
            except asyncio.QueueEmpty:
                pass

            if entry is None:
                async with self._lock:
                    if self._total < self.max_size:
                        entry = await self._make_entry()
            if entry is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError(
                        f"Timed out acquiring a connection after {self.timeout}s"
                    )
                try:
                    entry = await asyncio.wait_for(self._idle.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    continue

            if self._expired(entry):
                await self._discard(entry)
                continue
            if self.pre_ping and not await entry.conn.is_valid():
                await self._discard(entry)
                continue

            entry.uses += 1
            return PooledAsyncConnection(self, entry)

    async def _release(self, entry: _PoolEntry) -> None:
        if self._closed or self._expired(entry):
            await self._discard(entry)
            return
        try:
            self._idle.put_nowait(entry)
        except asyncio.QueueFull:
            await self._discard(entry)

    async def _discard(self, entry: _PoolEntry) -> None:
        try:
            await entry.conn.close()
        except Exception:
            pass
        async with self._lock:
            self._total = max(0, self._total - 1)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
        while True:
            try:
                entry = self._idle.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._discard(entry)

    async def __aenter__(self) -> "AsyncConnectionPool":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()


class ConnectionPool:
    """Enhanced connection pool with concurrency management.

    Features:
    - Connection wait queue with timeout
    - Stale connection detection and recycling
    - Deadlock retry logic
    - Per-query timeout enforcement
    - Connection health monitoring
    - Statistics tracking
    """

    def __init__(
        self,
        connection_factory: Callable,
        min_size: int = 1,
        max_size: int = 20,
        timeout: float = 30.0,
        idle_timeout: int = 900,
        health_check_interval: int = 300,
    ):
        self.connection_factory = connection_factory
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.health_check_interval = health_check_interval

        self._available: deque = deque()
        self._in_use: Dict[int, Any] = {}
        self._metadata: Dict[int, ConnectionMetadata] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stats = PoolStatistics()
        self._last_health_check = datetime.now()

    def acquire(self, timeout: Optional[float] = None) -> Any:
        timeout = timeout or self.timeout
        start_time = time.time()

        with self._condition:
            self._cleanup_stale_connections()

            while self._available and time.time() - start_time < timeout:
                conn = self._available.popleft()
                conn_id = id(conn)

                if self._is_connection_healthy(conn):
                    self._in_use[conn_id] = conn
                    meta = self._metadata[conn_id]
                    meta.state = ConnectionState.IN_USE
                    meta.acquired_at = datetime.now()
                    self._stats.total_acquisitions += 1
                    self._stats.active_connections = len(self._in_use)
                    return conn

                self._metadata[conn_id].state = ConnectionState.ERROR
                self._close_connection(conn)

            if len(self._in_use) + len(self._available) < self.max_size:
                try:
                    conn = self.connection_factory()
                    conn_id = id(conn)
                    self._in_use[conn_id] = conn
                    self._metadata[conn_id] = ConnectionMetadata(
                        connection_id=str(conn_id),
                        state=ConnectionState.IN_USE,
                        acquired_at=datetime.now(),
                    )
                    self._stats.total_connections += 1
                    self._stats.total_acquisitions += 1
                    self._stats.active_connections = len(self._in_use)
                    return conn
                except Exception as e:
                    logger.error("Failed to create new connection: %s", e)
                    raise

            remaining_timeout = timeout - (time.time() - start_time)
            while remaining_timeout > 0:
                logger.warning(
                    "Connection pool exhausted. Waiting %.1fs for available connection.",
                    remaining_timeout,
                )
                self._stats.queued_requests += 1
                self._condition.wait(remaining_timeout)
                self._stats.queued_requests -= 1

                if self._available:
                    return self.acquire(timeout=remaining_timeout)
                if len(self._in_use) + len(self._available) < self.max_size:
                    return self.acquire(timeout=remaining_timeout)

                remaining_timeout = timeout - (time.time() - start_time)

            self._stats.total_timeouts += 1
            raise TimeoutError(
                f"Could not acquire connection within {timeout}s. "
                f"Pool: {len(self._in_use)} in use, {len(self._available)} available, "
                f"limit: {self.max_size}"
            )

    def release(self, connection: Any) -> None:
        conn_id = id(connection)

        with self._condition:
            if conn_id in self._in_use:
                del self._in_use[conn_id]

                if self._is_connection_healthy(connection):
                    meta = self._metadata[conn_id]
                    meta.state = ConnectionState.IDLE
                    meta.released_at = datetime.now()
                    meta.last_used_at = datetime.now()
                    meta.query_count += 1
                    self._available.append(connection)
                else:
                    meta = self._metadata[conn_id]
                    meta.state = ConnectionState.ERROR
                    self._close_connection(connection)

                self._stats.total_releases += 1
                self._stats.active_connections = len(self._in_use)
                self._condition.notify_all()

    def _cleanup_stale_connections(self) -> None:
        stale_conns = []
        for conn in list(self._available):
            conn_id = id(conn)
            meta = self._metadata.get(conn_id)
            if meta and meta.is_stale(self.idle_timeout):
                stale_conns.append(conn)

        for conn in stale_conns:
            self._available.remove(conn)
            self._close_connection(conn)

    def _is_connection_healthy(self, connection: Any) -> bool:
        try:
            if hasattr(connection, "ping"):
                connection.ping()
                return True
            return True
        except Exception:
            return False

    def _close_connection(self, connection: Any) -> None:
        try:
            if hasattr(connection, "close"):
                connection.close()
        except Exception as e:
            logger.warning("Error closing connection: %s", e)

    def get_statistics(self) -> PoolStatistics:
        with self._lock:
            self._stats.total_connections = len(self._in_use) + len(self._available)
            self._stats.active_connections = len(self._in_use)
            self._stats.idle_connections = len(self._available)
            self._stats.last_updated = datetime.now()
            return self._stats

    def close_all(self) -> None:
        with self._lock:
            for conn in self._available:
                self._close_connection(conn)
            for conn in self._in_use.values():
                self._close_connection(conn)

            self._available.clear()
            self._in_use.clear()
            self._metadata.clear()


class QueryExecutor:
    """Query execution with deadlock retry and timeout handling."""

    def __init__(self, connection_pool: ConnectionPool) -> None:
        self.pool = connection_pool

    def execute(
        self,
        query_func: Callable,
        *args,
        timeout: Optional[float] = None,
        retry_on_deadlock: bool = True,
        **kwargs,
    ) -> Any:
        last_error = None

        for attempt in range(1, DeadlockRetryPolicy.MAX_RETRIES + 1):
            try:
                conn = self.pool.acquire(timeout)
                try:
                    return query_func(conn, *args, **kwargs)
                finally:
                    self.pool.release(conn)
            except TimeoutError:
                raise
            except Exception as e:
                last_error = e
                if retry_on_deadlock and DeadlockRetryPolicy.is_deadlock_error(e):
                    if attempt < DeadlockRetryPolicy.MAX_RETRIES:
                        backoff_ms = DeadlockRetryPolicy.get_backoff_ms(attempt)
                        logger.warning(
                            "Deadlock detected (attempt %d). Retrying in %dms...",
                            attempt,
                            backoff_ms,
                        )
                        time.sleep(backoff_ms / 1000.0)
                        continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Query execution failed")


__all__ = [
    "AsyncConnectionPool",
    "PooledAsyncConnection",
    "PooledConnection",
    "SyncConnectionPool",
    "ConnectionState",
    "PoolStatistics",
    "ConnectionMetadata",
    "DeadlockRetryPolicy",
    "ConnectionPool",
    "QueryExecutor",
]

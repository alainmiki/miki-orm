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
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import TYPE_CHECKING, Any, Iterable, Optional

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


__all__ = [
    "AsyncConnectionPool",
    "PooledAsyncConnection",
    "PooledConnection",
    "SyncConnectionPool",
]

"""Abstract connection interfaces and adapters."""

from __future__ import annotations

import asyncio
import queue
import ssl
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Tuple

from ..settings import settings

def get_param_placeholder() -> str:
    """Return the appropriate SQL parameter placeholder for the configured database."""
    db_config = settings.get_database("default")
    if db_config.engine == "postgresql" or db_config.engine == "mysql":
        return "%s"
    return "?"



class BaseConnection(ABC):
    """Base interface for a database connection."""

    @property
    @abstractmethod
    def param_placeholder(self) -> str:
        """Return the parameter placeholder style for this database backend."""

    @abstractmethod
    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        raise NotImplementedError

    @abstractmethod
    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class BaseAdapter(ABC):
    """Abstract adapter for connection factories and pools."""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> BaseConnection:
        pass

    @abstractmethod
    def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> Any:
        pass

    def validate_connection(self, conn: BaseConnection) -> bool:
        try:
            row = conn.fetchone("SELECT 1", ())
            return bool(row)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Asynchronous interfaces
# ---------------------------------------------------------------------------

class BaseAsyncConnection(ABC):
    """Base interface for an async database connection."""

    @property
    @abstractmethod
    def param_placeholder(self) -> str:
        """Return the parameter placeholder style for this database backend."""

    @abstractmethod
    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        raise NotImplementedError

    @abstractmethod
    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class BaseAsyncAdapter(ABC):
    """Abstract async adapter for connection factories and pools."""

    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> BaseAsyncConnection:
        pass

    @abstractmethod
    async def create_pool(self, config: Dict[str, Any], pool_config: Dict[str, Any] | None = None) -> Any:
        pass


class SyncConnectionPool:
    """Simple thread-safe connection pool for sync adapters."""

    def __init__(
        self,
        adapter: "BaseAdapter",
        config: Dict[str, Any],
        min_size: int = 1,
        max_size: int = 5,
        timeout: int = 30,
    ) -> None:
        self.adapter = adapter
        self.config = config
        self.max_size = max_size
        self.timeout = timeout
        self._lock = threading.Lock()
        self._pool: queue.Queue[BaseConnection] = queue.Queue(maxsize=max_size)
        self._created = 0

        for _ in range(min_size):
            self._pool.put(self._create_connection())

    def _create_connection(self) -> BaseConnection:
        conn = self.adapter.connect(self.config)
        self._created += 1
        return conn

    def acquire(self) -> "PooledConnection":
        with self._lock:
            if not self._pool.empty():
                conn = self._pool.get_nowait()
                return PooledConnection(self, conn)
            if self._created < self.max_size:
                return PooledConnection(self, self._create_connection())

        try:
            conn = self._pool.get(timeout=self.timeout)
            return PooledConnection(self, conn)
        except queue.Empty as exc:
            raise TimeoutError("Timed out waiting for a connection from the pool") from exc

    def release(self, conn: BaseConnection) -> None:
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            if hasattr(conn, "close"):
                conn.close()

    def close(self) -> None:
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            if hasattr(conn, "close"):
                conn.close()


class PooledConnection(BaseConnection):
    """Connection wrapper that returns connections to the pool on close."""

    def __init__(self, pool: SyncConnectionPool, conn: BaseConnection) -> None:
        self._pool = pool
        self._conn = conn

    def __enter__(self) -> "PooledConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def param_placeholder(self) -> str:
        return self._conn.param_placeholder

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return self._conn.execute(sql, params)

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        return self._conn.fetchall(sql, params)

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        return self._conn.fetchone(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._pool.release(self._conn)


class AsyncConnectionPool:
    """Simple async connection pool for async adapters."""

    def __init__(
        self,
        adapter: "BaseAsyncAdapter",
        config: Dict[str, Any],
        min_size: int = 1,
        max_size: int = 5,
        timeout: int = 30,
    ) -> None:
        self.adapter = adapter
        self.config = config
        self.max_size = max_size
        self.timeout = timeout
        self._queue: asyncio.Queue[BaseAsyncConnection] = asyncio.Queue(maxsize=max_size)
        self._created = 0
        self._lock = asyncio.Lock()

    async def _create_connection(self) -> BaseAsyncConnection:
        conn = await self.adapter.connect(self.config)
        self._created += 1
        return conn

    async def acquire(self) -> "PooledAsyncConnection":
        async with self._lock:
            if not self._queue.empty():
                conn = self._queue.get_nowait()
                return PooledAsyncConnection(self, conn)
            if self._created < self.max_size:
                return PooledAsyncConnection(self, await self._create_connection())

        try:
            conn = await asyncio.wait_for(self._queue.get(), timeout=self.timeout)
            return PooledAsyncConnection(self, conn)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timed out waiting for an async connection from the pool") from exc

    async def release(self, conn: BaseAsyncConnection) -> None:
        try:
            self._queue.put_nowait(conn)
        except asyncio.QueueFull:
            await conn.close()

    async def close(self) -> None:
        while not self._queue.empty():
            conn = self._queue.get_nowait()
            await conn.close()


class PooledAsyncConnection(BaseAsyncConnection):
    """Async connection wrapper that returns connections to the pool on close."""

    def __init__(self, pool: AsyncConnectionPool, conn: BaseAsyncConnection) -> None:
        self._pool = pool
        self._conn = conn

    async def __aenter__(self) -> "PooledAsyncConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @property
    def param_placeholder(self) -> str:
        return self._conn.param_placeholder

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return await self._conn.execute(sql, params)

    async def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[Tuple[Any, ...]]:
        return await self._conn.fetchall(sql, params)

    async def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Tuple[Any, ...] | None:
        return await self._conn.fetchone(sql, params)

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def close(self) -> None:
        await self._pool.release(self._conn)

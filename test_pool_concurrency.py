"""Tests for connection pool and concurrency management.

Validates:
- Pool initialization and configuration
- Connection acquisition and release
- Stale connection detection and cleanup
- Deadlock retry policy
- Query executor with retry logic
- Connection health monitoring
- Pool statistics tracking
- Thread safety
"""

import pytest
import threading
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from mikiorm.db_pool import (
    ConnectionState,
    PoolStatistics,
    ConnectionMetadata,
    DeadlockRetryPolicy,
    ConnectionPool,
    QueryExecutor,
)


class TestPoolStatistics:
    """Tests for PoolStatistics dataclass."""
    
    def test_initialization(self):
        """Test statistics initialization."""
        stats = PoolStatistics()
        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.idle_connections == 0
        assert stats.total_timeouts == 0
        assert isinstance(stats.created_at, datetime)
    
    def test_uptime_seconds(self):
        """Test uptime calculation."""
        stats = PoolStatistics()
        assert stats.uptime_seconds() >= 0
        
        stats.created_at = datetime.now() - timedelta(seconds=10)
        assert 9 < stats.uptime_seconds() < 11
    
    def test_utilization_percent(self):
        """Test utilization percentage."""
        stats = PoolStatistics()
        assert stats.utilization_percent() == 0.0
        
        stats.total_connections = 20
        stats.active_connections = 10
        assert stats.utilization_percent() == 50.0
        
        stats.active_connections = 20
        assert stats.utilization_percent() == 100.0


class TestConnectionMetadata:
    """Tests for ConnectionMetadata."""
    
    def test_initialization(self):
        """Test metadata initialization."""
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.HEALTHY
        )
        assert meta.connection_id == "conn1"
        assert meta.state == ConnectionState.HEALTHY
        assert meta.error_count == 0
        assert meta.query_count == 0
    
    def test_is_stale_with_no_last_used(self):
        """Test stale detection when never used."""
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.IDLE
        )
        assert not meta.is_stale(timeout_seconds=900)
    
    def test_is_stale_recently_used(self):
        """Test stale detection for recently used connection."""
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.IDLE,
            last_used_at=datetime.now()
        )
        assert not meta.is_stale(timeout_seconds=900)
    
    def test_is_stale_timeout_exceeded(self):
        """Test stale detection when timeout exceeded."""
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.IDLE,
            last_used_at=datetime.now() - timedelta(seconds=1000)
        )
        assert meta.is_stale(timeout_seconds=900)
    
    def test_acquire_duration_ms(self):
        """Test acquire duration calculation."""
        now = datetime.now()
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.IN_USE,
            acquired_at=now,
            released_at=now + timedelta(milliseconds=100)
        )
        duration = meta.acquire_duration_ms()
        assert 99 < duration < 101
    
    def test_idle_duration_seconds(self):
        """Test idle duration calculation."""
        meta = ConnectionMetadata(
            connection_id="conn1",
            state=ConnectionState.IDLE,
            released_at=datetime.now() - timedelta(seconds=10)
        )
        duration = meta.idle_duration_seconds()
        assert 9 < duration < 11


class TestDeadlockRetryPolicy:
    """Tests for deadlock retry policy."""
    
    def test_is_deadlock_error_mysql(self):
        """Test MySQL deadlock detection."""
        error = Exception("Error 1213: Deadlock found")
        assert DeadlockRetryPolicy.is_deadlock_error(error)
    
    def test_is_deadlock_error_postgresql(self):
        """Test PostgreSQL deadlock detection."""
        error = Exception("ERROR: deadlocked 40P01")
        assert DeadlockRetryPolicy.is_deadlock_error(error)
    
    def test_is_not_deadlock_error(self):
        """Test non-deadlock error."""
        error = Exception("Syntax error")
        assert not DeadlockRetryPolicy.is_deadlock_error(error)
    
    def test_backoff_ms_progression(self):
        """Test exponential backoff progression."""
        backoff1 = DeadlockRetryPolicy.get_backoff_ms(1)
        backoff2 = DeadlockRetryPolicy.get_backoff_ms(2)
        backoff3 = DeadlockRetryPolicy.get_backoff_ms(3)
        
        assert backoff1 == 100
        assert backoff2 == 200
        assert backoff3 == 400
    
    def test_backoff_ms_max_cap(self):
        """Test backoff capped at max."""
        backoff4 = DeadlockRetryPolicy.get_backoff_ms(4)
        assert backoff4 == 400


class TestConnectionPool:
    """Tests for connection pool."""
    
    def test_pool_initialization(self):
        """Test pool initialization."""
        factory = Mock()
        pool = ConnectionPool(
            factory,
            min_size=2,
            max_size=10,
            timeout=30,
            idle_timeout=900
        )
        assert pool.min_size == 2
        assert pool.max_size == 10
        assert pool.timeout == 30
        assert pool.idle_timeout == 900
    
    def test_acquire_creates_connection(self):
        """Test acquiring a connection."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        
        acquired = pool.acquire(timeout=5)
        assert acquired is conn
        assert factory.called
    
    def test_acquire_reuses_available(self):
        """Test reusing available connection."""
        conn1 = Mock()
        conn2 = Mock()
        factory = Mock(side_effect=[conn1, conn2])
        pool = ConnectionPool(factory, max_size=5)
        
        # Acquire first connection
        c1 = pool.acquire(timeout=5)
        assert c1 is conn1
        
        # Release it
        pool.release(c1)
        
        # Acquire again - should reuse
        c1_again = pool.acquire(timeout=5)
        assert c1_again is conn1
        
        # Factory should only be called once
        assert factory.call_count == 1
    
    def test_acquire_timeout(self):
        """Test acquisition timeout."""
        factory = Mock()
        pool = ConnectionPool(factory, max_size=1, timeout=0.1)
        
        # Acquire the only available connection
        conn = pool.acquire(timeout=1)
        
        # Try to acquire another - should timeout
        with pytest.raises(TimeoutError):
            pool.acquire(timeout=0.1)
    
    def test_release_unhealthy_discards(self):
        """Test releasing unhealthy connection discards it."""
        conn = Mock()
        conn.ping = Mock(side_effect=Exception("Connection lost"))
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        
        conn_acquired = pool.acquire(timeout=5)
        
        # Mock health check to fail
        with patch.object(pool, '_is_connection_healthy', return_value=False):
            pool.release(conn_acquired)
        
        # Verify stats
        stats = pool.get_statistics()
        assert stats.active_connections == 0
        assert stats.idle_connections == 0
    
    def test_cleanup_stale_connections(self):
        """Test stale connection cleanup."""
        conns = [Mock() for _ in range(3)]
        factory = Mock(side_effect=conns)
        pool = ConnectionPool(factory, max_size=10, idle_timeout=0)
        
        # Acquire and release connections
        for conn in conns:
            c = pool.acquire(timeout=5)
            pool.release(c)
        
        # All should be idle
        assert len(pool._available) == 3
        
        # Cleanup stale
        with patch.object(pool, '_is_connection_healthy', return_value=True):
            pool._cleanup_stale_connections()
        
        # All marked as stale with timeout=0 should be removed
        assert len(pool._available) == 0
    
    def test_get_statistics(self):
        """Test pool statistics."""
        conn1 = Mock()
        conn2 = Mock()
        factory = Mock(side_effect=[conn1, conn2])
        pool = ConnectionPool(factory, max_size=10)
        
        c1 = pool.acquire(timeout=5)
        c2 = pool.acquire(timeout=5)
        
        stats = pool.get_statistics()
        assert stats.total_connections == 2
        assert stats.active_connections == 2
        assert stats.idle_connections == 0
        
        pool.release(c1)
        
        stats = pool.get_statistics()
        assert stats.active_connections == 1
        assert stats.idle_connections == 1
    
    def test_close_all(self):
        """Test closing all connections."""
        conn1 = Mock()
        conn2 = Mock()
        factory = Mock(side_effect=[conn1, conn2])
        pool = ConnectionPool(factory, max_size=10)
        
        c1 = pool.acquire(timeout=5)
        c2 = pool.acquire(timeout=5)
        pool.release(c1)
        
        pool.close_all()
        
        assert conn1.close.called
        assert conn2.close.called
        assert len(pool._available) == 0
        assert len(pool._in_use) == 0
    
    def test_thread_safety(self):
        """Test thread-safe concurrent access."""
        acquired = []
        errors = []
        
        def acquire_and_release():
            try:
                conn = Mock()
                pool = ConnectionPool(Mock(return_value=conn), max_size=5, timeout=1)
                c = pool.acquire(timeout=1)
                acquired.append(c)
                time.sleep(0.01)
                pool.release(c)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=acquire_and_release) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestQueryExecutor:
    """Tests for query executor."""
    
    def test_execute_success(self):
        """Test successful query execution."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection):
            return "result"
        
        result = executor.execute(query_func)
        assert result == "result"
    
    def test_execute_with_args(self):
        """Test query execution with arguments."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection, arg1, arg2):
            return arg1 + arg2
        
        result = executor.execute(query_func, 5, 10)
        assert result == 15
    
    def test_execute_with_kwargs(self):
        """Test query execution with keyword arguments."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection, x=0, y=0):
            return x * y
        
        result = executor.execute(query_func, x=3, y=4)
        assert result == 12
    
    def test_execute_deadlock_retry(self):
        """Test deadlock detection and retry."""
        conn = Mock()
        
        call_count = [0]
        def factory():
            return conn
        
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Error 1213: Deadlock found")
            return "success"
        
        result = executor.execute(query_func, retry_on_deadlock=True)
        assert result == "success"
        assert call_count[0] == 2
    
    def test_execute_timeout_error_not_retried(self):
        """Test that timeout errors are not retried."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection):
            raise TimeoutError("Timeout")
        
        with pytest.raises(TimeoutError):
            executor.execute(query_func, timeout=1)
    
    def test_execute_max_retries_exceeded(self):
        """Test max retries exceeded."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        def query_func(connection):
            raise Exception("Error 1213: Deadlock found")
        
        with pytest.raises(Exception):
            executor.execute(query_func, retry_on_deadlock=True)
    
    def test_execute_non_deadlock_error_not_retried(self):
        """Test non-deadlock errors are not retried."""
        conn = Mock()
        factory = Mock(return_value=conn)
        pool = ConnectionPool(factory, max_size=5)
        executor = QueryExecutor(pool)
        
        call_count = [0]
        def query_func(connection):
            call_count[0] += 1
            raise Exception("Syntax error")
        
        with pytest.raises(Exception):
            executor.execute(query_func, retry_on_deadlock=True)
        
        # Should only be called once (no retry)
        assert call_count[0] == 1


class TestConnectionPoolIntegration:
    """Integration tests for connection pool."""
    
    def test_pool_concurrent_load(self):
        """Test pool under concurrent load."""
        results = []
        errors = []
        
        conn_factory_calls = [0]
        def factory():
            conn_factory_calls[0] += 1
            conn = Mock()
            conn.id = conn_factory_calls[0]
            return conn
        
        pool = ConnectionPool(factory, max_size=5, timeout=1)
        
        def worker(worker_id):
            try:
                for _ in range(3):
                    conn = pool.acquire(timeout=1)
                    time.sleep(0.01)
                    pool.release(conn)
                    results.append(worker_id)
            except Exception as e:
                errors.append((worker_id, e))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 30
        
        # Should reuse connections (not create 30)
        assert conn_factory_calls[0] <= 5
    
    def test_pool_stats_accuracy(self):
        """Test pool statistics accuracy."""
        conns = [Mock() for _ in range(3)]
        factory = Mock(side_effect=conns)
        pool = ConnectionPool(factory, max_size=10)
        
        c1 = pool.acquire(timeout=5)
        c2 = pool.acquire(timeout=5)
        
        stats = pool.get_statistics()
        assert stats.total_acquisitions == 2
        
        pool.release(c1)
        pool.release(c2)
        
        stats = pool.get_statistics()
        assert stats.total_releases == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

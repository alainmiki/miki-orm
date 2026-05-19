"""Retry mechanism for transient migration errors."""

import logging
import time
from typing import Callable, Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TransientError(Exception):
    """Base class for transient errors that can be retried."""

    pass


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff_ms: int = 100,
        max_backoff_ms: int = 10000,
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retries
            initial_backoff_ms: Initial backoff in milliseconds
            max_backoff_ms: Maximum backoff in milliseconds
            backoff_multiplier: Exponential backoff multiplier
        """
        self.max_retries = max_retries
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.backoff_multiplier = backoff_multiplier

    def get_backoff(self, attempt: int) -> int:
        """
        Calculate backoff time for attempt.

        Args:
            attempt: Zero-indexed attempt number

        Returns:
            Backoff time in milliseconds
        """
        backoff = int(
            self.initial_backoff_ms * (self.backoff_multiplier ** attempt)
        )
        return min(backoff, self.max_backoff_ms)


def is_transient_error(exception: Exception) -> bool:
    """
    Determine if an exception is transient and can be retried.

    Args:
        exception: The exception to check

    Returns:
        True if the error is transient
    """
    # Transient error types
    transient_errors = (
        TransientError,
        TimeoutError,
        ConnectionError,
        BrokenPipeError,
        ConnectionResetError,
        ConnectionAbortedError,
        ConnectionRefusedError,
    )

    if isinstance(exception, transient_errors):
        return True

    # Check error message for transient indicators
    error_msg = str(exception).lower()
    transient_indicators = (
        "timeout",
        "temporarily unavailable",
        "resource temporarily unavailable",
        "try again",
        "connection reset",
        "connection refused",
        "connection lost",
        "broken pipe",
        "database is locked",
    )

    return any(indicator in error_msg for indicator in transient_indicators)


def retry_with_backoff(
    func: Callable[..., T],
    *args: Any,
    config: RetryConfig = RetryConfig(),
    **kwargs: Any,
) -> T:
    """
    Execute a function with retry and exponential backoff.

    Args:
        func: The function to execute
        *args: Positional arguments to pass to func
        config: RetryConfig for retry behavior
        **kwargs: Keyword arguments to pass to func

    Returns:
        The result of func

    Raises:
        The last exception encountered after max retries
    """
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if not is_transient_error(e):
                # Non-transient error: fail immediately
                logger.error(
                    f"Non-transient error on attempt {attempt + 1}: {e}"
                )
                raise

            if attempt < config.max_retries:
                backoff_ms = config.get_backoff(attempt)
                logger.warning(
                    f"Transient error on attempt {attempt + 1}, "
                    f"retrying in {backoff_ms}ms: {e}"
                )
                time.sleep(backoff_ms / 1000.0)
            else:
                logger.error(
                    f"Max retries ({config.max_retries}) exceeded after {attempt + 1} attempts: {e}"
                )

    # If we get here, we've exhausted retries
    if last_exception:
        raise last_exception

    raise RuntimeError("Retry loop completed without result or exception")

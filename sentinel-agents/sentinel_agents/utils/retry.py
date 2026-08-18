"""Configurable retry helpers built on tenacity.

Central place for retry policy so LLM calls, threat-intel lookups, and key DB
operations share one configurable exponential-backoff strategy. Parameters
come from env (overridable per call):

    SENTINEL_RETRY_ATTEMPTS   (default 3)   — total attempts
    SENTINEL_RETRY_BASE_S     (default 1)   — exponential base interval, seconds
    SENTINEL_RETRY_MAX_S      (default 10)  — max backoff interval, seconds

Only *retryable* exceptions are retried: transient network/timeout/5xx-style
errors. Programming errors and 4xx client errors surface immediately.
"""

from __future__ import annotations

import os
from typing import Any, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

F = TypeVar("F", bound=Callable[..., Any])


def retry_attempts() -> int:
    return int(os.getenv("SENTINEL_RETRY_ATTEMPTS", "3"))


def retry_base_seconds() -> float:
    return float(os.getenv("SENTINEL_RETRY_BASE_S", "1"))


def retry_max_seconds() -> float:
    return float(os.getenv("SENTINEL_RETRY_MAX_S", "10"))


# Exceptions considered transient and safe to retry.
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    ConnectionError,
    TimeoutError,
)


def is_retryable(exc: BaseException) -> bool:
    """
    Decide whether an exception is worth retrying.

    Retryable: network/timeout/protocol errors, and HTTP 5xx / 429 responses.
    Not retryable: everything else (4xx client errors, ValueError, etc.).
    """
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    # HTTP status errors: retry only 429 and 5xx.
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return False


def async_retry(
    attempts: int | None = None,
    base_s: float | None = None,
    max_s: float | None = None,
) -> AsyncRetrying:
    """
    Build an AsyncRetrying with the configured exponential-backoff policy.

    Usage::

        async for attempt in async_retry():
            with attempt:
                await do_something()
    """
    return AsyncRetrying(
        retry=retry_if_exception(is_retryable),
        stop=stop_after_attempt(attempts or retry_attempts()),
        wait=wait_exponential(
            multiplier=base_s or retry_base_seconds(),
            max=max_s or retry_max_seconds(),
        ),
        reraise=True,
    )


async def call_with_retry(
    func: Callable[..., Any],
    *args: Any,
    attempts: int | None = None,
    base_s: float | None = None,
    max_s: float | None = None,
    **kwargs: Any,
) -> Any:
    """
    Await ``func(*args, **kwargs)`` retrying retryable failures with backoff.

    Reraises the last exception after exhausting attempts.
    """
    async for attempt in async_retry(attempts=attempts, base_s=base_s, max_s=max_s):
        with attempt:
            return await func(*args, **kwargs)

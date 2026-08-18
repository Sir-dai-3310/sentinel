"""Sentinel SDK exceptions and error mapping."""

from __future__ import annotations


class SentinelError(Exception):
    """Base error for all SDK failures.

    Attributes:
        status_code: HTTP status code if the error came from an API response.
        detail: Server-provided error detail when available.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: object = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AuthError(SentinelError):
    """401 — missing, invalid, or expired credentials."""


class ForbiddenError(SentinelError):
    """403 — authenticated but lacking the required role/permission."""


class NotFoundError(SentinelError):
    """404 — the requested resource does not exist."""


class ConflictError(SentinelError):
    """409 — resource conflict (e.g. duplicate rule id)."""


class RequestError(SentinelError):
    """400/422 — the request was malformed or failed validation."""


class RateLimitError(SentinelError):
    """429 — rate limit exceeded.

    Attributes:
        retry_after: Seconds to wait before retrying, if the server said so.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = 429,
        detail: object = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code, detail)
        self.retry_after = retry_after


class ServerError(SentinelError):
    """5xx — server-side failure (retried automatically by default)."""


class NetworkError(SentinelError):
    """Connection/timeout failure (retried automatically by default)."""


def error_from_status(status_code: int, detail: object = None) -> SentinelError:
    """Map an HTTP error status to the matching SDK exception."""
    message = detail if isinstance(detail, str) else f"HTTP {status_code}"
    if status_code == 401:
        return AuthError(message, status_code, detail)
    if status_code == 403:
        return ForbiddenError(message, status_code, detail)
    if status_code == 404:
        return NotFoundError(message, status_code, detail)
    if status_code == 409:
        return ConflictError(message, status_code, detail)
    if status_code == 429:
        return RateLimitError(message, status_code, detail)
    if status_code in (400, 422):
        return RequestError(message, status_code, detail)
    if status_code >= 500:
        return ServerError(message, status_code, detail)
    return SentinelError(message, status_code, detail)

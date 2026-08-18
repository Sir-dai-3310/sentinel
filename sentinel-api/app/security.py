"""Security middleware for Sentinel API."""

import os
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        if os.getenv("ENVIRONMENT") == "production":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'"
            )

        # HSTS (only in production with HTTPS)
        if os.getenv("ENVIRONMENT") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Prevent caching of sensitive data
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


class RateLimiter:
    """Simple in-memory rate limiter using token bucket algorithm."""

    def __init__(self, rate: int = 100, per: int = 60):
        """
        Initialize rate limiter.

        Args:
            rate: Maximum requests allowed
            per: Time window in seconds
        """
        self.rate = rate
        self.per = per
        self.buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed.

        Args:
            key: Client identifier (IP address, API key, etc.)

        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        bucket = self.buckets[key]

        # Remove old entries
        bucket[:] = [t for t in bucket if now - t < self.per]

        if len(bucket) < self.rate:
            bucket.append(now)
            return True

        return False

    def remaining(self, key: str) -> int:
        """Get remaining requests in current window."""
        now = time.time()
        bucket = self.buckets[key]
        bucket[:] = [t for t in bucket if now - t < self.per]
        return max(0, self.rate - len(bucket))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""

    def __init__(self, app, rate: int = 100, per: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(rate=rate, per=per)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        # Also check for forwarded IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        if not self.limiter.is_allowed(client_ip):
            remaining = self.limiter.remaining(client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Too many requests. Try again in {self.limiter.per} seconds.",
                    "remaining": remaining,
                },
                headers={
                    "Retry-After": str(self.limiter.per),
                    "X-RateLimit-Limit": str(self.limiter.rate),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(int(time.time()) + self.limiter.per),
                },
            )

        return await call_next(request)


class AuditLogger:
    """Audit log for security-relevant events."""

    def __init__(self):
        self.enabled = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
        self.log_file = os.getenv("AUDIT_LOG_FILE", "/var/log/sentinel/audit.log")

    def log(
        self,
        action: str,
        user: str,
        resource: str = "",
        details: dict[str, Any] | None = None,
        ip: str = "",
        success: bool = True,
    ) -> None:
        """
        Log a security-relevant event.

        Args:
            action: Action performed (e.g., "login", "rule_create", "analyze")
            user: User who performed the action
            resource: Resource affected (e.g., rule ID)
            details: Additional details
            ip: Client IP address
            success: Whether the action succeeded
        """
        if not self.enabled:
            return

        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "action": action,
            "user": user,
            "resource": resource,
            "ip": ip,
            "success": success,
            "request_id": str(uuid.uuid4()),
        }

        if details:
            entry["details"] = details

        # Write to audit log file
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, "a") as f:
                import json
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            # Fallback to stderr
            print(f"AUDIT_LOG_ERROR: {e}", file=__import__("sys").stderr)


# Global instances
audit_logger = AuditLogger()

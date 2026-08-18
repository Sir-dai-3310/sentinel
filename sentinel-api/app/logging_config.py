"""Structured JSON logging for Sentinel."""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

# Context variable for request ID tracking
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class StructuredFormatter(logging.Formatter):
    """JSON-formatted log output for ELK/Loki compatibility."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(""),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Get a structured JSON logger.

    Args:
        name: Logger name (usually __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

    return logger


def set_request_id(request_id: str | None = None) -> str:
    """
    Set the current request ID for log correlation.

    Args:
        request_id: Request ID (auto-generated if None)

    Returns:
        The request ID
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    return request_id


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_fields: Any,
) -> None:
    """
    Log a message with additional structured fields.

    Args:
        logger: Logger instance
        level: Log level
        message: Log message
        **extra_fields: Additional key-value pairs to include in log
    """
    record = logger.makeRecord(
        logger.name,
        level,
        "",
        0,
        message,
        (),
        None,
    )
    record.extra_fields = extra_fields
    logger.handle(record)


class RequestIDMiddleware:
    """Middleware to inject request ID into each request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request_id = set_request_id()
            scope["request_id"] = request_id
        await self.app(scope, receive, send)

"""Sentinel Python SDK — async client for the Sentinel API."""

from sentinel_sdk.client import SentinelClient
from sentinel_sdk.exceptions import (
    AuthError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RequestError,
    SentinelError,
    ServerError,
)
from sentinel_sdk.models import (
    AnalysisResult,
    BatchAnalysisResult,
    Health,
    ImportStatus,
    Rule,
    RuleList,
    RuleSummary,
    Stats,
    Token,
)

__version__ = "1.2.0"

__all__ = [
    "SentinelClient",
    "__version__",
    # models
    "AnalysisResult",
    "BatchAnalysisResult",
    "Health",
    "ImportStatus",
    "Rule",
    "RuleList",
    "RuleSummary",
    "Stats",
    "Token",
    # exceptions
    "SentinelError",
    "AuthError",
    "ForbiddenError",
    "NotFoundError",
    "ConflictError",
    "RequestError",
    "RateLimitError",
    "ServerError",
    "NetworkError",
]

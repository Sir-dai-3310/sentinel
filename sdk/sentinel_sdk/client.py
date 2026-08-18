"""Async client for the Sentinel API.

Retries (5xx / network errors) use a small exponential-backoff loop so the
only runtime dependency is httpx; HTTP error statuses are mapped to typed
SDK exceptions — see ``exceptions.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from sentinel_sdk.exceptions import (
    NetworkError,
    RateLimitError,
    ServerError,
    error_from_status,
)
from sentinel_sdk.models import (
    AnalysisResult,
    BatchAnalysisResult,
    Health,
    ImportStatus,
    Rule,
    RuleList,
    Stats,
    Token,
)

API_PREFIX = "/api/v1"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB client-side guard for file uploads


class SentinelClient:
    """Sentinel API client.

    Args:
        base_url: API origin, e.g. ``http://localhost:8000`` (no ``/api/v1`` suffix).
        token: Bearer token (JWT or API key). Optional if you'll call :meth:`login`.
        timeout: Per-request timeout in seconds.
        retries: Total attempts for retriable failures (5xx, connection errors).
        retry_backoff: Initial exponential backoff in seconds (doubles per attempt).
        transport: Optional httpx transport (e.g. ASGITransport in tests).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: str | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        retry_backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be >= 1")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "SentinelClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # low-level request machinery
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _detail(response: httpx.Response) -> Any:
        try:
            body = response.json()
            if isinstance(body, dict):
                # FastAPI errors carry "detail"; the i18n middleware localizes
                # them into "message" — accept both so errors stay informative.
                return body.get("detail") or body.get("message") or body.get("error") or body
            return body
        except ValueError:
            return response.text[:500]

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = self._detail(response)
        if response.status_code == 429:
            retry_after = None
            raw = response.headers.get("retry-after")
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    retry_after = None
            raise RateLimitError(
                detail if isinstance(detail, str) else "Rate limit exceeded",
                status_code=429,
                detail=detail,
                retry_after=retry_after,
            )
        raise error_from_status(response.status_code, detail)

    async def _request_once(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Single request attempt; raises retriable exceptions as-is."""
        try:
            response = await self._client.request(
                method,
                f"{API_PREFIX}{path}",
                headers=self._headers(),
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise NetworkError(f"{type(exc).__name__}: {exc}") from exc
        # Retryable server errors are raised here so tenacity can retry them.
        if response.status_code >= 500:
            self._raise_for_status(response)
        return response

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Request with retry on 5xx/network errors, then error mapping."""
        last_exc: ServerError | NetworkError | None = None
        for attempt in range(self.retries):
            try:
                response = await self._request_once(method, path, **kwargs)
            except (ServerError, NetworkError) as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    await asyncio.sleep(self.retry_backoff * (2**attempt))
                continue
            self._raise_for_status(response)
            return response
        assert last_exc is not None  # retries >= 1 guarantees an attempt ran
        raise last_exc

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str) -> Token:
        """Authenticate with username/password; stores the token on the client."""
        response = await self._request(
            "POST", "/auth/login", json={"username": username, "password": password}
        )
        token = Token.from_dict(response.json())
        self.token = token.access_token
        return token

    def authenticate(self, token: str) -> "SentinelClient":
        """Set an existing bearer token (fluent)."""
        self.token = token
        return self

    # ------------------------------------------------------------------
    # core endpoints
    # ------------------------------------------------------------------

    async def health(self) -> Health:
        """GET /health — liveness and per-service status."""
        response = await self._request("GET", "/health")
        return Health.from_dict(response.json())

    async def analyze(self, log: dict[str, Any]) -> AnalysisResult:
        """POST /analyze — analyze a single log event."""
        response = await self._request("POST", "/analyze", json={"log": log}, timeout=max(self.timeout, 60.0))
        return AnalysisResult.from_dict(response.json())

    async def analyze_batch(self, logs: list[dict[str, Any]]) -> BatchAnalysisResult:
        """POST /analyze/batch — analyze many log events in parallel."""
        response = await self._request("POST", "/analyze/batch", json={"logs": logs}, timeout=max(self.timeout, 120.0))
        return BatchAnalysisResult.from_dict(response.json())

    async def get_stats(self) -> Stats:
        """GET /stats — dashboard statistics."""
        response = await self._request("GET", "/stats")
        return Stats.from_dict(response.json())

    async def llm_costs(self) -> dict[str, Any]:
        """GET /stats/llm-costs — LLM usage and estimated cost summary."""
        response = await self._request("GET", "/stats/llm-costs")
        return response.json()

    async def get_settings(self) -> dict[str, Any]:
        """GET /settings — sanitized runtime settings."""
        response = await self._request("GET", "/settings")
        return response.json()

    # ------------------------------------------------------------------
    # rules
    # ------------------------------------------------------------------

    async def list_rules(self) -> RuleList:
        """GET /rules — list all Sigma rules."""
        response = await self._request("GET", "/rules")
        return RuleList.from_dict(response.json())

    async def get_rule(self, rule_id: str) -> Rule:
        """GET /rules/{rule_id}."""
        response = await self._request("GET", f"/rules/{rule_id}")
        return Rule.from_dict(response.json())

    async def create_rule(self, rule: Rule | dict[str, Any]) -> dict[str, Any]:
        """POST /rules — create a new Sigma rule; returns {status, file_path}."""
        payload = rule.to_dict() if isinstance(rule, Rule) else rule
        response = await self._request("POST", "/rules", json=payload)
        return response.json()

    async def update_rule(self, rule_id: str, rule: Rule | dict[str, Any]) -> dict[str, Any]:
        """PUT /rules/{rule_id} — overwrite an existing rule."""
        payload = rule.to_dict() if isinstance(rule, Rule) else rule
        response = await self._request("PUT", f"/rules/{rule_id}", json=payload)
        return response.json()

    async def delete_rule(self, rule_id: str) -> dict[str, Any]:
        """DELETE /rules/{rule_id}."""
        response = await self._request("DELETE", f"/rules/{rule_id}")
        return response.json()

    async def reload_rules(self) -> dict[str, Any]:
        """POST /rules/reload — trigger an engine rule reload."""
        response = await self._request("POST", "/rules/reload")
        return response.json()

    # ------------------------------------------------------------------
    # bulk import
    # ------------------------------------------------------------------

    async def import_logs(self, file: str | Path | BinaryIO) -> ImportStatus:
        """POST /logs/import — upload a JSONL/CSV file; returns the initial task status."""
        if isinstance(file, (str, Path)):
            path = Path(file)
            data = path.read_bytes()
            filename = path.name
        else:
            data = file.read()
            filename = getattr(file, "name", "upload.jsonl")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"import file is {len(data)} bytes; client-side limit is {MAX_UPLOAD_BYTES} bytes"
            )
        files = {"file": (filename, data, "application/octet-stream")}
        response = await self._request("POST", "/logs/import", files=files, timeout=max(self.timeout, 60.0))
        return ImportStatus.from_dict(response.json())

    async def import_status(self, task_id: str) -> ImportStatus:
        """GET /logs/import/{task_id} — poll an import task."""
        response = await self._request("GET", f"/logs/import/{task_id}")
        return ImportStatus.from_dict(response.json())

    async def poll_import(
        self,
        task_id: str,
        wait: bool = True,
        interval: float = 1.0,
        timeout: float = 300.0,
    ) -> ImportStatus:
        """Poll an import task until it reaches a terminal state.

        With wait=False, performs a single status fetch. Terminal states are
        ``completed``, ``failed``; raises TimeoutError if not terminal by
        ``timeout`` seconds.
        """
        if not wait:
            return await self.import_status(task_id)
        waited = 0.0
        while True:
            status = await self.import_status(task_id)
            if status.status in ("completed", "failed"):
                return status
            if waited >= timeout:
                raise TimeoutError(
                    f"import task {task_id} still {status.status} after {timeout}s "
                    f"({status.processed}/{status.total} processed)"
                )
            await asyncio.sleep(min(interval, max(timeout - waited, 0.0)))
            waited += interval

    # ------------------------------------------------------------------
    # privacy (admin)
    # ------------------------------------------------------------------

    async def export_privacy(self, subject: str) -> dict[str, Any]:
        """GET /privacy/export — export all data held for a subject (admin)."""
        response = await self._request("GET", "/privacy/export", params={"subject": subject})
        return response.json()

    async def delete_privacy(self, subject: str) -> dict[str, Any]:
        """DELETE /privacy/data — erase all data held for a subject (admin)."""
        response = await self._request("DELETE", "/privacy/data", params={"subject": subject})
        return response.json()

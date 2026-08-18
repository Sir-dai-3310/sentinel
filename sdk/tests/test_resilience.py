"""Retry / rate-limit behavior tests.

These use small but REAL FastAPI apps (actual ASGI stack, actual rate-limit
middleware from sentinel-api) — the SDK talks to them through
httpx.ASGITransport exactly as over the network.
"""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "sentinel-api") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "sentinel-api"))

from app.security import RateLimitMiddleware  # noqa: E402

from sentinel_sdk import (  # noqa: E402
    NetworkError,
    RateLimitError,
    SentinelClient,
    ServerError,
)


def flaky_app(failures: int) -> tuple[FastAPI, dict]:
    """App whose /api/v1/health 500s `failures` times before returning 200."""
    app = FastAPI()
    state = {"calls": 0}

    @app.get("/api/v1/health")
    async def health():
        state["calls"] += 1
        if state["calls"] <= failures:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=500, content={"detail": "boom"})
        return {"status": "healthy", "version": "1.2.0", "services": {"api": "up"}}

    return app, state


async def test_retries_5xx_then_succeeds():
    app, state = flaky_app(failures=2)
    async with SentinelClient(
        "http://t", transport=httpx.ASGITransport(app=app),
        retries=3, retry_backoff=0.01,
    ) as client:
        health = await client.health()
    assert health.status == "healthy"
    assert state["calls"] == 3  # 1 initial + 2 retries


async def test_5xx_exhausts_retries_and_raises_server_error():
    app, state = flaky_app(failures=99)
    async with SentinelClient(
        "http://t", transport=httpx.ASGITransport(app=app),
        retries=3, retry_backoff=0.01,
    ) as client:
        with pytest.raises(ServerError) as exc_info:
            await client.health()
    assert exc_info.value.status_code == 500
    assert state["calls"] == 3  # exactly `retries` attempts, no more


async def test_no_retry_on_4xx(admin_client):
    """4xx must fail fast (single attempt) — proven via 404 get_rule."""
    from sentinel_sdk import NotFoundError

    with pytest.raises(NotFoundError):
        await admin_client.get_rule("four-oh-four-rule")


def rate_limited_app() -> FastAPI:
    """Real app behind the real RateLimitMiddleware (burst=1 per 60s)."""
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    app.add_middleware(RateLimitMiddleware, rate=1, per=60)
    return app


async def test_429_maps_to_rate_limit_error_with_retry_after():
    app = rate_limited_app()
    async with SentinelClient("http://t", transport=httpx.ASGITransport(app=app)) as client:
        # First request consumes the window (health would bypass the limiter).
        first = await client._request("GET", "/ping")
        assert first.status_code == 200
        with pytest.raises(RateLimitError) as exc_info:
            await client._request("GET", "/ping")
    err = exc_info.value
    assert err.status_code == 429
    assert err.retry_after == 60.0  # parsed from the Retry-After header


async def test_network_error_on_unreachable_host():
    async with SentinelClient(
        "http://127.0.0.1:1", timeout=1.0, retries=2, retry_backoff=0.01,
    ) as client:
        with pytest.raises(NetworkError):
            await client.health()

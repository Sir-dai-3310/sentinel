"""Retry & exponential-backoff tests (tenacity wrapper)."""

import httpx
import pytest

from sentinel_agents.utils.retry import (
    async_retry,
    call_with_retry,
    is_retryable,
    retry_attempts,
    retry_base_seconds,
    retry_max_seconds,
)


def _timeout():
    return httpx.TimeoutException("timed out")


class TestIsRetryable:
    def test_timeout_retryable(self):
        assert is_retryable(httpx.TimeoutException("t")) is True

    def test_network_error_retryable(self):
        assert is_retryable(httpx.ConnectError("c")) is True

    def test_value_error_not_retryable(self):
        assert is_retryable(ValueError("bad")) is False

    def test_http_5xx_retryable(self):
        resp = httpx.Response(503, request=httpx.Request("GET", "http://x"))
        exc = httpx.HTTPStatusError("err", request=resp.request, response=resp)
        assert is_retryable(exc) is True

    def test_http_429_retryable(self):
        resp = httpx.Response(429, request=httpx.Request("GET", "http://x"))
        exc = httpx.HTTPStatusError("err", request=resp.request, response=resp)
        assert is_retryable(exc) is True

    def test_http_4xx_not_retryable(self):
        resp = httpx.Response(404, request=httpx.Request("GET", "http://x"))
        exc = httpx.HTTPStatusError("err", request=resp.request, response=resp)
        assert is_retryable(exc) is False


class TestEnvConfig:
    def test_defaults(self, monkeypatch):
        for v in ("SENTINEL_RETRY_ATTEMPTS", "SENTINEL_RETRY_BASE_S", "SENTINEL_RETRY_MAX_S"):
            monkeypatch.delenv(v, raising=False)
        assert retry_attempts() == 3
        assert retry_base_seconds() == 1.0
        assert retry_max_seconds() == 10.0

    def test_overrides(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_RETRY_ATTEMPTS", "5")
        monkeypatch.setenv("SENTINEL_RETRY_BASE_S", "2")
        monkeypatch.setenv("SENTINEL_RETRY_MAX_S", "30")
        assert retry_attempts() == 5
        assert retry_base_seconds() == 2.0
        assert retry_max_seconds() == 30.0


class TestCallWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_after_n_failures(self):
        """Fails twice (retryable), then succeeds on the 3rd attempt."""
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _timeout()
            return "ok"

        # base_s=0 -> no real sleeping in tests
        result = await call_with_retry(flaky, attempts=5, base_s=0, max_s=0)
        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_attempts(self):
        calls = {"n": 0}

        async def always_fail():
            calls["n"] += 1
            raise _timeout()

        with pytest.raises(httpx.TimeoutException):
            await call_with_retry(always_fail, attempts=3, base_s=0, max_s=0)
        assert calls["n"] == 3  # exactly `attempts` tries

    @pytest.mark.asyncio
    async def test_non_retryable_not_retried(self):
        calls = {"n": 0}

        async def bad():
            calls["n"] += 1
            raise ValueError("programming error")

        with pytest.raises(ValueError):
            await call_with_retry(bad, attempts=5, base_s=0, max_s=0)
        assert calls["n"] == 1  # no retry on non-retryable

    @pytest.mark.asyncio
    async def test_passes_args_kwargs(self):
        async def add(a, b, scale=1):
            return (a + b) * scale

        assert await call_with_retry(add, 2, 3, scale=2, base_s=0, max_s=0) == 10


class TestAsyncRetryContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_form(self):
        calls = {"n": 0}
        async for attempt in async_retry(attempts=3, base_s=0, max_s=0):
            with attempt:
                calls["n"] += 1
                if calls["n"] < 2:
                    raise _timeout()
        assert calls["n"] == 2

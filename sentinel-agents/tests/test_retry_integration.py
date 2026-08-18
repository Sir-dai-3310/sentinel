"""Retry behaviour wired into LLMClient and the threat-intel aggregator."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sentinel_agents.llm.client import LLMClient


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    """Make backoff instant in tests."""
    monkeypatch.setenv("SENTINEL_RETRY_BASE_S", "0")
    monkeypatch.setenv("SENTINEL_RETRY_MAX_S", "0")


def _client_with_flaky_model(fail_times: int, max_retries: int = 3):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LLM_API_KEY", "test_key")
        client = LLMClient(max_retries=max_retries)
    ok = MagicMock()
    ok.content = "recovered"
    ok.response_metadata = {"token_usage": {"total_tokens": 5}}

    side_effects = [httpx.TimeoutException("t")] * fail_times + [ok]
    mock_model = AsyncMock()
    mock_model.ainvoke.side_effect = side_effects
    client.model = mock_model
    return client, mock_model


class TestLLMClientRetry:
    @pytest.mark.asyncio
    async def test_recovers_after_transient_failures(self):
        client, mock_model = _client_with_flaky_model(fail_times=2, max_retries=3)
        result = await client.ainvoke("prompt")
        assert result == "recovered"
        assert mock_model.ainvoke.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        client, mock_model = _client_with_flaky_model(fail_times=5, max_retries=3)
        with pytest.raises(httpx.TimeoutException):
            await client.ainvoke("prompt")
        assert mock_model.ainvoke.call_count == 3  # exactly max_retries

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LLM_API_KEY", "test_key")
            client = LLMClient(max_retries=5)
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = ValueError("bad prompt")
        client.model = mock_model
        with pytest.raises(ValueError):
            await client.ainvoke("prompt")
        assert mock_model.ainvoke.call_count == 1


class _FlakyProvider:
    """A threat-intel provider that fails N times then returns a result."""

    def __init__(self, fail_times: int):
        self.calls = 0
        self.fail_times = fail_times

    async def lookup_ip(self, ip):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise httpx.ConnectError("boom")
        from sentinel_agents.state import ThreatIntel

        return ThreatIntel(
            source="test", ioc_type="ip", ioc_value=ip, malicious=True, confidence=90
        )

    async def lookup_hash(self, h):
        return None

    async def lookup_domain(self, d):
        return None


class TestIntelAggregatorRetry:
    @pytest.mark.asyncio
    async def test_recovers_transient_failure(self):
        from sentinel_agents.intelligence import IntelligenceAggregator

        provider = _FlakyProvider(fail_times=2)
        agg = IntelligenceAggregator([provider])
        results = await agg.lookup_ip("1.2.3.4")
        assert len(results) == 1
        assert provider.calls == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_persistent_failure_returns_empty(self):
        from sentinel_agents.intelligence import IntelligenceAggregator

        provider = _FlakyProvider(fail_times=99)
        agg = IntelligenceAggregator([provider])
        results = await agg.lookup_ip("1.2.3.4")
        assert results == []  # tolerated, never blocks analysis

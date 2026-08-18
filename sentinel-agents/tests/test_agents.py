"""Tests for agent implementations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel_agents.agents import AnalystAgent, HunterAgent, ReporterAgent, TriageAgent
from sentinel_agents.state import IncidentState, Verdict


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.ainvoke = AsyncMock(return_value="Mocked LLM response")
    client.ainvoke_structured = AsyncMock(
        return_value=Verdict(
            malicious=True,
            danger_level=85,
            reason="Mocked analysis",
            mitre_techniques=["T1059.001"],
            recommended_actions=["Isolate host"],
        )
    )
    return client


@pytest.mark.asyncio
async def test_triage_agent_high_confidence_skip_llm(mock_llm_client):
    """Test that high confidence rule hits skip LLM."""
    agent = TriageAgent(llm_client=mock_llm_client)

    log = {
        "EventID": 1,
        "Image": "mimikatz.exe",
        "CommandLine": "mimikatz.exe sekurlsa::logonpasswords",
    }

    state = IncidentState(log=log)
    result = await agent(state)

    # Should have rule hit with confidence >= 90
    assert len(result.rule_hits) > 0
    assert any(hit.confidence >= 90 for hit in result.rule_hits)

    # Should skip LLM
    assert result.skipped_llm is True
    assert result.verdict is not None
    assert result.verdict.malicious is True


@pytest.mark.asyncio
async def test_triage_agent_low_confidence_needs_llm(mock_llm_client):
    """Test that low confidence hits don't skip LLM."""
    agent = TriageAgent(llm_client=mock_llm_client)

    log = {
        "EventID": 1,
        "Image": "powershell.exe",
        "CommandLine": "powershell -enc JABjAD0AJw",
    }

    state = IncidentState(log=log)
    result = await agent(state)

    # Should have rule hit but low confidence
    assert len(result.rule_hits) > 0

    # Should NOT skip LLM (confidence < 90)
    assert result.skipped_llm is False
    assert result.verdict is None  # Verdict should be set by AnalystAgent


@pytest.mark.asyncio
async def test_analyst_agent_graceful_degradation(mock_llm_client):
    """Test AnalystAgent handles LLM failure gracefully."""
    # Make the mock fail
    mock_llm_client.ainvoke_structured = AsyncMock(side_effect=Exception("LLM API error"))

    agent = AnalystAgent(llm_client=mock_llm_client)

    log = {"EventID": 1, "Image": "unknown.exe"}
    state = IncidentState(log=log)
    state.skipped_llm = False

    result = await agent(state)

    # Should have verdict even if LLM fails
    assert result.verdict is not None
    # Should indicate manual review needed
    assert "manual review" in result.verdict.reason.lower() or "failed" in result.verdict.reason.lower()


@pytest.mark.asyncio
async def test_analyst_agent_with_llm_success(mock_llm_client):
    """Test AnalystAgent with successful LLM call."""
    agent = AnalystAgent(llm_client=mock_llm_client)

    log = {"EventID": 1, "Image": "powershell.exe"}
    state = IncidentState(log=log)
    state.skipped_llm = False

    result = await agent(state)

    # Should have verdict from LLM
    assert result.verdict is not None
    assert result.verdict.malicious is True
    assert result.verdict.danger_level == 85
    assert "Mocked analysis" in result.verdict.reason


def test_verdict_validation():
    """Test Verdict model validation."""
    # Valid verdict
    v = Verdict(
        malicious=True,
        danger_level=85,
        reason="Test",
        mitre_techniques=["T1059.001"],
    )
    assert v.danger_level == 85

    # Danger level should be clamped to 0-100
    with pytest.raises(Exception):
        Verdict(malicious=True, danger_level=150, reason="Test")


def test_incident_state_trace():
    """Test agent trace recording."""
    state = IncidentState(log={})

    assert len(state.agent_trace) == 0

    state.agent_trace.append("Agent1")
    state.agent_trace.append("Agent2")

    assert len(state.agent_trace) == 2
    assert state.agent_trace[0] == "Agent1"

"""Tests for SOAR response module."""

import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel_agents.response import (
    ResponseEngine,
    ScriptAction,
    SlackAction,
    WebhookAction,
    get_response_engine,
)
from sentinel_agents.state import IncidentState, RuleHit, Verdict


@pytest.fixture
def sample_state():
    """Create a sample incident state with high-confidence rule hit."""
    state = IncidentState(log={"EventID": 1, "Image": "test.exe"})
    state.verdict = Verdict(
        malicious=True,
        danger_level=95,
        reason="Critical threat detected",
        mitre_techniques=["T1059.001"],
        recommended_actions=["Isolate host"],
    )
    state.rule_hits = [
        RuleHit(
            rule_id="R001",
            rule_name="Test Rule",
            technique="T1059.001",
            confidence=95,
            severity="critical",
            reason="Test",
        )
    ]
    return state


class TestWebhookAction:
    """Tests for WebhookAction."""

    def test_name(self):
        action = WebhookAction()
        assert action.name == "webhook"

    @pytest.mark.asyncio
    async def test_execute_no_url(self, sample_state):
        """Test execute without webhook URL returns False."""
        with patch.dict("os.environ", {}, clear=True):
            action = WebhookAction()
            result = await action.execute(sample_state, {})
            assert result is False

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        """Test successful webhook execution."""
        with patch.dict("os.environ", {"SOAR_WEBHOOK_URL": "https://example.com/hook"}):
            action = WebhookAction()

            mock_response = MagicMock()
            mock_response.status_code = 200

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await action.execute(sample_state, {})
                assert result is True

                # Verify webhook was called with correct payload
                call_args = mock_client.post.call_args
                assert "verdict" in str(call_args)

    @pytest.mark.asyncio
    async def test_execute_failure(self, sample_state):
        """Test webhook failure returns False."""
        with patch.dict("os.environ", {"SOAR_WEBHOOK_URL": "https://example.com/hook"}):
            action = WebhookAction()

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.side_effect = Exception("Connection failed")
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await action.execute(sample_state, {})
                assert result is False


class TestSlackAction:
    """Tests for SlackAction."""

    def test_name(self):
        action = SlackAction()
        assert action.name == "slack"

    @pytest.mark.asyncio
    async def test_execute_no_webhook(self, sample_state):
        """Test execute without Slack webhook returns False."""
        with patch.dict("os.environ", {}, clear=True):
            action = SlackAction()
            result = await action.execute(sample_state, {})
            assert result is False

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_state):
        """Test successful Slack notification."""
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            action = SlackAction()

            mock_response = MagicMock()
            mock_response.status_code = 200

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await action.execute(sample_state, {})
                assert result is True

                # Verify Slack payload
                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert "attachments" in payload
                assert payload["attachments"][0]["color"] == "danger"  # malicious = red


class TestScriptAction:
    """Tests for ScriptAction."""

    def test_name(self):
        action = ScriptAction()
        assert action.name == "script"

    @pytest.mark.asyncio
    async def test_execute_whitelist_rejection(self, sample_state):
        """Test that non-whitelisted scripts are rejected."""
        action = ScriptAction()
        result = await action.execute(sample_state, {"script": "evil_script"})
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_script_not_found(self, sample_state):
        """Test that missing script file returns False."""
        action = ScriptAction()
        result = await action.execute(sample_state, {"script": "isolate_host"})
        assert result is False  # Script file doesn't exist

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="requires a bash interpreter")
    async def test_execute_success(self, sample_state):
        """Test successful script execution."""
        import tempfile
        import os

        # Create a temporary script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/bash\necho 'OK'\nexit 0\n")
            script_path = f.name

        try:
            action = ScriptAction()
            # Override the whitelist to include our test script
            action.ALLOWED_SCRIPTS["test_script"] = script_path

            result = await action.execute(sample_state, {"script": "test_script"})
            assert result is True
        finally:
            os.unlink(script_path)


class TestResponseEngine:
    """Tests for ResponseEngine."""

    def test_register_default_actions(self):
        """Test that default actions are registered."""
        engine = ResponseEngine()
        actions = engine.list_actions()
        assert len(actions) == 3
        names = [a["name"] for a in actions]
        assert "webhook" in names
        assert "slack" in names
        assert "script" in names

    def test_register_custom_action(self):
        """Test registering a custom action."""
        engine = ResponseEngine()

        class CustomAction(WebhookAction):
            @property
            def name(self):
                return "custom"

        engine.register(CustomAction())
        actions = engine.list_actions()
        assert len(actions) == 4

    @pytest.mark.asyncio
    async def test_execute_for_state_no_high_confidence(self, sample_state):
        """Test that low-confidence hits don't trigger actions."""
        sample_state.rule_hits[0].confidence = 50  # Below threshold

        engine = ResponseEngine()
        results = await engine.execute_for_state(sample_state)
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_for_state_disabled_actions(self, sample_state):
        """Test that disabled actions are not executed."""
        engine = ResponseEngine()
        results = await engine.execute_for_state(sample_state)
        # All actions disabled by default
        assert results == {}

    def test_get_response_engine_singleton(self):
        """Test that get_response_engine returns singleton."""
        e1 = get_response_engine()
        e2 = get_response_engine()
        assert e1 is e2

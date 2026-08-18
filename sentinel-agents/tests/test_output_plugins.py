"""Tests for output plugins."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel_agents.output import (
    ElasticsearchPlugin,
    OutputPluginManager,
    SlackPlugin,
    WebhookPlugin,
    get_plugin_manager,
)
from sentinel_agents.state import IncidentState, Verdict


@pytest.fixture
def sample_state():
    """Create a sample incident state."""
    state = IncidentState(log={"EventID": 1, "Image": "test.exe"})
    state.verdict = Verdict(
        malicious=True,
        danger_level=85,
        reason="Test verdict",
        mitre_techniques=["T1059.001"],
        recommended_actions=["Isolate host"],
    )
    return state


class TestSlackPlugin:
    """Tests for SlackPlugin."""

    def test_name(self):
        plugin = SlackPlugin()
        assert plugin.name == "slack"

    def test_is_enabled_default(self):
        with patch.dict("os.environ", {}, clear=True):
            plugin = SlackPlugin()
            assert plugin.is_enabled() is False

    def test_is_enabled_when_set(self):
        with patch.dict("os.environ", {"OUTPUT_SLACK_ENABLED": "true"}):
            plugin = SlackPlugin()
            assert plugin.is_enabled() is True

    @pytest.mark.asyncio
    async def test_send_no_webhook(self, sample_state):
        with patch.dict("os.environ", {}, clear=True):
            plugin = SlackPlugin()
            result = await plugin.send(sample_state)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_success(self, sample_state):
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            plugin = SlackPlugin()

            mock_response = MagicMock()
            mock_response.status_code = 200

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await plugin.send(sample_state)
                assert result is True


class TestWebhookPlugin:
    """Tests for WebhookPlugin."""

    def test_name(self):
        plugin = WebhookPlugin()
        assert plugin.name == "webhook"

    def test_is_enabled_default(self):
        with patch.dict("os.environ", {}, clear=True):
            plugin = WebhookPlugin()
            assert plugin.is_enabled() is False

    @pytest.mark.asyncio
    async def test_send_no_webhook(self, sample_state):
        with patch.dict("os.environ", {}, clear=True):
            plugin = WebhookPlugin()
            result = await plugin.send(sample_state)
            assert result is False


class TestElasticsearchPlugin:
    """Tests for ElasticsearchPlugin."""

    def test_name(self):
        plugin = ElasticsearchPlugin()
        assert plugin.name == "elasticsearch"

    def test_is_enabled_default(self):
        with patch.dict("os.environ", {}, clear=True):
            plugin = ElasticsearchPlugin()
            assert plugin.is_enabled() is False

    @pytest.mark.asyncio
    async def test_send_success(self, sample_state):
        with patch.dict("os.environ", {"ELASTICSEARCH_URL": "http://localhost:9200"}):
            plugin = ElasticsearchPlugin()

            mock_response = MagicMock()
            mock_response.status_code = 201

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client_class.return_value = mock_client

                result = await plugin.send(sample_state)
                assert result is True


class TestOutputPluginManager:
    """Tests for OutputPluginManager."""

    def test_register_default_plugins(self):
        manager = OutputPluginManager()
        plugins = manager.list_plugins()
        assert len(plugins) == 3
        names = [p["name"] for p in plugins]
        assert "slack" in names
        assert "webhook" in names
        assert "elasticsearch" in names

    def test_register_custom_plugin(self):
        manager = OutputPluginManager()

        class CustomPlugin(SlackPlugin):
            @property
            def name(self):
                return "custom"

        manager.register(CustomPlugin())
        plugins = manager.list_plugins()
        assert len(plugins) == 4

    @pytest.mark.asyncio
    async def test_send_all_disabled(self, sample_state):
        manager = OutputPluginManager()
        results = await manager.send_all(sample_state)
        assert results == {}

    def test_get_plugin_manager_singleton(self):
        m1 = get_plugin_manager()
        m2 = get_plugin_manager()
        assert m1 is m2

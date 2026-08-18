"""Output plugin system for Sentinel."""

import os
from abc import ABC, abstractmethod
from typing import Any

from sentinel_agents.state import IncidentState


class OutputPlugin(ABC):
    """Base class for output plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @abstractmethod
    async def send(self, state: IncidentState) -> bool:
        """
        Send analysis result to the output destination.

        Args:
            state: Complete incident state with verdict

        Returns:
            True if successful, False otherwise
        """
        pass

    def is_enabled(self) -> bool:
        """Check if plugin is enabled via environment."""
        env_key = f"OUTPUT_{self.name.upper()}_ENABLED"
        return os.getenv(env_key, "false").lower() == "true"


class SlackPlugin(OutputPlugin):
    """Send results to Slack webhook."""

    @property
    def name(self) -> str:
        return "slack"

    async def send(self, state: IncidentState) -> bool:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return False

        try:
            import httpx

            verdict = state.verdict
            if not verdict:
                return False

            color = "danger" if verdict.malicious else "good"
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"Sentinel Alert: {'Malicious' if verdict.malicious else 'Benign'}",
                        "fields": [
                            {"title": "Danger Level", "value": str(verdict.danger_level), "short": True},
                            {"title": "Confidence", "value": f"{verdict.danger_level}%", "short": True},
                            {"title": "Reason", "value": verdict.reason, "short": False},
                            {"title": "MITRE Techniques", "value": ", ".join(verdict.mitre_techniques), "short": False},
                        ],
                    }
                ]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=10)
                return response.status_code == 200
        except Exception:
            return False


class WebhookPlugin(OutputPlugin):
    """Send results to a generic webhook."""

    @property
    def name(self) -> str:
        return "webhook"

    async def send(self, state: IncidentState) -> bool:
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            return False

        try:
            import httpx

            payload = {
                "verdict": state.verdict.model_dump() if state.verdict else None,
                "rule_hits": [h.model_dump() for h in state.rule_hits],
                "agent_trace": state.agent_trace,
                "timestamp": state.metadata.get("timestamp", ""),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=10)
                return response.status_code in (200, 201, 202, 204)
        except Exception:
            return False


class ElasticsearchPlugin(OutputPlugin):
    """Send results to Elasticsearch."""

    @property
    def name(self) -> str:
        return "elasticsearch"

    async def send(self, state: IncidentState) -> bool:
        es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        es_index = os.getenv("ELASTICSEARCH_INDEX", "sentinel-alerts")

        try:
            import httpx

            doc = {
                "verdict": state.verdict.model_dump() if state.verdict else None,
                "rule_hits": [h.model_dump() for h in state.rule_hits],
                "threat_intel": [t.model_dump() for t in state.threat_intel],
                "agent_trace": state.agent_trace,
                "log": state.log,
                "@timestamp": state.metadata.get("timestamp", ""),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{es_url}/{es_index}/_doc",
                    json=doc,
                    timeout=10,
                )
                return response.status_code in (200, 201)
        except Exception:
            return False


class OutputPluginManager:
    """Manages output plugins."""

    def __init__(self):
        self._plugins: list[OutputPlugin] = []
        self._register_default_plugins()

    def _register_default_plugins(self):
        """Register built-in plugins."""
        self.register(SlackPlugin())
        self.register(WebhookPlugin())
        self.register(ElasticsearchPlugin())

    def register(self, plugin: OutputPlugin) -> None:
        """Register an output plugin."""
        self._plugins.append(plugin)

    async def send_all(self, state: IncidentState) -> dict[str, bool]:
        """
        Send to all enabled plugins.

        Returns:
            Dictionary of plugin_name -> success
        """
        results = {}
        for plugin in self._plugins:
            if plugin.is_enabled():
                results[plugin.name] = await plugin.send(state)
        return results

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all registered plugins."""
        return [
            {
                "name": p.name,
                "enabled": p.is_enabled(),
            }
            for p in self._plugins
        ]


# Global plugin manager
_plugin_manager = None


def get_plugin_manager() -> OutputPluginManager:
    """Get or create the global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = OutputPluginManager()
    return _plugin_manager

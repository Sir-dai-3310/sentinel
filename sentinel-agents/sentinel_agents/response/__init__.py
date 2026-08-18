"""SOAR (Security Orchestration, Automation and Response) framework."""

import asyncio
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any

import httpx

from sentinel_agents.state import IncidentState


class ResponseAction(ABC):
    """Base class for response actions."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Action name."""
        pass

    @abstractmethod
    async def execute(self, state: IncidentState, config: dict[str, Any]) -> bool:
        """
        Execute the response action.

        Args:
            state: Incident state with verdict
            config: Action-specific configuration

        Returns:
            True if successful
        """
        pass


class WebhookAction(ResponseAction):
    """Send alert to a webhook."""

    @property
    def name(self) -> str:
        return "webhook"

    async def execute(self, state: IncidentState, config: dict[str, Any]) -> bool:
        url = config.get("url") or os.getenv("SOAR_WEBHOOK_URL")
        if not url:
            return False

        try:
            payload = {
                "action": "alert",
                "verdict": state.verdict.model_dump() if state.verdict else None,
                "rule_hits": [h.model_dump() for h in state.rule_hits],
                "timestamp": state.metadata.get("timestamp", ""),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10)
                return response.status_code in (200, 201, 202, 204)
        except Exception:
            return False


class SlackAction(ResponseAction):
    """Send alert to Slack."""

    @property
    def name(self) -> str:
        return "slack"

    async def execute(self, state: IncidentState, config: dict[str, Any]) -> bool:
        webhook_url = config.get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return False

        try:
            verdict = state.verdict
            if not verdict:
                return False

            color = "danger" if verdict.malicious else "good"
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"Sentinel SOAR: {'Malicious' if verdict.malicious else 'Benign'}",
                        "fields": [
                            {"title": "Danger Level", "value": str(verdict.danger_level), "short": True},
                            {"title": "Reason", "value": verdict.reason[:200], "short": False},
                        ],
                    }
                ]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=10)
                return response.status_code == 200
        except Exception:
            return False


class ScriptAction(ResponseAction):
    """Execute a local script (with whitelist)."""

    ALLOWED_SCRIPTS = {
        "isolate_host": "scripts/isolate_host.sh",
        "block_ip": "scripts/block_ip.sh",
        "collect_evidence": "scripts/collect_evidence.sh",
        "notify_admin": "scripts/notify_admin.sh",
    }

    @property
    def name(self) -> str:
        return "script"

    async def execute(self, state: IncidentState, config: dict[str, Any]) -> bool:
        script_name = config.get("script")
        if not script_name or script_name not in self.ALLOWED_SCRIPTS:
            return False

        script_path = self.ALLOWED_SCRIPTS[script_name]
        if not os.path.exists(script_path):
            return False

        try:
            verdict = state.verdict
            env = {
                **os.environ,
                "SENTINEL_MALICIOUS": str(verdict.malicious if verdict else False),
                "SENTINEL_DANGER_LEVEL": str(verdict.danger_level if verdict else 0),
                "SENTINEL_REASON": verdict.reason if verdict else "",
            }

            process = await asyncio.create_subprocess_exec(
                "bash",
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            return process.returncode == 0
        except Exception:
            return False


class ResponseEngine:
    """Execute response actions based on rule hits."""

    def __init__(self):
        self._actions: dict[str, ResponseAction] = {}
        self._register_default_actions()

    def _register_default_actions(self):
        """Register built-in actions."""
        self.register(WebhookAction())
        self.register(SlackAction())
        self.register(ScriptAction())

    def register(self, action: ResponseAction) -> None:
        """Register a response action."""
        self._actions[action.name] = action

    async def execute_for_state(self, state: IncidentState) -> dict[str, bool]:
        """
        Execute all configured response actions for an incident.

        Returns:
            Dictionary of action_name -> success
        """
        results = {}

        # Check if any rule hit has response configuration
        for hit in state.rule_hits:
            response_config = hit.reason  # In production, this would come from rule metadata
            # For now, execute all enabled actions on high-confidence hits
            if hit.confidence >= 90:
                for name, action in self._actions.items():
                    config = self._get_action_config(name)
                    if config.get("enabled", False):
                        results[name] = await action.execute(state, config)

        return results

    def _get_action_config(self, name: str) -> dict[str, Any]:
        """Get action configuration from environment."""
        enabled = os.getenv(f"SOAR_{name.upper()}_ENABLED", "false").lower() == "true"
        return {"enabled": enabled}

    def list_actions(self) -> list[dict[str, Any]]:
        """List all registered actions."""
        return [
            {
                "name": action.name,
                "enabled": self._get_action_config(action.name).get("enabled", False),
            }
            for action in self._actions.values()
        ]


# Global response engine
_engine = None


def get_response_engine() -> ResponseEngine:
    """Get or create the global response engine."""
    global _engine
    if _engine is None:
        _engine = ResponseEngine()
    return _engine

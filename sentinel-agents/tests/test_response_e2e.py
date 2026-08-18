"""End-to-end SOAR verification with a REAL HTTP mock server.

Unlike test_response.py (which mocks httpx), these tests spin up an actual
HTTP server on localhost and verify that WebhookAction / SlackAction deliver
real HTTP POST requests with the expected payloads. ScriptAction is tested
with a real script on disk, and failure degradation is verified against a
dead endpoint.
"""

import asyncio
import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sentinel_agents.response import (
    ResponseEngine,
    ScriptAction,
    SlackAction,
    WebhookAction,
)
from sentinel_agents.state import IncidentState, RuleHit, Verdict


# ---------------------------------------------------------------------------
# Real HTTP mock server
# ---------------------------------------------------------------------------


class _CaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler that records every POST body it receives."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.received.append(  # type: ignore[attr-defined]
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body.decode("utf-8", errors="replace"),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):  # noqa: A002 - silence server logs
        pass


@pytest.fixture
def mock_server():
    """Start a real HTTP server on an ephemeral port; yield (url, received)."""
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    server.received = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}", server.received  # type: ignore[attr-defined]
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def malicious_state() -> IncidentState:
    return IncidentState(
        log={"EventID": 4688, "Image": "powershell.exe"},
        rule_hits=[
            RuleHit(
                rule_id="sigma-ps-001",
                rule_name="Suspicious PowerShell",
                technique="T1059.001",
                confidence=95,
                severity="high",
                reason="encoded command",
            )
        ],
        verdict=Verdict(
            malicious=True,
            danger_level=92,
            reason="Encoded PowerShell attack detected",
            mitre_techniques=["T1059.001"],
            recommended_actions=["Isolate host"],
        ),
        agent_trace=["TriageAgent", "AnalystAgent"],
        metadata={"timestamp": "2026-08-18T09:00:00Z"},
    )


# ---------------------------------------------------------------------------
# Webhook action against a real server
# ---------------------------------------------------------------------------


class TestWebhookE2E:
    @pytest.mark.asyncio
    async def test_webhook_delivers_real_http_post(self, mock_server, malicious_state):
        url, received = mock_server
        action = WebhookAction()

        ok = await action.execute(malicious_state, {"url": url})

        assert ok is True
        assert len(received) == 1, f"Server got {len(received)} requests, expected 1"

        request = received[0]
        assert request["path"] == "/"
        payload = json.loads(request["body"])

        # Verify full payload structure
        assert payload["action"] == "alert"
        assert payload["verdict"]["malicious"] is True
        assert payload["verdict"]["danger_level"] == 92
        assert payload["verdict"]["reason"] == "Encoded PowerShell attack detected"
        assert payload["rule_hits"][0]["rule_id"] == "sigma-ps-001"
        assert payload["rule_hits"][0]["confidence"] == 95
        assert payload["timestamp"] == "2026-08-18T09:00:00Z"

    @pytest.mark.asyncio
    async def test_webhook_to_dead_endpoint_degrades_gracefully(self, malicious_state):
        """Connection refused must return False, not raise."""
        action = WebhookAction()
        # Port 1 is reserved/unusable -> connection refused
        ok = await action.execute(malicious_state, {"url": "http://127.0.0.1:1/hook"})
        assert ok is False


# ---------------------------------------------------------------------------
# Slack action against a real server
# ---------------------------------------------------------------------------


class TestSlackE2E:
    @pytest.mark.asyncio
    async def test_slack_delivers_attachment_payload(self, mock_server, malicious_state):
        url, received = mock_server
        action = SlackAction()

        ok = await action.execute(malicious_state, {"webhook_url": url})

        assert ok is True
        assert len(received) == 1
        payload = json.loads(received[0]["body"])

        # Verify Slack attachment structure
        assert "attachments" in payload
        attachment = payload["attachments"][0]
        assert attachment["color"] == "danger"  # malicious -> red
        assert "Malicious" in attachment["title"]
        fields = {f["title"]: f["value"] for f in attachment["fields"]}
        assert fields["Danger Level"] == "92"
        assert "Encoded PowerShell" in fields["Reason"]

    @pytest.mark.asyncio
    async def test_slack_benign_uses_good_color(self, mock_server):
        url, received = mock_server
        state = IncidentState(
            log={"EventID": 1},
            verdict=Verdict(malicious=False, danger_level=3, reason="clean"),
        )
        action = SlackAction()
        ok = await action.execute(state, {"webhook_url": url})
        assert ok is True
        payload = json.loads(received[0]["body"])
        assert payload["attachments"][0]["color"] == "good"


# ---------------------------------------------------------------------------
# Script action with a real script on disk
# ---------------------------------------------------------------------------


class TestScriptE2E:
    @pytest.mark.asyncio
    async def test_script_executes_with_sentinel_env(self, tmp_path, malicious_state, monkeypatch):
        """Real script execution: verify env vars are passed and exit code honored."""
        script = tmp_path / "capture_env.sh"
        output_file = tmp_path / "env_capture.txt"
        script.write_text(
            "#!/bin/bash\n"
            f'echo "mal=$SENTINEL_MALICIOUS level=$SENTINEL_DANGER_LEVEL" > {output_file}\n'
            f'echo "reason=$SENTINEL_REASON" >> {output_file}\n'
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

        monkeypatch.setitem(ScriptAction.ALLOWED_SCRIPTS, "capture_env", str(script))

        action = ScriptAction()
        ok = await action.execute(malicious_state, {"script": "capture_env"})

        assert ok is True
        content = output_file.read_text()
        assert "mal=True" in content
        assert "level=92" in content
        assert "Encoded PowerShell attack detected" in content

    @pytest.mark.asyncio
    async def test_script_nonzero_exit_returns_false(self, tmp_path, malicious_state, monkeypatch):
        script = tmp_path / "fail.sh"
        script.write_text("#!/bin/bash\nexit 1\n")
        monkeypatch.setitem(ScriptAction.ALLOWED_SCRIPTS, "failer", str(script))

        action = ScriptAction()
        ok = await action.execute(malicious_state, {"script": "failer"})
        assert ok is False

    @pytest.mark.asyncio
    async def test_script_whitelist_blocks_arbitrary_path(self, malicious_state):
        """A script NOT in the whitelist must be rejected before any exec."""
        action = ScriptAction()
        ok = await action.execute(malicious_state, {"script": "/etc/passwd"})
        assert ok is False
        ok = await action.execute(malicious_state, {"script": "../../evil.sh"})
        assert ok is False
        ok = await action.execute(malicious_state, {"script": "rm_rf"})
        assert ok is False


# ---------------------------------------------------------------------------
# ResponseEngine end-to-end: rule hit -> actions fire -> failure degrades
# ---------------------------------------------------------------------------


class TestResponseEngineE2E:
    @pytest.mark.asyncio
    async def test_high_confidence_hit_triggers_enabled_actions(
        self, mock_server, malicious_state, monkeypatch
    ):
        """Full chain: confidence>=90 hit + SOAR_*_ENABLED=true -> real HTTP delivery."""
        url, received = mock_server
        monkeypatch.setenv("SOAR_WEBHOOK_ENABLED", "true")
        monkeypatch.setenv("SOAR_WEBHOOK_URL", url)
        monkeypatch.setenv("SOAR_SLACK_ENABLED", "true")
        monkeypatch.setenv("SLACK_WEBHOOK_URL", url)
        # Script action left disabled

        engine = ResponseEngine()
        results = await engine.execute_for_state(malicious_state)

        assert results.get("webhook") is True
        assert results.get("slack") is True
        assert "script" not in results  # disabled -> not executed

        # Both actions delivered real HTTP requests to the mock server
        assert len(received) == 2
        bodies = [json.loads(r["body"]) for r in received]
        # One is the webhook payload, one is the Slack payload
        actions_seen = {("alert" if b.get("action") == "alert" else "slack") for b in bodies}
        assert actions_seen == {"alert", "slack"}

    @pytest.mark.asyncio
    async def test_action_failure_does_not_block_others(
        self, mock_server, malicious_state, monkeypatch
    ):
        """Webhook dead + Slack alive: Slack must still fire, failures recorded."""
        url, received = mock_server
        monkeypatch.setenv("SOAR_WEBHOOK_ENABLED", "true")
        monkeypatch.setenv("SOAR_WEBHOOK_URL", "http://127.0.0.1:1/dead")
        monkeypatch.setenv("SOAR_SLACK_ENABLED", "true")
        monkeypatch.setenv("SLACK_WEBHOOK_URL", url)

        engine = ResponseEngine()
        results = await engine.execute_for_state(malicious_state)

        assert results.get("webhook") is False  # dead endpoint
        assert results.get("slack") is True  # still delivered
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_low_confidence_hit_triggers_nothing(self, monkeypatch):
        """confidence < 90 must not trigger any action."""
        monkeypatch.setenv("SOAR_WEBHOOK_ENABLED", "true")
        state = IncidentState(
            log={"EventID": 1},
            rule_hits=[
                RuleHit(
                    rule_id="r1",
                    rule_name="low conf",
                    technique="T1000",
                    confidence=50,
                    severity="low",
                    reason="weak signal",
                )
            ],
            verdict=Verdict(malicious=False, danger_level=10, reason="probably fine"),
        )
        engine = ResponseEngine()
        results = await engine.execute_for_state(state)
        assert results == {}

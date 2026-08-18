"""End-to-end SDK behavior tests over the real HTTP/ASGI stack."""

import json
from pathlib import Path

import pytest

from sentinel_sdk import (
    AnalysisResult,
    AuthError,
    ConflictError,
    Health,
    ImportStatus,
    NotFoundError,
    Rule,
    RuleList,
    Stats,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "logs"


# ----------------------------------------------------------------------
# health & login
# ----------------------------------------------------------------------


async def test_health(client):
    health = await client.health()
    assert isinstance(health, Health)
    assert health.status == "healthy"
    assert health.services["api"] == "up"


async def test_login_success_sets_token(client):
    token = await client.login("admin", "admin")
    assert token.access_token
    assert token.token_type == "bearer"
    assert client.token == token.access_token


async def test_login_wrong_password_raises_auth_error(client):
    with pytest.raises(AuthError) as exc_info:
        await client.login("admin", "wrong-password")
    assert exc_info.value.status_code == 401


async def test_authenticate_fluent(client):
    assert client.authenticate("some-token") is client
    assert client.token == "some-token"


# ----------------------------------------------------------------------
# auth header / error mapping
# ----------------------------------------------------------------------


async def test_missing_token_maps_to_auth_error(client):
    """Protected endpoint without a token: 401 -> AuthError."""
    with pytest.raises(AuthError) as exc_info:
        await client.get_stats()
    assert exc_info.value.status_code == 401


async def test_invalid_token_maps_to_auth_error(client):
    client.authenticate("not.a.valid.jwt")
    with pytest.raises(AuthError):
        await client.list_rules()


async def test_not_found_maps_to_not_found_error(admin_client):
    with pytest.raises(NotFoundError) as exc_info:
        await admin_client.get_rule("definitely-not-a-rule-id")
    assert exc_info.value.status_code == 404


async def test_conflict_maps_to_conflict_error(admin_client):
    rule = Rule(
        id="conflict-test-rule",
        title="Conflict test",
        logsource={"product": "test"},
        detection={"selection": {"a": "b"}, "condition": "selection"},
    )
    await admin_client.create_rule(rule)
    with pytest.raises(ConflictError) as exc_info:
        await admin_client.create_rule(rule)
    assert exc_info.value.status_code == 409
    await admin_client.delete_rule("conflict-test-rule")


# ----------------------------------------------------------------------
# analyze round-trip
# ----------------------------------------------------------------------


async def test_analyze_round_trip(admin_client):
    log = json.loads((EXAMPLES / "mimikatz_detection.json").read_text())
    result = await admin_client.analyze(log)
    assert isinstance(result, AnalysisResult)
    assert result.verdict is not None
    # mimikatz sample hits a high-confidence rule -> skipped_llm fast path
    assert result.verdict["malicious"] is True
    assert result.skipped_llm is True
    assert result.rule_hits
    assert "TriageAgent" in result.agent_trace


async def test_analyze_batch_round_trip(admin_client):
    logs = [
        json.loads((EXAMPLES / "mimikatz_detection.json").read_text()),
        json.loads((EXAMPLES / "benign_chrome.json").read_text()),
    ]
    result = await admin_client.analyze_batch(logs)
    assert result.total == 2
    assert result.successful + result.failed == 2


# ----------------------------------------------------------------------
# rules round-trip
# ----------------------------------------------------------------------


async def test_rules_full_lifecycle(admin_client):
    listed = await admin_client.list_rules()
    assert isinstance(listed, RuleList)
    assert listed.total > 0
    first = listed.rules[0]

    fetched = await admin_client.get_rule(first.id)
    assert fetched.id == first.id
    assert fetched.detection

    new_rule = Rule(
        id="sdk-lifecycle-rule",
        title="SDK lifecycle test rule",
        description="created by sdk tests",
        level="high",
        logsource={"product": "windows", "category": "process_creation"},
        detection={
            "selection": {"Image|endswith": "\\sdk_test.exe"},
            "condition": "selection",
        },
        tags=["attack.execution"],
    )
    created = await admin_client.create_rule(new_rule)
    assert created["status"] == "created"

    got = await admin_client.get_rule("sdk-lifecycle-rule")
    assert got.title == "SDK lifecycle test rule"
    assert got.level == "high"

    updated = await admin_client.update_rule("sdk-lifecycle-rule", new_rule)
    assert updated["status"] == "updated"

    deleted = await admin_client.delete_rule("sdk-lifecycle-rule")
    assert deleted["status"] == "deleted"

    with pytest.raises(NotFoundError):
        await admin_client.get_rule("sdk-lifecycle-rule")

    reloaded = await admin_client.reload_rules()
    assert reloaded["status"] == "reloaded"
    assert reloaded["count"] > 0


# ----------------------------------------------------------------------
# stats / settings
# ----------------------------------------------------------------------


async def test_stats_and_settings(admin_client):
    stats = await admin_client.get_stats()
    assert isinstance(stats, Stats)

    costs = await admin_client.llm_costs()
    assert isinstance(costs, dict)

    settings = await admin_client.get_settings()
    assert "llm_model" in settings


# ----------------------------------------------------------------------
# bulk import + polling
# ----------------------------------------------------------------------


async def test_import_logs_and_poll(admin_client, tmp_path):
    jsonl = tmp_path / "batch.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"EventID": 4688, "Image": "powershell.exe"},
                {"EventID": 4624, "Image": "svchost.exe"},
            ]
        )
        + "\n"
    )
    task = await admin_client.import_logs(jsonl)
    assert isinstance(task, ImportStatus)
    assert task.task_id
    assert task.status in ("pending", "processing", "completed")

    final = await admin_client.poll_import(task.task_id, wait=True,
                                           interval=0.05, timeout=30)
    assert final.status == "completed"
    assert final.processed == 2
    assert final.total == 2


async def test_import_status_no_wait(admin_client, tmp_path):
    f = tmp_path / "one.jsonl"
    f.write_text(json.dumps({"EventID": 1}) + "\n")
    task = await admin_client.import_logs(f)
    status = await admin_client.poll_import(task.task_id, wait=False)
    assert status.task_id == task.task_id


async def test_import_unknown_task_is_not_found(admin_client):
    with pytest.raises(NotFoundError):
        await admin_client.import_status("no-such-task-id")


# ----------------------------------------------------------------------
# privacy (admin role required)
# ----------------------------------------------------------------------


async def test_privacy_export_and_delete(admin_client):
    exported = await admin_client.export_privacy("admin")
    assert exported["subject"] == "admin"
    assert "record_count" in exported

    deleted = await admin_client.delete_privacy("sdk-tests-subject")
    assert deleted["status"] == "erased"

"""LLM cost endpoint test."""

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.main import app

client = TestClient(app)
TOKEN = create_access_token("stats_user")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_llm_costs_endpoint_structure():
    resp = client.get("/api/v1/stats/llm-costs", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "total_calls",
        "total_tokens",
        "total_prompt_tokens",
        "total_completion_tokens",
        "estimated_cost_usd",
        "calls_by_model",
        "tokens_by_model",
    ):
        assert key in body
    assert isinstance(body["total_calls"], int)
    assert isinstance(body["calls_by_model"], dict)
    assert isinstance(body["estimated_cost_usd"], (int, float))


def test_llm_costs_requires_auth():
    assert client.get("/api/v1/stats/llm-costs").status_code == 401


def test_llm_costs_aggregates_recorded_usage():
    from sentinel_agents.llm.cost_tracker import TokenUsage, get_cost_tracker

    tracker = get_cost_tracker()
    tracker.reset()
    tracker.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, model="gpt-4o"))
    tracker.record(TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, model="llama3"))

    resp = client.get("/api/v1/stats/llm-costs", headers=HEADERS)
    body = resp.json()
    assert body["total_calls"] == 2
    assert body["total_tokens"] == 165
    assert body["calls_by_model"]["gpt-4o"] == 1
    assert body["calls_by_model"]["llama3"] == 1
    assert body["estimated_cost_usd"] > 0  # gpt-4o has nonzero pricing
    tracker.reset()

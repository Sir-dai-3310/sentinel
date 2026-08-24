"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.jwt import create_access_token
from app.main import app
from app.routers import analysis as analysis_router
from app.routers import health as health_router
from sentinel_agents.state import IncidentState

client = TestClient(app)

# Create a test JWT token
TEST_TOKEN = create_access_token("test_user", roles=["analyst"])
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_health_endpoint(monkeypatch):
    """Test health check endpoint."""

    async def database_is_ready():
        return True

    monkeypatch.setattr(health_router, "database_is_ready", database_is_ready)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "healthy",
        "version": "1.2.0",
        "services": {"api": "up", "database": "up"},
    }


def test_health_endpoint_reports_database_failure(monkeypatch):
    async def database_is_ready():
        return False

    monkeypatch.setattr(health_router, "database_is_ready", database_is_ready)
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "version": "1.2.0",
        "services": {"api": "up", "database": "down"},
    }


def test_liveness_endpoint_does_not_probe_database(monkeypatch):
    async def database_is_ready():
        raise AssertionError("liveness must not access the database")

    monkeypatch.setattr(health_router, "database_is_ready", database_is_ready)
    response = client.get("/api/v1/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "version": "1.2.0",
        "services": {"api": "up"},
    }


def test_readiness_endpoint_reports_database_failure(monkeypatch):
    async def database_is_ready():
        return False

    monkeypatch.setattr(health_router, "database_is_ready", database_is_ready)
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["services"]["database"] == "down"


def test_health_endpoint_includes_request_id():
    response = client.get("/api/v1/live")
    request_id = response.headers.get("x-request-id")
    assert request_id
    assert len(request_id) == 36


@pytest.mark.asyncio
async def test_database_health_check_executes_probe(monkeypatch):
    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def execute(self, statement):
            assert str(statement) == "SELECT 1"

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(health_router, "engine", Engine())
    assert await health_router.database_is_ready() is True


@pytest.mark.asyncio
async def test_database_health_check_reports_probe_failure(monkeypatch):
    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def execute(self, statement):
            raise RuntimeError("database unavailable")

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(health_router, "engine", Engine())
    assert await health_router.database_is_ready() is False


def test_analyze_endpoint_requires_auth():
    """Test analyze endpoint requires authentication."""
    response = client.post(
        "/api/v1/analyze",
        json={
            "log": {
                "EventID": 1,
                "Image": "powershell.exe",
                "CommandLine": "powershell -enc test",
            }
        },
    )

    # Should return 401 without auth token
    assert response.status_code == 401


def test_analyze_endpoint_with_auth():
    """Test analyze endpoint with valid auth token."""
    response = client.post(
        "/api/v1/analyze",
        json={
            "log": {
                "EventID": 1,
                "Image": "powershell.exe",
                "CommandLine": "powershell -enc test",
            }
        },
        headers=AUTH_HEADERS,
    )

    # Should return 200 or 500 (if LLM not configured)
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "verdict" in data
        assert "rule_hits" in data
        assert "agent_trace" in data
        assert "analysis_status" in data
    else:
        assert "detail" in response.json()


def test_analyze_endpoint_returns_explicit_llm_failure(monkeypatch):
    async def failed_analysis(log):
        return IncidentState(
            log=log,
            analysis_status="failed",
            analysis_error="LLM analysis unavailable; manual review required.",
        )

    monkeypatch.setattr(analysis_router, "analyze_log", failed_analysis)
    response = client.post(
        "/api/v1/analyze",
        json={"log": {"EventID": 1}},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] is None
    assert data["analysis_status"] == "failed"
    assert data["analysis_error"] == "LLM analysis unavailable; manual review required."


def test_analyze_batch_counts_llm_failures(monkeypatch):
    async def mixed_analysis(log):
        if log["EventID"] == 1:
            return IncidentState(
                log=log,
                analysis_status="failed",
                analysis_error="LLM analysis unavailable; manual review required.",
            )
        return IncidentState(
            log=log,
            analysis_status="completed",
        )

    monkeypatch.setattr(analysis_router, "analyze_log", mixed_analysis)
    response = client.post(
        "/api/v1/analyze/batch",
        json={"logs": [{"EventID": 1}, {"EventID": 2}]},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1
    assert data["results"][0]["success"] is False
    assert data["results"][0]["verdict"] is None
    assert data["results"][0]["analysis_status"] == "failed"
    assert data["results"][1]["success"] is True
    assert data["results"][1]["analysis_status"] == "completed"


def test_analyze_endpoint_invalid_input():
    """Test analyze endpoint rejects invalid input."""
    response = client.post(
        "/api/v1/analyze",
        json={"invalid": "data"},
        headers=AUTH_HEADERS,
    )

    # Should return 422 (validation error)
    assert response.status_code == 422


def test_rules_list_endpoint():
    """Test rules listing endpoint."""
    response = client.get("/api/v1/rules", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "rules" in data
    assert isinstance(data["rules"], list)


def test_rules_list_requires_auth():
    """Test rules listing requires authentication."""
    response = client.get("/api/v1/rules")
    assert response.status_code == 401


def test_metrics_endpoint_exposes_http_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


def test_metrics_endpoint_exposes_engine_metrics(monkeypatch):
    import sys
    import types

    fake_core = types.ModuleType("sentinel_core")

    def metrics_text():
        return "# TYPE sentinel_evaluations_total counter\nsentinel_evaluations_total 7\n"

    fake_core.metrics_text = metrics_text
    monkeypatch.setitem(sys.modules, "sentinel_core", fake_core)
    try:
        response = client.get("/metrics")
    finally:
        monkeypatch.delitem(sys.modules, "sentinel_core")
    assert response.status_code == 200
    assert "sentinel_evaluations_total 7" in response.text
    assert "http_requests_total" in response.text

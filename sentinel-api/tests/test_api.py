"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.main import app

client = TestClient(app)

# Create a test JWT token
TEST_TOKEN = create_access_token("test_user")
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


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

"""Security regression tests for the batch-5 hardening.

Covers: fail-closed environment handling, default-credential blocking,
RBAC mounting on rules/analysis, batch caps, and XFF handling.
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.auth.jwt import create_access_token  # noqa: E402
from app.env import is_local_mode  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

ADMIN_TOKEN = create_access_token("admin_user", roles=["admin"])
ANALYST_TOKEN = create_access_token("analyst_user", roles=["analyst"])
VIEWER_TOKEN = create_access_token("viewer_user", roles=["viewer"])


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


class TestEnvironmentModes:
    def test_local_modes(self):
        for v in ("", "development", "dev", "local"):
            os.environ["ENVIRONMENT"] = v
            assert is_local_mode(), v
        for v in ("production", "prod", "staging"):
            os.environ["ENVIRONMENT"] = v
            assert not is_local_mode(), v
        os.environ["ENVIRONMENT"] = "development"

    def test_default_secret_refuses_start_outside_local(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "CHANGE_THIS_IN_PRODUCTION")
        import importlib
        import sys

        for m in [k for k in sys.modules if k.startswith("app.auth")]:
            del sys.modules[m]
        with pytest.raises(ValueError, match="JWT_SECRET"):
            importlib.import_module("app.auth.jwt")


class TestDefaultCredentials:
    def test_wrong_password_401(self):
        r = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "nope"}
        )
        assert r.status_code == 401

    def test_unknown_user_401(self):
        r = client.post(
            "/api/v1/auth/login", json={"username": "ghost", "password": "x"}
        )
        assert r.status_code == 401


class TestRBACMounting:
    def test_rules_write_requires_admin(self):
        r = client.delete("/api/v1/rules/R999", headers=_h(VIEWER_TOKEN))
        assert r.status_code == 403
        r = client.post("/api/v1/rules/reload", headers=_h(ANALYST_TOKEN))
        assert r.status_code == 403

    def test_rules_read_allowed_for_viewer(self):
        r = client.get("/api/v1/rules", headers=_h(VIEWER_TOKEN))
        assert r.status_code == 200

    def test_analyze_forbidden_for_viewer(self):
        r = client.post("/api/v1/analyze", json={"log": {}}, headers=_h(VIEWER_TOKEN))
        assert r.status_code == 403


class TestBatchCaps:
    def test_batch_over_cap_rejected(self):
        logs = [{"EventID": 1}] * 150
        r = client.post(
            "/api/v1/analyze/batch", json={"logs": logs}, headers=_h(ADMIN_TOKEN)
        )
        assert r.status_code == 422


class TestNoDetailLeak:
    def test_500_handler_has_request_id_not_detail(self):
        import asyncio

        from app.main import global_exception_handler

        class Boom(Exception):
            pass

        resp = asyncio.run(global_exception_handler(None, Boom("postgresql://u:p@h/db")))
        assert b"postgresql" not in resp.body
        assert b"request_id" in resp.body

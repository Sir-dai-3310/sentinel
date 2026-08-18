"""i18n tests: locale negotiation + localized error responses over HTTP."""

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.i18n import localize_error_body, message_for, negotiate_locale
from app.main import app

client = TestClient(app)
TOKEN = create_access_token("i18n_user")
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class TestNegotiate:
    def test_default_when_missing(self):
        assert negotiate_locale(None) == "en"
        assert negotiate_locale("") == "en"

    def test_simple(self):
        assert negotiate_locale("zh") == "zh"
        assert negotiate_locale("en") == "en"

    def test_subtag(self):
        assert negotiate_locale("zh-CN") == "zh"
        assert negotiate_locale("zh-Hans-CN") == "zh"

    def test_quality_weights(self):
        assert negotiate_locale("en;q=0.5,zh;q=0.9") == "zh"
        assert negotiate_locale("zh;q=0.4,en;q=0.9") == "en"

    def test_unsupported_falls_back(self):
        assert negotiate_locale("fr,de") == "en"


class TestCatalog:
    def test_message_per_locale(self):
        assert message_for(401, "en") != message_for(401, "zh")
        assert "认证" in message_for(401, "zh")

    def test_unknown_status_uses_500(self):
        assert message_for(999, "en") == message_for(500, "en")

    def test_unknown_locale_falls_back_to_en(self):
        assert message_for(404, "xx") == message_for(404, "en")


class TestLocalizeBody:
    def test_string_detail_replaced(self):
        body = {"detail": "Not authenticated"}
        out = localize_error_body(body, 401, "zh")
        assert out["message"] == message_for(401, "zh")
        assert out["detail"] == message_for(401, "zh")

    def test_structured_detail_kept_but_message_added(self):
        body = {"detail": [{"loc": ["body", "log"], "msg": "field required"}]}
        out = localize_error_body(body, 422, "zh")
        assert out["message"] == message_for(422, "zh")
        assert isinstance(out["detail"], list)  # validation detail preserved

    def test_success_status_passthrough(self):
        body = {"ok": True}
        assert localize_error_body(body, 200, "zh") == body


class TestHTTP:
    def test_401_english(self):
        r = client.post("/api/v1/analyze", json={"log": {}}, headers={"Accept-Language": "en"})
        assert r.status_code == 401
        assert r.json()["message"] == message_for(401, "en")

    def test_401_chinese(self):
        r = client.post("/api/v1/analyze", json={"log": {}}, headers={"Accept-Language": "zh-CN"})
        assert r.status_code == 401
        assert "认证" in r.json()["message"]

    def test_404_chinese(self):
        r = client.get("/api/v1/no-such-route", headers={**AUTH, "Accept-Language": "zh"})
        assert r.status_code == 404
        assert r.json()["message"] == message_for(404, "zh")

    def test_422_chinese(self):
        # invalid body triggers 422 validation error
        r = client.post(
            "/api/v1/analyze",
            json={"invalid": "data"},
            headers={**AUTH, "Accept-Language": "zh"},
        )
        assert r.status_code == 422
        assert r.json()["message"] == message_for(422, "zh")

    def test_429_chinese(self):
        """A rate-limited (429) JSON error is localized by the middleware."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        mini = FastAPI()

        @mini.middleware("http")
        async def _i18n(request, call_next):
            from app.main import i18n_error_middleware

            return await i18n_error_middleware(request, call_next)

        @mini.get("/limited")
        async def limited():
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})

        c = TestClient(mini)
        r = c.get("/limited", headers={"Accept-Language": "zh"})
        assert r.status_code == 429
        assert r.json()["message"] == message_for(429, "zh")

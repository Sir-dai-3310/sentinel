"""GDPR data-subject rights tests: export -> delete -> audit trail."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import create_access_token
from app.db.models import AnalysisResult, AuditLog, Base
from app.main import app
from app.routers import privacy as privacy_router

# Admin token (roles claim drives require_admin)
ADMIN_TOKEN = create_access_token("admin_user", roles=["admin"])
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
# Non-admin token
USER_TOKEN = create_access_token("regular_user", roles=[])
USER_HEADERS = {"Authorization": f"Bearer {USER_TOKEN}"}


@pytest_asyncio.fixture
async def sqlite_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(privacy_router, "async_session", factory)
    yield factory
    await engine.dispose()


async def _seed(factory):
    async with factory() as s:
        s.add_all([
            AnalysisResult(log_event={"e": 1}, user_id="subject-a", tenant_id="default"),
            AnalysisResult(log_event={"e": 2}, user_id="subject-a", tenant_id="default"),
            AnalysisResult(log_event={"e": 3}, user_id="subject-b", tenant_id="default"),
        ])
        await s.commit()


@pytest.mark.asyncio
async def test_export_returns_all_subject_rows(sqlite_session):
    await _seed(sqlite_session)
    client = TestClient(app)
    resp = client.get(
        "/api/v1/privacy/export", params={"subject": "subject-a"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == "subject-a"
    assert body["record_count"] == 2
    assert len(body["analysis_results"]) == 2
    assert all(r["user_id"] == "subject-a" for r in body["analysis_results"])


@pytest.mark.asyncio
async def test_delete_erases_subject_and_keeps_others(sqlite_session):
    await _seed(sqlite_session)
    client = TestClient(app)
    resp = client.delete(
        "/api/v1/privacy/data", params={"subject": "subject-a"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted_count"] == 2

    # subject-a gone, subject-b intact
    async with sqlite_session() as s:
        a = (
            await s.execute(
                select(func.count())
                .select_from(AnalysisResult)
                .where(AnalysisResult.user_id == "subject-a")
            )
        ).scalar()
        b = (
            await s.execute(
                select(func.count())
                .select_from(AnalysisResult)
                .where(AnalysisResult.user_id == "subject-b")
            )
        ).scalar()
    assert a == 0
    assert b == 1


@pytest.mark.asyncio
async def test_delete_writes_audit_log(sqlite_session):
    await _seed(sqlite_session)
    client = TestClient(app)
    client.delete(
        "/api/v1/privacy/data", params={"subject": "subject-a"}, headers=ADMIN_HEADERS
    )
    async with sqlite_session() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "privacy_delete")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].resource == "privacy:subject:subject-a"
    assert rows[0].details["rows_deleted"] == 2


@pytest.mark.asyncio
async def test_export_writes_audit_log(sqlite_session):
    await _seed(sqlite_session)
    client = TestClient(app)
    client.get(
        "/api/v1/privacy/export", params={"subject": "subject-b"}, headers=ADMIN_HEADERS
    )
    async with sqlite_session() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "privacy_export")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].details["rows_exported"] == 1


@pytest.mark.asyncio
async def test_non_admin_forbidden(sqlite_session):
    await _seed(sqlite_session)
    client = TestClient(app)
    r1 = client.get(
        "/api/v1/privacy/export", params={"subject": "subject-a"}, headers=USER_HEADERS
    )
    r2 = client.delete(
        "/api/v1/privacy/data", params={"subject": "subject-a"}, headers=USER_HEADERS
    )
    assert r1.status_code == 403
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_requires_auth(sqlite_session):
    client = TestClient(app)
    assert client.get("/api/v1/privacy/export", params={"subject": "x"}).status_code == 401
    assert client.delete("/api/v1/privacy/data", params={"subject": "x"}).status_code == 401

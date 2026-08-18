"""Verify analysis results are masked BEFORE persistence (store-masked)."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import User
from app.db.models import AnalysisResult, Base
from app.routers import analysis as analysis_router
from sentinel_agents.state import IncidentState, Verdict


@pytest_asyncio.fixture
async def sqlite_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # Point the analysis router's session factory at SQLite
    import app.db.session as db_session_mod

    monkeypatch.setattr(db_session_mod, "async_session", factory)
    # The router imported async_session by name; patch that reference too.
    monkeypatch.setattr(analysis_router, "async_session", factory, raising=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_masks_log_event(sqlite_session, monkeypatch):
    """With masking enabled, the stored log_event must be masked."""
    from sentinel_agents.utils import masking

    cfg_rules = [
        {"path": "user.name", "strategy": "redact"},
        {"path": "source.ip", "strategy": "partial"},
    ]
    masking.reset_masker()
    monkeypatch.setenv("MASKING_ENABLED", "true")
    # Inject a configured masker directly (bypasses yaml file lookup).
    monkeypatch.setattr(masking, "_MASKER", Masker_for_test(cfg_rules))
    monkeypatch.setattr(masking, "_LOADED", True)

    log = {
        "EventID": 1,
        "user": {"name": "alice.smith"},
        "source": {"ip": "203.0.113.99"},
    }
    state = IncidentState(log=log)
    state.verdict = Verdict(malicious=True, danger_level=80, reason="test")
    user = User(username="analyst1", tenant_id="default")

    await analysis_router._persist_result(log, state, user)

    async with sqlite_session() as s:
        row = (await s.execute(select(AnalysisResult))).scalar_one()

    assert row.log_event["user"]["name"] == "***"
    assert row.log_event["source"]["ip"] == "203.0.***.***"
    assert row.user_id == "analyst1"
    assert row.malicious is True
    masking.reset_masker()


@pytest.mark.asyncio
async def test_persist_passthrough_when_masking_off(sqlite_session, monkeypatch):
    """With masking disabled (default), the payload persists unchanged."""
    from sentinel_agents.utils import masking

    masking.reset_masker()
    monkeypatch.delenv("MASKING_ENABLED", raising=False)

    log = {"EventID": 2, "user": {"name": "bob"}, "source": {"ip": "8.8.8.8"}}
    state = IncidentState(log=log)
    state.verdict = Verdict(malicious=False, danger_level=5, reason="benign")
    user = User(username="analyst2", tenant_id="default")

    await analysis_router._persist_result(log, state, user)

    async with sqlite_session() as s:
        row = (await s.execute(select(AnalysisResult))).scalar_one()

    assert row.log_event["user"]["name"] == "bob"
    assert row.log_event["source"]["ip"] == "8.8.8.8"
    masking.reset_masker()


def Masker_for_test(rules):
    from sentinel_agents.utils.masking import Masker

    return Masker(rules=rules, enabled=True)

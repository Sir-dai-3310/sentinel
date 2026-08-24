from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import create_access_token
from app.db.models import AnalysisResult, Base, RuleMetadata
from app.main import app
from app.routers import stats as stats_router


@pytest_asyncio.fixture
async def sqlite_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(stats_router, "async_session", factory)
    monkeypatch.setenv("MULTI_TENANT_ENABLED", "true")
    yield factory
    await engine.dispose()


async def seed_dashboard_data(factory):
    now = datetime.utcnow()
    async with factory() as session:
        session.add_all(
            [
                AnalysisResult(
                    tenant_id="acme",
                    created_at=now,
                    log_event={"event": 1},
                    malicious=True,
                    danger_level=95,
                    mitre_techniques=["T1059.001"],
                    rule_hits=[
                        {
                            "rule_id": "R001",
                            "rule_name": "PowerShell Encoded Command",
                            "technique": "T1059.001",
                        }
                    ],
                ),
                AnalysisResult(
                    tenant_id="acme",
                    created_at=now - timedelta(days=1),
                    log_event={"event": 2},
                    malicious=False,
                    danger_level=10,
                    rule_hits=[],
                ),
                AnalysisResult(
                    tenant_id="globex",
                    created_at=now,
                    log_event={"event": 3},
                    malicious=True,
                    danger_level=99,
                    rule_hits=[
                        {
                            "rule_id": "R999",
                            "rule_name": "Other Tenant Rule",
                            "technique": "T1003",
                        }
                    ],
                ),
                RuleMetadata(
                    rule_id="R001",
                    title="PowerShell Encoded Command",
                    level="high",
                    file_path="execution/powershell_encoded.yml",
                    tags=["attack.execution", "attack.t1059.001"],
                ),
            ]
        )
        await session.commit()


def headers(tenant: str):
    token = create_access_token(f"{tenant}-user", tenant_id=tenant, roles=["analyst"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_dashboard_stats_are_real_and_tenant_scoped(sqlite_session):
    await seed_dashboard_data(sqlite_session)
    client = TestClient(app)

    response = client.get("/api/v1/stats", headers=headers("acme"))

    assert response.status_code == 200
    assert response.json() == {
        "total_events": 2,
        "alerts": 1,
        "critical": 1,
        "accuracy": 1.0,
    }

    response = client.get("/api/v1/stats", headers=headers("globex"))
    assert response.json()["total_events"] == 1
    assert response.json()["alerts"] == 1
    assert response.json()["critical"] == 1


@pytest.mark.asyncio
async def test_dashboard_trend_rule_hits_and_tactics(sqlite_session):
    await seed_dashboard_data(sqlite_session)
    client = TestClient(app)

    trend = client.get("/api/v1/stats/threat-trend", headers=headers("acme"))
    assert trend.status_code == 200
    assert len(trend.json()) == 7
    assert trend.json()[-1]["threats"] == 1

    rule_hits = client.get("/api/v1/stats/rule-hits", headers=headers("acme"))
    assert rule_hits.json() == [{"rule_name": "PowerShell Encoded Command", "count": 1}]

    tactics = client.get("/api/v1/stats/attack-tactics", headers=headers("acme"))
    assert tactics.json() == [{"tactic": "execution", "count": 1}]

    globex_hits = client.get("/api/v1/stats/rule-hits", headers=headers("globex"))
    assert globex_hits.json() == [{"rule_name": "Other Tenant Rule", "count": 1}]


@pytest.mark.asyncio
async def test_dashboard_stats_require_auth(sqlite_session):
    client = TestClient(app)
    for path in (
        "/api/v1/stats",
        "/api/v1/stats/threat-trend",
        "/api/v1/stats/rule-hits",
        "/api/v1/stats/attack-tactics",
    ):
        assert client.get(path).status_code == 401

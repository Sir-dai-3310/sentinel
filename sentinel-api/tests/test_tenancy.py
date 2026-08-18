"""Multi-tenancy tests: JWT claims, resolution logic, and REAL data isolation.

Data isolation is verified against a real (in-memory) SQLite database using
the actual models and tenant_filter — not mocks.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import create_access_token, get_current_user, verify_token
from app.db.models import AnalysisResult, AuditLog, Base, Tenant
from app.tenancy import (
    DEFAULT_TENANT,
    multi_tenant_enabled,
    resolve_tenant_id,
    tenant_filter,
)


# ---------------------------------------------------------------------------
# JWT tenant claims
# ---------------------------------------------------------------------------


class TestJWTTenantClaims:
    def test_token_embeds_tenant_and_roles(self):
        token = create_access_token("alice", tenant_id="acme-corp", roles=["admin"])
        data = verify_token(token)
        assert data.sub == "alice"
        assert data.tenant == "acme-corp"
        assert data.roles == ["admin"]

    def test_token_defaults_when_no_tenant(self):
        token = create_access_token("bob")
        data = verify_token(token)
        assert data.tenant == DEFAULT_TENANT
        assert data.roles == []

    @pytest.mark.asyncio
    async def test_get_current_user_populates_tenant(self):
        token = create_access_token("carol", tenant_id="globex", roles=["analyst"])

        class Cred:
            credentials = token

        user = await get_current_user(Cred())
        assert user.username == "carol"
        assert user.tenant_id == "globex"
        assert user.roles == ["analyst"]


# ---------------------------------------------------------------------------
# Tenant resolution (single vs multi tenant mode)
# ---------------------------------------------------------------------------


class TestTenantResolution:
    def test_single_tenant_mode_collapses_to_default(self, monkeypatch):
        monkeypatch.setenv("MULTI_TENANT_ENABLED", "false")
        user = make_user(tenant_id="acme-corp")
        assert multi_tenant_enabled() is False
        assert resolve_tenant_id(user) == DEFAULT_TENANT

    def test_multi_tenant_mode_uses_jwt_claim(self, monkeypatch):
        monkeypatch.setenv("MULTI_TENANT_ENABLED", "true")
        user = make_user(tenant_id="acme-corp")
        assert multi_tenant_enabled() is True
        assert resolve_tenant_id(user) == "acme-corp"

    def test_empty_claim_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MULTI_TENANT_ENABLED", "true")
        user = make_user(tenant_id="")
        assert resolve_tenant_id(user) == DEFAULT_TENANT


def make_user(tenant_id: str = "default", roles: list[str] | None = None):
    from app.auth.jwt import User

    return User(username="tester", tenant_id=tenant_id, roles=roles or [])


# ---------------------------------------------------------------------------
# REAL data isolation against SQLite
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite with the real models."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_two_tenants(session):
    """Insert analysis results + audit logs for two tenants."""
    session.add_all([
        AnalysisResult(log_event={"e": 1}, malicious=True, danger_level=90, tenant_id="acme"),
        AnalysisResult(log_event={"e": 2}, malicious=False, danger_level=10, tenant_id="acme"),
        AnalysisResult(log_event={"e": 3}, malicious=True, danger_level=95, tenant_id="globex"),
        AuditLog(action="analyze", user_id="alice", tenant_id="acme"),
        AuditLog(action="analyze", user_id="bob", tenant_id="globex"),
        AuditLog(action="login", user_id="bob", tenant_id="globex"),
    ])
    await session.commit()


class TestDataIsolation:
    @pytest.mark.asyncio
    async def test_analysis_results_isolated_per_tenant(self, db_session):
        await _seed_two_tenants(db_session)

        # Query as acme: must see only acme's 2 rows
        stmt = tenant_filter(select(AnalysisResult), AnalysisResult, "acme")
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 2
        assert all(r.tenant_id == "acme" for r in rows)

        # Query as globex: must see only globex's 1 row
        stmt = tenant_filter(select(AnalysisResult), AnalysisResult, "globex")
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == "globex"
        assert rows[0].danger_level == 95

    @pytest.mark.asyncio
    async def test_audit_logs_isolated_per_tenant(self, db_session):
        await _seed_two_tenants(db_session)

        stmt = tenant_filter(select(AuditLog), AuditLog, "globex")
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 2
        assert {r.action for r in rows} == {"analyze", "login"}

        stmt = tenant_filter(select(AuditLog), AuditLog, "acme")
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_count_aggregation_respects_tenant(self, db_session):
        await _seed_two_tenants(db_session)

        stmt = tenant_filter(
            select(func.count()).select_from(AnalysisResult), AnalysisResult, "acme"
        )
        count = (await db_session.execute(stmt)).scalar()
        assert count == 2

        # A nonexistent tenant sees zero
        stmt = tenant_filter(
            select(func.count()).select_from(AnalysisResult), AnalysisResult, "no-such-tenant"
        )
        count = (await db_session.execute(stmt)).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_cross_tenant_write_visible_only_to_owner(self, db_session):
        """A row written by tenant A must not appear in tenant B's queries."""
        db_session.add(
            AnalysisResult(
                log_event={"secret": "acme-only"},
                malicious=True,
                danger_level=99,
                tenant_id="acme",
            )
        )
        await db_session.commit()

        stmt = tenant_filter(select(AnalysisResult), AnalysisResult, "globex")
        rows = (await db_session.execute(stmt)).scalars().all()
        assert all("acme-only" not in str(r.log_event) for r in rows)

    @pytest.mark.asyncio
    async def test_default_tenant_rows_hidden_from_named_tenant(self, db_session):
        """Legacy rows (tenant_id=default) must not leak into named tenants."""
        db_session.add(
            AnalysisResult(log_event={"legacy": True}, malicious=False, danger_level=1)
        )
        await db_session.commit()

        # Default value applied
        stmt = select(AnalysisResult)
        row = (await db_session.execute(stmt)).scalars().first()
        assert row.tenant_id == "default"

        # Named tenant sees nothing
        stmt = tenant_filter(select(AnalysisResult), AnalysisResult, "acme")
        assert (await db_session.execute(stmt)).scalars().all() == []


class TestTenantModel:
    @pytest.mark.asyncio
    async def test_tenant_crud(self, db_session):
        tenant = Tenant(slug="acme-corp", name="Acme Corporation")
        db_session.add(tenant)
        await db_session.commit()

        result = await db_session.execute(select(Tenant).where(Tenant.slug == "acme-corp"))
        fetched = result.scalar_one()
        assert fetched.name == "Acme Corporation"
        assert fetched.active is True

        # Disable
        fetched.active = False
        await db_session.commit()
        result = await db_session.execute(
            select(Tenant).where(Tenant.slug == "acme-corp", Tenant.active.is_(True))
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_tenant_slug_unique(self, db_session):
        db_session.add(Tenant(slug="acme", name="A"))
        await db_session.commit()
        db_session.add(Tenant(slug="acme", name="A2"))
        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()


# ---------------------------------------------------------------------------
# require_admin dependency
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.tenancy import require_admin

        user = make_user(roles=["admin"])
        assert await _call(require_admin, user) is user

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self):
        from fastapi import HTTPException

        from app.tenancy import require_admin

        with pytest.raises(HTTPException) as exc:
            await _call(require_admin, make_user(roles=["analyst"]))
        assert exc.value.status_code == 403


async def _call(fn, *args):
    """Support calling sync or async dependency functions."""
    import inspect

    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result

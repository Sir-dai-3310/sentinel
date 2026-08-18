"""Retention sweep tests against a real in-memory SQLite database."""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import AnalysisResult, AuditLog, Base
from app import retention


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


def _seed(session, now):
    """Insert a mix of expired and fresh rows for both tables."""
    old_analysis = now - timedelta(days=45)
    fresh_analysis = now - timedelta(days=5)
    old_audit = now - timedelta(days=120)
    fresh_audit = now - timedelta(days=10)
    session.add_all([
        AnalysisResult(log_event={"e": "old"}, created_at=old_analysis),
        AnalysisResult(log_event={"e": "fresh"}, created_at=fresh_analysis),
        AuditLog(action="old_login", user_id="u1", timestamp=old_audit),
        AuditLog(action="fresh_login", user_id="u2", timestamp=fresh_audit),
    ])


class TestPurgeExpiredAnalysis:
    @pytest.mark.asyncio
    async def test_deletes_only_expired_rows(self, db_session):
        now = datetime.utcnow()
        _seed(db_session, now)
        await db_session.commit()

        deleted = await retention.purge_expired_analysis(
            db_session, retention_days=30, now=now
        )
        assert deleted == 1

        remaining = (await db_session.execute(select(AnalysisResult))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].log_event == {"e": "fresh"}

    @pytest.mark.asyncio
    async def test_respects_custom_window(self, db_session):
        now = datetime.utcnow()
        _seed(db_session, now)
        await db_session.commit()

        # A 3-day window expires BOTH rows (5 and 45 days old)
        deleted = await retention.purge_expired_analysis(
            db_session, retention_days=3, now=now
        )
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_zero_window_keeps_nothing_expired(self, db_session):
        now = datetime.utcnow()
        db_session.add(
            AnalysisResult(log_event={"e": "now"}, created_at=now)
        )
        await db_session.commit()
        deleted = await retention.purge_expired_analysis(
            db_session, retention_days=0, now=now
        )
        assert deleted == 0


class TestPurgeExpiredAuditLogs:
    @pytest.mark.asyncio
    async def test_deletes_only_expired_rows(self, db_session):
        now = datetime.utcnow()
        _seed(db_session, now)
        await db_session.commit()

        deleted = await retention.purge_expired_audit_logs(
            db_session, retention_days=90, now=now
        )
        assert deleted == 1

        remaining = (await db_session.execute(select(AuditLog))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].action == "fresh_login"


class TestEnvConfig:
    def test_defaults(self, monkeypatch):
        for var in (
            "ANALYSIS_RETENTION_DAYS",
            "AUDIT_RETENTION_DAYS",
            "RETENTION_SWEEP_INTERVAL_HOURS",
        ):
            monkeypatch.delenv(var, raising=False)
        assert retention.analysis_retention_days() == 30
        assert retention.audit_retention_days() == 90
        assert retention.sweep_interval_hours() == 24.0

    def test_overrides(self, monkeypatch):
        monkeypatch.setenv("ANALYSIS_RETENTION_DAYS", "7")
        monkeypatch.setenv("AUDIT_RETENTION_DAYS", "180")
        monkeypatch.setenv("RETENTION_SWEEP_INTERVAL_HOURS", "6")
        assert retention.analysis_retention_days() == 7
        assert retention.audit_retention_days() == 180
        assert retention.sweep_interval_hours() == 6.0


class TestRunSweep:
    @pytest.mark.asyncio
    async def test_sweep_uses_env_window(self, db_session, monkeypatch):
        """run_retention_sweep should apply the env-configured windows."""
        monkeypatch.setenv("ANALYSIS_RETENTION_DAYS", "30")
        monkeypatch.setenv("AUDIT_RETENTION_DAYS", "90")

        now = datetime.utcnow()
        _seed(db_session, now)
        await db_session.commit()

        # Point the module session factory at our test session's bind.
        maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
        monkeypatch.setattr(retention, "async_session", maker)

        summary = await retention.run_retention_sweep(now=now)
        assert summary["analysis_results_deleted"] == 1
        assert summary["audit_logs_deleted"] == 1

        a_count = (
            await db_session.execute(select(func.count()).select_from(AnalysisResult))
        ).scalar()
        l_count = (
            await db_session.execute(select(func.count()).select_from(AuditLog))
        ).scalar()
        assert a_count == 1
        assert l_count == 1

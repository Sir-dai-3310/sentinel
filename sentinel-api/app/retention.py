"""Configurable data retention sweeps.

Periodic cleanup of time-bounded rows (analysis results, audit logs) so the
database does not grow unboundedly. Retention windows are configured via env:

    ANALYSIS_RETENTION_DAYS          (default 30)
    AUDIT_RETENTION_DAYS             (default 90)
    RETENTION_SWEEP_INTERVAL_HOURS   (default 24)

The sweep logic is exposed as standalone async functions so it can be unit
tested against SQLite and invoked from the FastAPI lifespan loop.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete

from app.db.models import AnalysisResult, AuditLog
from app.db.session import async_session


def analysis_retention_days() -> int:
    """Retention window for analysis results, in days."""
    return int(os.getenv("ANALYSIS_RETENTION_DAYS", "30"))


def audit_retention_days() -> int:
    """Retention window for audit logs, in days."""
    return int(os.getenv("AUDIT_RETENTION_DAYS", "90"))


def sweep_interval_hours() -> float:
    """How often the retention sweep runs, in hours."""
    return float(os.getenv("RETENTION_SWEEP_INTERVAL_HOURS", "24"))


async def purge_expired_analysis(
    session, retention_days: int | None = None, now: datetime | None = None
) -> int:
    """
    Delete analysis results older than the retention window.

    Args:
        session: SQLAlchemy async session
        retention_days: override for the window (defaults to env)
        now: reference time (defaults to utcnow, injectable for tests)

    Returns:
        Number of rows deleted.
    """
    days = analysis_retention_days() if retention_days is None else retention_days
    ref = now or datetime.utcnow()
    cutoff = ref - timedelta(days=days)
    result = await session.execute(
        delete(AnalysisResult).where(AnalysisResult.created_at < cutoff)
    )
    await session.commit()
    return result.rowcount or 0


async def purge_expired_audit_logs(
    session, retention_days: int | None = None, now: datetime | None = None
) -> int:
    """
    Delete audit logs older than the retention window.

    Args:
        session: SQLAlchemy async session
        retention_days: override for the window (defaults to env)
        now: reference time (defaults to utcnow, injectable for tests)

    Returns:
        Number of rows deleted.
    """
    days = audit_retention_days() if retention_days is None else retention_days
    ref = now or datetime.utcnow()
    cutoff = ref - timedelta(days=days)
    result = await session.execute(
        delete(AuditLog).where(AuditLog.timestamp < cutoff)
    )
    await session.commit()
    return result.rowcount or 0


async def run_retention_sweep(now: datetime | None = None) -> dict[str, int]:
    """
    Run one full retention sweep across all governed tables.

    Returns:
        Dict with counts of deleted rows per table.
    """
    async with async_session() as session:
        analysis_deleted = await purge_expired_analysis(session, now=now)
        audit_deleted = await purge_expired_audit_logs(session, now=now)
    return {
        "analysis_results_deleted": analysis_deleted,
        "audit_logs_deleted": audit_deleted,
    }


async def retention_loop(stop_event: asyncio.Event) -> None:
    """
    Background loop: sweep, then sleep for the configured interval.

    Runs until ``stop_event`` is set; cancelled cleanly on shutdown.
    """
    while not stop_event.is_set():
        try:
            summary = await run_retention_sweep()
            print(f"🧹 Retention sweep: {summary}")
        except Exception as e:  # pragma: no cover - defensive, DB hiccup
            print(f"⚠️  Retention sweep failed: {e}")

        interval_s = sweep_interval_hours() * 3600
        try:
            # Wait for the interval, but wake immediately if stopping.
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass


def start_retention_task() -> tuple[asyncio.Task, asyncio.Event]:
    """
    Start the retention background task.

    Returns:
        (task, stop_event) — set stop_event / cancel task on shutdown.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(retention_loop(stop_event))
    return task, stop_event


async def stop_retention_task(task: asyncio.Task, stop_event: asyncio.Event) -> None:
    """Signal the loop to stop and wait for it to finish."""
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

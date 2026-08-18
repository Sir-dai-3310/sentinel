"""Statistics endpoint for Dashboard."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.jwt import User, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


class Stats(BaseModel):
    """Dashboard statistics."""

    total_events: int
    alerts: int
    critical: int
    accuracy: float


@router.get("/stats", response_model=Stats)
async def get_stats() -> Stats:
    """
    Get real-time statistics for dashboard.

    In production, this would query a database or metrics store.
    For now, returns placeholder data that would be populated from real metrics.
    """
    # TODO: Integrate with real metrics storage (PostgreSQL/Redis/Prometheus)
    # For now, return realistic placeholder data
    return Stats(
        total_events=0,
        alerts=0,
        critical=0,
        accuracy=0.0,
    )


@router.get("/stats/llm-costs")
async def get_llm_costs() -> dict[str, Any]:
    """
    Aggregated LLM usage and estimated cost from the cost tracker.

    Returns call counts, token totals and per-model breakdowns. Data is
    in-process (reset on restart) unless a persistent tracker is wired in.
    """
    from sentinel_agents.llm.cost_tracker import get_cost_tracker

    return get_cost_tracker().get_summary()

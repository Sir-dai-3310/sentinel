"""Statistics endpoints for Dashboard."""

from collections import Counter
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select

from app.auth.jwt import User, require_auth
from app.db.models import AnalysisResult, RuleMetadata
from app.db.session import async_session
from app.tenancy import resolve_tenant_id

router = APIRouter(dependencies=[Depends(require_auth)])

CRITICAL_DANGER_LEVEL = 80
TREND_DAYS = 7
ATTACK_TACTICS = {
    "reconnaissance",
    "resource-development",
    "initial-access",
    "execution",
    "persistence",
    "privilege-escalation",
    "defense-evasion",
    "credential-access",
    "discovery",
    "lateral-movement",
    "collection",
    "command-and-control",
    "exfiltration",
    "impact",
}


class Stats(BaseModel):
    total_events: int
    alerts: int
    critical: int
    accuracy: float


class ThreatTrendPoint(BaseModel):
    timestamp: str
    threats: int


class RuleHitStat(BaseModel):
    rule_name: str
    count: int


class AttackTacticStat(BaseModel):
    tactic: str
    count: int


def _rule_hits(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [hit for hit in value if isinstance(hit, dict)]


def _tactics_from_tags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    tactics = set()
    for tag in value:
        if not isinstance(tag, str) or not tag.startswith("attack."):
            continue
        tactic = tag.removeprefix("attack.").lower()
        if tactic in ATTACK_TACTICS:
            tactics.add(tactic)
    return tactics


@router.get("/stats", response_model=Stats)
async def get_stats(user: User = Depends(require_auth)) -> Stats:
    tenant_id = resolve_tenant_id(user)
    stmt = select(
        func.count(AnalysisResult.id),
        func.sum(case((AnalysisResult.malicious.is_(True), 1), else_=0)),
        func.sum(
            case((AnalysisResult.danger_level >= CRITICAL_DANGER_LEVEL, 1), else_=0)
        ),
        func.sum(case((AnalysisResult.malicious.is_not(None), 1), else_=0)),
    ).where(AnalysisResult.tenant_id == tenant_id)

    async with async_session() as session:
        total, alerts, critical, classified = (await session.execute(stmt)).one()

    total_events = int(total or 0)
    return Stats(
        total_events=total_events,
        alerts=int(alerts or 0),
        critical=int(critical or 0),
        accuracy=(int(classified or 0) / total_events) if total_events else 0.0,
    )


@router.get("/stats/threat-trend", response_model=list[ThreatTrendPoint])
async def get_threat_trend(
    user: User = Depends(require_auth),
) -> list[ThreatTrendPoint]:
    tenant_id = resolve_tenant_id(user)
    today = datetime.utcnow().date()
    first_day = today - timedelta(days=TREND_DAYS - 1)
    start = datetime.combine(first_day, time.min)
    stmt = select(AnalysisResult.created_at).where(
        AnalysisResult.tenant_id == tenant_id,
        AnalysisResult.malicious.is_(True),
        AnalysisResult.created_at >= start,
    )

    async with async_session() as session:
        timestamps = (await session.execute(stmt)).scalars().all()

    counts = Counter(timestamp.date() for timestamp in timestamps)
    return [
        ThreatTrendPoint(
            timestamp=(first_day + timedelta(days=offset)).isoformat(),
            threats=counts[first_day + timedelta(days=offset)],
        )
        for offset in range(TREND_DAYS)
    ]


@router.get("/stats/rule-hits", response_model=list[RuleHitStat])
async def get_rule_hits(user: User = Depends(require_auth)) -> list[RuleHitStat]:
    tenant_id = resolve_tenant_id(user)
    stmt = select(AnalysisResult.rule_hits).where(AnalysisResult.tenant_id == tenant_id)

    async with async_session() as session:
        rows = (await session.execute(stmt)).scalars().all()

    counts: Counter[str] = Counter()
    for row in rows:
        for hit in _rule_hits(row):
            name = hit.get("rule_name") or hit.get("rule_id")
            if isinstance(name, str) and name:
                counts[name] += 1

    return [
        RuleHitStat(rule_name=name, count=count)
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


@router.get("/stats/attack-tactics", response_model=list[AttackTacticStat])
async def get_attack_tactics(
    user: User = Depends(require_auth),
) -> list[AttackTacticStat]:
    tenant_id = resolve_tenant_id(user)
    hits_stmt = select(AnalysisResult.rule_hits).where(
        AnalysisResult.tenant_id == tenant_id
    )
    rules_stmt = select(RuleMetadata.rule_id, RuleMetadata.tags)

    async with async_session() as session:
        rows = (await session.execute(hits_stmt)).scalars().all()
        rule_rows = (await session.execute(rules_stmt)).all()

    tactics_by_rule = {
        rule_id: _tactics_from_tags(tags)
        for rule_id, tags in rule_rows
        if isinstance(rule_id, str)
    }
    counts: Counter[str] = Counter()
    for row in rows:
        for hit in _rule_hits(row):
            rule_id = hit.get("rule_id")
            tactics = (
                tactics_by_rule.get(rule_id, set())
                if isinstance(rule_id, str)
                else set()
            )
            direct_tactic = hit.get("tactic")
            if isinstance(direct_tactic, str) and direct_tactic in ATTACK_TACTICS:
                tactics = tactics | {direct_tactic}
            for tactic in tactics:
                counts[tactic] += 1

    return [
        AttackTacticStat(tactic=tactic, count=counts[tactic])
        for tactic in sorted(counts)
        if counts[tactic] > 0
    ]


@router.get("/stats/llm-costs")
async def get_llm_costs() -> dict[str, Any]:
    from sentinel_agents.llm.cost_tracker import get_cost_tracker

    return get_cost_tracker().get_summary()

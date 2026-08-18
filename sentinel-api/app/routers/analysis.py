"""Analysis endpoints with real agent integration."""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt import User, require_auth
from app.rbac import require_permission
from app.tenancy import resolve_tenant_id
from sentinel_agents.graph import analyze_log
from sentinel_agents.state import IncidentState
from sentinel_agents.utils.masking import mask

router = APIRouter(dependencies=[Depends(require_auth)])


async def _persist_result(
    log: dict[str, Any], result: IncidentState, user: User
) -> None:
    """
    Persist an analysis result to the DB.

    The log event is masked BEFORE storage (store-masked, never in the clear)
    when masking is enabled. Persistence is best-effort: a DB outage must not
    fail the analysis request itself.
    """
    try:
        from app.db.models import AnalysisResult as AnalysisResultRow
        from app.db.session import async_session

        tenant_id = resolve_tenant_id(user)
        verdict = result.verdict
        async with async_session() as session:
            session.add(
                AnalysisResultRow(
                    log_event=mask(log),  # store masked
                    malicious=verdict.malicious if verdict else None,
                    danger_level=verdict.danger_level if verdict else None,
                    reason=verdict.reason if verdict else None,
                    mitre_techniques=verdict.mitre_techniques if verdict else None,
                    recommended_actions=(
                        verdict.recommended_actions if verdict else None
                    ),
                    rule_hits=[h.model_dump() for h in result.rule_hits],
                    rule_hit_count=len(result.rule_hits),
                    agent_trace=result.agent_trace,
                    skipped_llm=result.skipped_llm,
                    threat_intel=[ti.model_dump() for ti in result.threat_intel],
                    threat_intel_count=len(result.threat_intel),
                    metadata_json=result.metadata,
                    user_id=user.username,
                    request_id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                )
            )
            await session.commit()
    except Exception as e:  # pragma: no cover - DB may be absent in tests
        print(f"⚠️  analysis persistence skipped: {e}")


class LogInput(BaseModel):
    """Log event input."""

    log: dict[str, Any]


class BatchLogInput(BaseModel):
    """Batch log event input."""

    logs: list[dict[str, Any]]


class AnalysisResult(BaseModel):
    """Analysis result."""

    verdict: dict[str, Any] | None
    rule_hits: list[dict[str, Any]]
    threat_intel: list[dict[str, Any]]
    agent_trace: list[str]
    metadata: dict[str, Any]
    skipped_llm: bool


class BatchAnalysisResult(BaseModel):
    """Batch analysis result."""

    results: list[dict[str, Any]]
    total: int
    successful: int
    failed: int
    throughput_eps: float


@router.post("/analyze", response_model=AnalysisResult)
async def analyze_log_endpoint(
    input: LogInput, user: User = Depends(require_auth)
) -> AnalysisResult:
    """
    Analyze a single log event.

    Returns complete analysis including verdict, rule hits, and threat intel.
    The result is persisted (with masking applied before storage) for audit
    and GDPR subject access.
    """
    try:
        # Call real agent graph
        result: IncidentState = await analyze_log(input.log)

        # Persist (masked) for audit / GDPR; non-fatal if DB unavailable.
        await _persist_result(input.log, result, user)

        # Convert to API response format
        return AnalysisResult(
            verdict=result.verdict.model_dump() if result.verdict else None,
            rule_hits=[hit.model_dump() for hit in result.rule_hits],
            threat_intel=[ti.model_dump() for ti in result.threat_intel],
            agent_trace=result.agent_trace,
            metadata=result.metadata,
            skipped_llm=result.skipped_llm,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analyze/batch", response_model=BatchAnalysisResult)
async def analyze_batch(input: BatchLogInput) -> BatchAnalysisResult:
    """
    Analyze multiple logs in batch with parallel processing.

    Processes logs concurrently using asyncio.gather for maximum throughput.
    """
    start_time = asyncio.get_event_loop().time()

    async def analyze_one(log: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await analyze_log(log)
            return {
                "verdict": result.verdict.model_dump() if result.verdict else None,
                "rule_hits": [hit.model_dump() for hit in result.rule_hits],
                "success": True,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Process all logs in parallel
    results = await asyncio.gather(
        *[analyze_one(log) for log in input.logs],
        return_exceptions=False,
    )

    elapsed = asyncio.get_event_loop().time() - start_time
    successful = sum(1 for r in results if r.get("success", False))
    failed = len(results) - successful
    throughput = len(results) / elapsed if elapsed > 0 else 0

    return BatchAnalysisResult(
        results=results,
        total=len(results),
        successful=successful,
        failed=failed,
        throughput_eps=round(throughput, 2),
    )
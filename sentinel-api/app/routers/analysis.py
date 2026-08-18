"""Analysis endpoints with real agent integration."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt import User, require_auth
from app.rbac import require_permission
from sentinel_agents.graph import analyze_log
from sentinel_agents.state import IncidentState

router = APIRouter(dependencies=[Depends(require_auth)])


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
async def analyze_log_endpoint(input: LogInput) -> AnalysisResult:
    """
    Analyze a single log event.

    Returns complete analysis including verdict, rule hits, and threat intel.
    """
    try:
        # Call real agent graph
        result: IncidentState = await analyze_log(input.log)

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
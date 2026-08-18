"""Bulk log import endpoints.

Upload a JSONL or CSV file; the file is parsed and each row runs through the
lightweight rule-engine path (TriageAgent — no LLM call per row) in a
background task. The client polls the task status endpoint for progress.
"""

import csv
import io
import json
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.jwt import User, require_auth
from app.db.models import ImportTask
from app.db.session import async_session
from app.tenancy import resolve_tenant_id

router = APIRouter(dependencies=[Depends(require_auth)])


class ImportStatus(BaseModel):
    """Import task progress."""

    task_id: str
    status: str
    total: int
    processed: int
    failed: int


def _detect_format(filename: str, sample: str) -> str:
    """Detect upload format from filename extension, falling back to content."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return "csv"
    if name.endswith((".jsonl", ".ndjson", ".json")):
        return "jsonl"
    # Content sniff: JSONL lines start with '{'
    return "jsonl" if sample.lstrip().startswith("{") else "csv"


def _parse_rows(text: str, fmt: str) -> tuple[list[dict[str, Any]], int]:
    """
    Parse the upload into log dicts.

    Returns:
        (rows, parse_failures) — rows are valid dicts; parse_failures counts
        lines that could not be turned into a dict.
    """
    rows: list[dict[str, Any]] = []
    failures = 0
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(text))
        for rec in reader:
            if rec and any(v not in (None, "") for v in rec.values()):
                rows.append(dict(rec))
            else:
                failures += 1
    else:  # jsonl
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
                else:
                    failures += 1
            except json.JSONDecodeError:
                failures += 1
    return rows, failures


async def _process_import(task_id: str, text: str, fmt: str, tenant_id: str) -> None:
    """
    Background worker: parse rows, run each through the lightweight rule
    engine, and update the ImportTask counters as it goes.
    """
    # Local import so the module loads even if agents extras are missing.
    from sentinel_agents.agents import TriageAgent
    from sentinel_agents.state import IncidentState

    rows, parse_failures = _parse_rows(text, fmt)

    async with async_session() as session:
        task = (
            await session.execute(
                select(ImportTask).where(ImportTask.task_id == task_id)
            )
        ).scalar_one_or_none()
        if task is None:
            return

        task.status = "processing"
        task.total = len(rows) + parse_failures
        task.failed = parse_failures
        await session.commit()

        # TriageAgent only runs the rule engine here (no LLM call), but its
        # constructor builds a default LLM client. Provide a no-op client so
        # import never depends on LLM credentials being configured.
        class _NullLLM:
            async def ainvoke(self, *a, **k):
                return ""

            async def ainvoke_structured(self, *a, **k):
                return None

        triage = TriageAgent(llm_client=_NullLLM())
        for row in rows:
            try:
                state = IncidentState(log=row)
                await triage(state)  # rule engine only; no LLM
                task.processed += 1
            except Exception:
                task.failed += 1
            # Persist progress every row (cheap for small batches).
            await session.commit()

        task.status = "completed"
        await session.commit()


@router.post("/logs/import", response_model=ImportStatus, status_code=status.HTTP_202_ACCEPTED)
async def import_logs(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_auth),
) -> ImportStatus:
    """
    Upload a JSONL or CSV file of log events for asynchronous bulk import.

    Returns a task_id immediately; processing happens in the background.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    fmt = _detect_format(file.filename or "", text[:512])
    tenant_id = resolve_tenant_id(user)
    task_id = uuid.uuid4().hex

    async with async_session() as session:
        session.add(
            ImportTask(
                task_id=task_id,
                status="pending",
                filename=file.filename,
                format=fmt,
                tenant_id=tenant_id,
            )
        )
        await session.commit()

    background_tasks.add_task(_process_import, task_id, text, fmt, tenant_id)

    return ImportStatus(task_id=task_id, status="pending", total=0, processed=0, failed=0)


@router.get("/logs/import/{task_id}", response_model=ImportStatus)
async def get_import_status(task_id: str, user: User = Depends(require_auth)) -> ImportStatus:
    """Get progress of a bulk import task."""
    tenant_id = resolve_tenant_id(user)
    async with async_session() as session:
        task = (
            await session.execute(
                select(ImportTask).where(
                    ImportTask.task_id == task_id,
                    ImportTask.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Import task not found")

    return ImportStatus(
        task_id=task.task_id,
        status=task.status,
        total=task.total,
        processed=task.processed,
        failed=task.failed,
    )

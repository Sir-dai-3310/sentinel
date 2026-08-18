"""GDPR/CCPA data-subject rights endpoints: export & erasure.

A "subject" is identified by the ``user_id`` recorded on analysis results.
Export returns every row tied to the subject as JSON; erasure deletes those
rows. Both operations are admin-gated and write an audit-log entry for the
action itself (the deletion is auditable even though the data is gone).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.auth.jwt import User, require_auth
from app.db.models import AnalysisResult, AuditLog
from app.db.session import async_session
from app.tenancy import require_admin, resolve_tenant_id

router = APIRouter(dependencies=[Depends(require_auth)])


def _row_to_dict(row: AnalysisResult) -> dict[str, Any]:
    """Serialize an AnalysisResult row for export."""
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "log_event": row.log_event,
        "malicious": row.malicious,
        "danger_level": row.danger_level,
        "reason": row.reason,
        "mitre_techniques": row.mitre_techniques,
        "recommended_actions": row.recommended_actions,
        "rule_hits": row.rule_hits,
        "threat_intel": row.threat_intel,
        "metadata": row.metadata_json,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
    }


async def _write_audit(
    session, action: str, actor: str, subject: str, tenant_id: str, details: dict
) -> None:
    """Record the privacy action itself in the audit log."""
    session.add(
        AuditLog(
            timestamp=datetime.utcnow(),
            action=action,
            user_id=actor,
            resource=f"privacy:subject:{subject}",
            success=True,
            details=details,
            tenant_id=tenant_id,
        )
    )


@router.get("/privacy/export")
async def export_subject_data(
    subject: str = Query(..., description="Data-subject id (user_id)"),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Export all data held for a subject as JSON (GDPR Art. 15 / data portability).
    """
    tenant_id = resolve_tenant_id(admin)
    async with async_session() as session:
        rows = (
            (
                await session.execute(
                    select(AnalysisResult).where(
                        AnalysisResult.user_id == subject,
                        AnalysisResult.tenant_id == tenant_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        await _write_audit(
            session, "privacy_export", admin.username, subject, tenant_id,
            {"rows_exported": len(rows)},
        )
        await session.commit()

    return {
        "subject": subject,
        "tenant_id": tenant_id,
        "exported_at": datetime.utcnow().isoformat(),
        "record_count": len(rows),
        "analysis_results": [_row_to_dict(r) for r in rows],
    }


class DeleteResponse(BaseModel):
    """Erasure outcome."""

    subject: str
    deleted_count: int
    status: str


@router.delete("/privacy/data", response_model=DeleteResponse)
async def delete_subject_data(
    subject: str = Query(..., description="Data-subject id (user_id)"),
    admin: User = Depends(require_admin),
) -> DeleteResponse:
    """
    Erase all data held for a subject (GDPR Art. 17 / right to erasure).

    The deletion action is itself audit-logged.
    """
    tenant_id = resolve_tenant_id(admin)
    async with async_session() as session:
        result = await session.execute(
            delete(AnalysisResult).where(
                AnalysisResult.user_id == subject,
                AnalysisResult.tenant_id == tenant_id,
            )
        )
        deleted = result.rowcount or 0
        await _write_audit(
            session, "privacy_delete", admin.username, subject, tenant_id,
            {"rows_deleted": deleted},
        )
        await session.commit()

    return DeleteResponse(subject=subject, deleted_count=deleted, status="erased")

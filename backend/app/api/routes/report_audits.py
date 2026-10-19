"""Routes: AI report auditor (phase 6, feature 10).

Submit one audit of a report draft (a report-mode message reference XOR
investigator-supplied text), list audit runs and read their findings. The
original draft is never modified; findings land as reviewable
``report_claim_review`` artifacts that follow the shared human-review
machine. Permission equals report drafting (``case.read``); the job itself
is cancellable through the shared cancellation contract.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import ApiHTTPException
from app.api.routes.evidence_intelligence import _artifact_out, _job_out
from app.core import rbac
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_DRAFT_SOURCE_INVALID,
    CODE_DRAFT_TOO_LARGE,
    CODE_DRAFT_UNAVAILABLE,
    CODE_JOB_NOT_FOUND,
    CODE_MESSAGE_NOT_REPORT_MODE,
    CODE_REPORT_AUDIT_ACTIVE,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import AIMessage, AnalysisJob, DerivedArtifact, User
from app.schemas.evidence_integrity import JobSubmitResponse
from app.schemas.report_audits import (
    ReportAuditDetailOut,
    ReportAuditListResponse,
    ReportAuditOut,
    ReportAuditSubmitRequest,
)
from app.services import analysis_jobs as jobs_svc
from app.services import audit as audit_svc
from app.services import report_audit as report_audit_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["report-audits"])

# Typed HTTP mapping for report-audit submission rejections.
_REJECTION_HTTP: dict[str, int] = {
    CODE_DRAFT_SOURCE_INVALID: 422,
    CODE_DRAFT_TOO_LARGE: 413,
    CODE_DRAFT_UNAVAILABLE: 404,
    CODE_MESSAGE_NOT_REPORT_MODE: 422,
    CODE_REPORT_AUDIT_ACTIVE: 409,
    CODE_JOB_NOT_FOUND: 404,
}


def _summary_str(summary: dict[str, Any], key: str) -> str | None:
    value = summary.get(key)
    return value if isinstance(value, str) else None


def _summary_int(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    return value if isinstance(value, int) else None


async def _staleness(session: AsyncSession, summary: dict[str, Any]) -> bool | None:
    """Compare the audited draft hash with the current message content.

    ``None`` when the audit did not reference a message or the message is no
    longer available (the audit still describes its pinned snapshot).
    """
    message_id = _summary_str(summary, "message_id")
    draft_hash = _summary_str(summary, "draft_hash")
    if not message_id or not draft_hash:
        return None
    message = await session.get(AIMessage, uuid.UUID(message_id))
    if message is None:
        return None
    return report_audit_svc.draft_sha256(message.content) != draft_hash


def _audit_out(
    job: AnalysisJob,
    artifact: DerivedArtifact | None,
    stale: bool | None,
) -> ReportAuditOut:
    summary = dict(job.result_summary or {})
    claims: int | None = None
    if artifact is not None:
        payload = artifact.payload or {}
        raw_claims = payload.get("claims")
        if isinstance(raw_claims, list):
            claims = len(raw_claims)
    return ReportAuditOut(
        id=job.id,
        case_id=uuid.UUID(str(job.case_id)),
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
        draft_source_type=_summary_str(summary, "draft_source_type"),
        draft_hash=_summary_str(summary, "draft_hash"),
        draft_chars=_summary_int(summary, "draft_chars"),
        conversation_id=(
            uuid.UUID(message_id)
            if (message_id := _summary_str(summary, "conversation_id"))
            else None
        ),
        message_id=(
            uuid.UUID(message_id) if (message_id := _summary_str(summary, "message_id")) else None
        ),
        artifact_id=artifact.id if artifact is not None else None,
        claims=claims,
        stale=stale,
        result_summary=job.result_summary,
    )


async def _artifacts_by_job(
    session: AsyncSession, case_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> dict[str, DerivedArtifact]:
    if not job_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(DerivedArtifact).where(
                    DerivedArtifact.case_id == str(case_id),
                    DerivedArtifact.kind == "report_claim_review",
                    DerivedArtifact.analysis_job_id.in_(job_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(row.analysis_job_id): row for row in rows}


@router.post(
    "/{case_id}/report-audits",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_report_audit(
    case_id: uuid.UUID,
    body: ReportAuditSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> JobSubmitResponse:
    """Queue one bounded audit of a report draft.

    Exactly one source: a report-mode assistant message of this case
    (``conversation_id`` + ``message_id``) XOR ``draft_text``. Deterministic
    code validates every span, citation, number and date; the model only
    extracts claims and assesses support, and its output is verified or
    flagged - never trusted. The background task re-checks authorization and
    cancellation itself; this endpoint only validates, records and schedules.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    if not settings.AI_FEATURE_REPORT_AUDIT:
        raise ApiHTTPException(403, CODE_AI_DISABLED, "report audit feature is disabled")
    try:
        job, created, snapshot = await report_audit_svc.submit_report_audit(
            session,
            case_id=case_id,
            actor_id=user.id,
            settings=settings,
            conversation_id=body.conversation_id,
            message_id=body.message_id,
            draft_text=body.draft_text,
        )
    except report_audit_svc.ReportAuditRejected as exc:
        raise ApiHTTPException(_REJECTION_HTTP.get(exc.code, 422), exc.code, exc.message) from exc
    if created:
        background_tasks.add_task(
            report_audit_svc.run_report_audit_job,
            request.app,
            uuid.UUID(str(job.id)),
            snapshot,
        )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="report_audit.submitted",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={
            "duplicate": not created,
            "draft_source_type": snapshot.get("source_type", "text"),
        },
    )
    await session.commit()
    return JobSubmitResponse(job=_job_out(job), duplicate=not created)


@router.get("/{case_id}/report-audits", response_model=ReportAuditListResponse)
async def list_report_audits(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> ReportAuditListResponse:
    """List report-audit runs (newest first) for a case the caller can read."""
    await get_case_or_404(case_id, request, session)
    total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AnalysisJob)
                .where(
                    AnalysisJob.case_id == str(case_id),
                    AnalysisJob.feature == "report_audit",
                )
            )
        ).scalar_one()
    )
    rows = (
        (
            await session.execute(
                select(AnalysisJob)
                .where(
                    AnalysisJob.case_id == str(case_id),
                    AnalysisJob.feature == "report_audit",
                )
                .order_by(AnalysisJob.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    artifacts = await _artifacts_by_job(session, case_id, [uuid.UUID(str(row.id)) for row in rows])
    items: list[ReportAuditOut] = []
    for row in rows:
        artifact = artifacts.get(str(row.id))
        stale = await _staleness(session, dict(row.result_summary or {}))
        items.append(_audit_out(row, artifact, stale))
    return ReportAuditListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{case_id}/report-audits/{audit_id}", response_model=ReportAuditDetailOut)
async def get_report_audit(
    case_id: uuid.UUID,
    audit_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> ReportAuditDetailOut:
    """Read one audit run with its full claim-review findings payload."""
    await get_case_or_404(case_id, request, session)
    job = await jobs_svc.get_job(session, case_id, audit_id)
    if job is None or job.feature != "report_audit":
        raise ApiHTTPException(404, CODE_JOB_NOT_FOUND, f"audit {audit_id} not found in this case")
    artifact_row = (
        (
            await session.execute(
                select(DerivedArtifact)
                .where(
                    DerivedArtifact.case_id == str(case_id),
                    DerivedArtifact.kind == "report_claim_review",
                    DerivedArtifact.analysis_job_id == job.id,
                )
                .order_by(DerivedArtifact.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    summary = dict(job.result_summary or {})
    stale = await _staleness(session, summary)
    base = _audit_out(job, artifact_row, stale)
    return ReportAuditDetailOut(
        **base.model_dump(),
        artifact=_artifact_out(artifact_row) if artifact_row is not None else None,
    )

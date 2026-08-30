"""Routes: persisted analytics findings (explainable, reviewable, case-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_analytics_data_repository,
    get_case_or_404,
    get_current_user,
)
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import Finding, User
from app.repositories.analytics_repository import AnalyticsDataRepository
from app.schemas.analytics import (
    FindingListResponse,
    FindingOut,
    FindingStatsOut,
    FindingStatusOut,
)
from app.schemas.findings import FindingStatusUpdate
from app.services.audit import record_audit
from app.services.findings_service import (
    FindingsService,
    InvalidFindingTransition,
    required_permission_for,
)

router = APIRouter(prefix="/cases", tags=["findings"])

_FINDING_STATUSES = ("NEW", "REVIEWED", "DISMISSED", "CONFIRMED")


def _finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        id=finding.id,
        case_id=finding.case_id,
        run_id=finding.run_id,
        finding_type=finding.finding_type,
        title=finding.title,
        summary=finding.summary,
        severity=finding.severity,
        score=finding.score,
        confidence=finding.confidence,
        status=finding.status,
        affected_entities=[uuid.UUID(value) for value in finding.affected_entities or []],
        affected_relationships=[uuid.UUID(value) for value in finding.affected_relationships or []],
        evidence_ids=[uuid.UUID(value) for value in finding.evidence_ids or []],
        explanation=finding.explanation,
        details=finding.details,
        reviewed_by=finding.reviewed_by,
        reviewed_at=finding.reviewed_at,
        review_comment=finding.review_comment,
        created_at=finding.created_at,
    )


@router.get("/{case_id}/findings", response_model=FindingListResponse)
async def list_findings(
    case_id: uuid.UUID,
    request: Request,
    finding_type: str | None = Query(None),
    status: str | None = Query(None),
    severity: str | None = Query(None),
    run_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingListResponse:
    """Findings for a case, newest first. Filter by type/status/severity.

    Findings are snapshotted per analytics run: each ``POST /analytics/run``
    persists the findings it produced under its ``run_id``. Without a ``run_id``
    the full history across runs is returned; pass ``run_id`` to view exactly
    one run's snapshot.
    """
    await get_case_or_404(case_id, request, session)
    items, total = await repository.list_findings(
        case_id,
        finding_type=finding_type,
        status=status,
        severity=severity,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return FindingListResponse(
        items=[_finding_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/findings/stats", response_model=FindingStatsOut)
async def get_findings_stats(
    case_id: uuid.UUID,
    request: Request,
    run_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingStatsOut:
    """Counts of findings grouped by type, severity and status.

    Like the findings list, stats cover the whole case history unless a specific
    ``run_id`` snapshot is requested.
    """
    await get_case_or_404(case_id, request, session)
    stats = await repository.findings_stats(case_id, run_id=run_id)
    return FindingStatsOut(**stats)


@router.get("/{case_id}/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    case_id: uuid.UUID,
    request: Request,
    finding_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingOut:
    """A single finding with its full explanation and evidence chain."""
    await get_case_or_404(case_id, request, session)
    finding = await repository.get_finding(case_id, finding_id)
    if finding is None or str(finding.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    return _finding_out(finding)


@router.patch("/{case_id}/findings/{finding_id}/status", response_model=FindingStatusOut)
async def update_finding_status(
    case_id: uuid.UUID,
    request: Request,
    finding_id: uuid.UUID,
    payload: FindingStatusUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingStatusOut:
    """Review a finding through its lifecycle (NEW/REVIEWED/DISMISSED/CONFIRMED).

    The engine never auto-assigns ``CONFIRMED`` — that verdict requires a human.
    Permissions gate the target status: ``findings.review`` for REVIEWED,
    ``findings.dismiss`` for DISMISSED, ``findings.confirm`` for CONFIRMED.
    Closed findings (DISMISSED/CONFIRMED) are immutable except by an explicitly
    authorized ADMIN. Same-status calls are idempotent no-ops.
    """
    await get_case_or_404(case_id, request, session)
    roles = getattr(request.state, "roles", None) or []
    is_admin = any(rbac.is_admin_role(role) for role in roles)
    if payload.status not in _FINDING_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status {payload.status}")

    permission = required_permission_for(payload.status)
    if not rbac.has_permission(roles, permission):
        raise HTTPException(status_code=403, detail=f"permission '{permission}' required")

    finding = await repository.get_finding(case_id, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    previous_status = finding.status

    service = FindingsService(session)
    try:
        updated, changed = await service.apply_status_change(
            finding=finding,
            new_status=payload.status,
            actor_id=user.id,
            reason=payload.reason,
            is_admin=is_admin,
        )
    except InvalidFindingTransition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if changed:
        await record_audit(
            session,
            actor_id=user.id,
            action="finding.status_changed",
            resource_type="finding",
            resource_id=finding.id,
            case_id=case_id,
            metadata={
                "from": previous_status,
                "to": payload.status,
                "reason": payload.reason,
            },
        )
    await repository.commit()
    return FindingStatusOut(
        id=updated.id,
        status=updated.status,
        reviewed_by=updated.reviewed_by,
        reviewed_at=updated.reviewed_at,
        review_comment=updated.review_comment,
    )

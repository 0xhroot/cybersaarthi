"""Routes: persisted analytics findings (explainable, reviewable, case-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_analytics_data_repository, get_case_or_404
from app.db.postgres import get_db_session
from app.models import Finding
from app.repositories.analytics_repository import AnalyticsDataRepository
from app.schemas.analytics import (
    FindingListResponse,
    FindingOut,
    FindingStatsOut,
    FindingStatusOut,
)
from app.schemas.findings import FindingStatusUpdate

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
        created_at=finding.created_at,
    )


@router.get("/{case_id}/findings", response_model=FindingListResponse)
async def list_findings(
    case_id: uuid.UUID,
    finding_type: str | None = Query(None),
    status: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingListResponse:
    """Findings for a case, newest first. Filter by type/status/severity."""
    await get_case_or_404(case_id, session)
    items, total = await repository.list_findings(
        case_id,
        finding_type=finding_type,
        status=status,
        severity=severity,
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
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingStatsOut:
    """Counts of findings grouped by type, severity and status."""
    await get_case_or_404(case_id, session)
    stats = await repository.findings_stats(case_id)
    return FindingStatsOut(**stats)


@router.get("/{case_id}/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingOut:
    """A single finding with its full explanation and evidence chain."""
    await get_case_or_404(case_id, session)
    finding = await repository.get_finding(case_id, finding_id)
    if finding is None or str(finding.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    return _finding_out(finding)


@router.patch("/{case_id}/findings/{finding_id}/status", response_model=FindingStatusOut)
async def update_finding_status(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingStatusUpdate,
    session: AsyncSession = Depends(get_db_session),
    repository: AnalyticsDataRepository = Depends(get_analytics_data_repository),
) -> FindingStatusOut:
    """Review a finding: set NEW/REVIEWED/DISMISSED/CONFIRMED (analyst decision).

    The engine never auto-assigns CONFIRMED — that verdict requires a human.
    """
    await get_case_or_404(case_id, session)
    if payload.status not in _FINDING_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status {payload.status}")
    finding = await repository.get_finding(case_id, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    updated = await repository.update_finding_status(finding_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    await repository.commit()
    return FindingStatusOut(id=updated.id, status=updated.status)

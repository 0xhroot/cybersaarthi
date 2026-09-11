"""Routes: reports (case-scoped generate + download)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import Report, User
from app.services import audit as audit_svc
from app.services import reporting as rpt_svc
from app.services.timeline import record_event

router = APIRouter(prefix="/cases", tags=["reports"])


class ReportGenerateRequest(BaseModel):
    report_type: str
    format: str = "json"
    title: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    report_type: str
    format: str
    title: str
    status: str
    byte_size: int | None
    failure_reason: str | None
    created_at: datetime


class ReportListResponse(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int


def _report_out(r: Report) -> ReportOut:
    return ReportOut(
        id=r.id,
        case_id=uuid.UUID(str(r.case_id)),
        report_type=r.report_type,
        format=r.format,
        title=r.title,
        status=r.status,
        byte_size=r.byte_size,
        failure_reason=r.failure_reason,
        created_at=r.created_at,
    )


@router.post(
    "/{case_id}/reports",
    response_model=ReportOut,
    status_code=201,
)
async def generate_report(
    case_id: uuid.UUID,
    body: ReportGenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
    settings: Settings = Depends(get_settings),
) -> ReportOut:
    await get_case_or_404(case_id, request, session)
    title = body.title or f"{body.report_type.replace('_', ' ').title()} - Case"
    report = await rpt_svc.generate_report(
        session=session,
        storage=request.app.state.storage,
        settings=settings,
        case_id=case_id,
        report_type=body.report_type,
        fmt=body.format,
        title=title,
        created_by=user.id,
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="report.generated",
        resource_type="report",
        resource_id=report.id,
        case_id=case_id,
        metadata={
            "report_type": report.report_type,
            "format": report.format,
            "status": report.status,
        },
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=report.created_at,
        kind="report_generated",
        title=f"Report generated: {title}",
        description=f"format {report.format} · status {report.status}",
        actor_user_id=user.id,
        payload={
            "report_type": report.report_type,
            "format": report.format,
            "status": report.status,
        },
    )
    await session.commit()
    return _report_out(report)


@router.get("/{case_id}/reports", response_model=ReportListResponse)
async def list_reports(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> ReportListResponse:
    await get_case_or_404(case_id, request, session)
    rows, total = await rpt_svc.list_reports(
        session=session, case_id=case_id, limit=limit, offset=offset
    )
    return ReportListResponse(
        items=[_report_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/reports/{report_id}", response_model=ReportOut)
async def get_report(
    case_id: uuid.UUID,
    report_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> ReportOut:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    r = await rpt_svc.get_report(session, report_id)
    if r is None or str(r.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    return _report_out(r)


_CONTENT_TYPES = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf"}


@router.get("/{case_id}/reports/{report_id}/download")
async def download_report(
    case_id: uuid.UUID,
    report_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> StreamingResponse:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    r = await rpt_svc.get_report(session, report_id)
    if r is None or str(r.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    if r.status != "ready":
        raise HTTPException(status_code=409, detail="report not ready")
    content = await rpt_svc.get_report_bytes(storage=request.app.state.storage, report=r)

    async def _iter() -> AsyncIterator[bytes]:
        yield content

    filename = f"{r.title.replace(' ', '_')}.{r.format}"
    return StreamingResponse(
        _iter(),
        media_type=_CONTENT_TYPES.get(r.format, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

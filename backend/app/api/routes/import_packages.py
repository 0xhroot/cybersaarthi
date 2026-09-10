"""Routes: USB/desktop import package verification and ingestion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import User
from app.services import package_verification as pkg_svc

router = APIRouter(prefix="/cases", tags=["import"])


class ImportPackageAcceptedResponse(BaseModel):
    case_id: str
    device_serial: str
    imported_evidence_count: int
    evidence_ids: list[str]
    collection_name: str | None


@router.post(
    "/{case_id}/import/packages",
    response_model=ImportPackageAcceptedResponse,
    status_code=201,
)
async def import_package(
    case_id: uuid.UUID,
    request: Request,
    manifest: UploadFile = File(...),
    manifest_signature: UploadFile = File(...),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_UPLOAD)),
    settings: Settings = Depends(get_settings),
) -> ImportPackageAcceptedResponse:
    case = await get_case_or_404(case_id, request, session)
    from app.api.dependencies import assert_case_investigation_mutable

    assert_case_investigation_mutable(case)

    manifest_bytes = await manifest.read()
    sig_bytes = await manifest_signature.read()

    file_slices: list[tuple[str, bytes]] = []
    for f in files:
        if f.filename is None:
            continue
        content = await f.read()
        file_slices.append((f.filename, content))

    result = await pkg_svc.import_package(
        session=session,
        storage=request.app.state.storage,
        settings=settings,
        case_id=case_id,
        manifest_bytes=manifest_bytes,
        manifest_signature=sig_bytes,
        file_slices=file_slices,
        actor_id=user.id,
    )
    await session.commit()
    return ImportPackageAcceptedResponse(**result)

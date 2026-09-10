"""Routes: field device registry (case-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import FieldDevice, User
from app.services import audit as audit_svc
from app.services import devices as dev_svc
from app.services.timeline import record_event

router = APIRouter(prefix="/cases", tags=["devices"])


class DeviceRegisterRequest(BaseModel):
    platform: str
    serial: str
    model: str | None = None
    firmware_version: str | None = None
    public_key: str
    signature_algorithm: str = "RSA-SHA256"


class DeviceOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    platform: str
    serial: str
    model: str | None
    firmware_version: str | None
    signature_algorithm: str
    status: str
    approved_by: uuid.UUID | None
    last_seen_at: datetime | None
    created_at: datetime


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int
    limit: int
    offset: int


def _device_out(d: FieldDevice) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        case_id=uuid.UUID(str(d.case_id)),
        platform=d.platform,
        serial=d.serial,
        model=d.model,
        firmware_version=d.firmware_version,
        signature_algorithm=d.signature_algorithm,
        status=d.status,
        approved_by=uuid.UUID(str(d.approved_by)) if d.approved_by else None,
        last_seen_at=d.last_seen_at,
        created_at=d.created_at,
    )


@router.post(
    "/{case_id}/devices",
    response_model=DeviceOut,
    status_code=201,
)
async def register_device(
    case_id: uuid.UUID,
    body: DeviceRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> DeviceOut:
    await get_case_or_404(case_id, request, session)
    device = await dev_svc.register_device(
        session=session,
        case_id=case_id,
        user_id=user.id,
        platform=body.platform,
        serial=body.serial,
        model=body.model,
        firmware_version=body.firmware_version,
        public_key=body.public_key,
        signature_algorithm=body.signature_algorithm,
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="device.registered",
        resource_type="field_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"serial": device.serial, "platform": device.platform},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=device.created_at,
        kind="device_registered",
        title=f"Device '{device.serial}' registered",
        device_id=device.id,
        actor_user_id=user.id,
        payload={"platform": device.platform},
    )
    await session.commit()
    return _device_out(device)


@router.get("/{case_id}/devices", response_model=DeviceListResponse)
async def list_devices(
    case_id: uuid.UUID,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> DeviceListResponse:
    await get_case_or_404(case_id, request, session)
    rows, total = await dev_svc.list_devices(
        session=session, case_id=case_id, status=status, limit=limit, offset=offset
    )
    return DeviceListResponse(
        items=[_device_out(d) for d in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{case_id}/devices/{device_id}/approve",
    response_model=DeviceOut,
)
async def approve_device(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_USERS_MANAGE)),
) -> DeviceOut:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    device = await dev_svc.get_device(session, device_id)
    if device is None or str(device.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"device {device_id} not found")
    device = await dev_svc.approve_device(session=session, device=device, approved_by=user.id)
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="device.approved",
        resource_type="field_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"serial": device.serial},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=device.updated_at,
        kind="device_approved",
        title=f"Device '{device.serial}' approved",
        device_id=device.id,
        actor_user_id=user.id,
    )
    await session.commit()
    return _device_out(device)


@router.post(
    "/{case_id}/devices/{device_id}/revoke",
    response_model=DeviceOut,
)
async def revoke_device(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_USERS_MANAGE)),
) -> DeviceOut:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    device = await dev_svc.get_device(session, device_id)
    if device is None or str(device.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"device {device_id} not found")
    device = await dev_svc.revoke_device(session=session, device=device)
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="device.revoked",
        resource_type="field_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"serial": device.serial},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=device.revoked_at or device.updated_at,
        kind="device_revoked",
        title=f"Device '{device.serial}' revoked",
        device_id=device.id,
        actor_user_id=user.id,
    )
    await session.commit()
    return _device_out(device)


class DeviceVerifyRequest(BaseModel):
    data: str
    signature: str


class DeviceVerifyResponse(BaseModel):
    valid: bool


@router.post(
    "/{case_id}/devices/{device_id}/verify-key",
    response_model=DeviceVerifyResponse,
)
async def verify_device_key(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    body: DeviceVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> DeviceVerifyResponse:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    device = await dev_svc.get_device(session, device_id)
    if device is None or str(device.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"device {device_id} not found")
    valid = dev_svc.verify_signature(
        public_key_pem=device.public_key,
        algorithm=device.signature_algorithm,
        data=body.data.encode(),
        signature=bytes.fromhex(body.signature),
    )
    return DeviceVerifyResponse(valid=valid)

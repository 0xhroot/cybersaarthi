"""Routes: IoT device and event management for fraud investigations."""

from __future__ import annotations

import logging
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import CODE_DUPLICATE_DEVICE_SERIAL, ApiHTTPException
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import IoTDevice, IoTEvent, User
from app.schemas.iot import (
    IoTDeviceCreateRequest,
    IoTDeviceListResponse,
    IoTDeviceOut,
    IoTDeviceStatsOut,
    IoTDeviceUpdateRequest,
    IoTEventCreateRequest,
    IoTEventListResponse,
    IoTEventOut,
)
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["iot"])


async def _get_device_or_404(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    session: AsyncSession,
) -> IoTDevice:
    device = await session.get(IoTDevice, device_id)
    if device is None or str(device.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"iot device {device_id} not found in case")
    return device


def _to_device_out(device: IoTDevice, event_count: int = 0) -> IoTDeviceOut:
    return IoTDeviceOut(
        id=device.id,
        case_id=device.case_id,
        name=device.name,
        device_type=device.device_type,
        make=device.make,
        model=device.model,
        serial_number=device.serial_number,
        imei=device.imei,
        ip_address=device.ip_address,
        mac_address=device.mac_address,
        os=device.os,
        os_version=device.os_version,
        owner_name=device.owner_name,
        owner_phone=device.owner_phone,
        status=device.status,
        description=device.description,
        firmware_version=device.firmware_version,
        first_seen_at=device.first_seen_at,
        last_seen_at=device.last_seen_at,
        metadata_json=device.metadata_json,
        event_count=event_count,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _to_event_out(event: IoTEvent) -> IoTEventOut:
    return IoTEventOut(
        id=event.id,
        case_id=event.case_id,
        device_id=event.device_id,
        event_type=event.event_type,
        event_time=event.event_time,
        source=event.source,
        payload=event.payload,
        latitude=event.latitude,
        longitude=event.longitude,
        location_label=event.location_label,
        confidence=event.confidence,
        description=event.description,
        created_at=event.created_at,
    )


async def _event_counts(session: AsyncSession, case_id: uuid.UUID) -> dict[str, int]:
    result = await session.execute(
        select(IoTEvent.device_id, func.count(IoTEvent.id))
        .where(IoTEvent.case_id == case_id)
        .group_by(IoTEvent.device_id)
    )
    return {str(row[0]): int(row[1]) for row in result}


@router.get("/{case_id}/iot/devices", response_model=IoTDeviceListResponse)
async def list_devices(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, max_length=32),
    device_type: str | None = Query(None, max_length=32),
    search: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_db_session),
) -> IoTDeviceListResponse:
    """List IoT devices registered against a case."""
    await get_case_or_404(case_id, request, session)
    filters = [IoTDevice.case_id == case_id]
    if status:
        filters.append(IoTDevice.status == status)
    if device_type:
        filters.append(IoTDevice.device_type == device_type)
    if search:
        pattern = f"%{search}%"
        filters.append(IoTDevice.name.ilike(pattern) | IoTDevice.serial_number.ilike(pattern))

    base = select(IoTDevice).where(*filters)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.order_by(IoTDevice.created_at.desc()).limit(limit).offset(offset)
    )
    devices = list(result.scalars())
    counts = await _event_counts(session, case_id)
    return IoTDeviceListResponse(
        items=[_to_device_out(d, counts.get(str(d.id), 0)) for d in devices],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/{case_id}/iot/devices", response_model=IoTDeviceOut, status_code=201)
async def register_device(
    case_id: uuid.UUID,
    payload: IoTDeviceCreateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> IoTDeviceOut:
    """Register a device for monitoring within a case."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    device = IoTDevice(
        case_id=case_id,
        registered_by=user.id,
        **payload.model_dump(exclude_unset=True),
    )
    try:
        session.add(device)
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiHTTPException(
            409,
            CODE_DUPLICATE_DEVICE_SERIAL,
            f"serial_number {payload.serial_number!r} is already registered for this case",
        ) from exc
    await session.refresh(device)
    await record_audit(
        session,
        actor_id=user.id,
        action="iot.device_registered",
        resource_type="iot_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"name": device.name, "serial_number": device.serial_number},
    )
    await session.commit()
    return _to_device_out(device)


@router.get("/{case_id}/iot/devices/{device_id}", response_model=IoTDeviceOut)
async def get_device(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IoTDeviceOut:
    """Get a single registered device."""
    await get_case_or_404(case_id, request, session)
    device = await _get_device_or_404(case_id, device_id, session)
    counts = await _event_counts(session, case_id)
    return _to_device_out(device, counts.get(str(device.id), 0))


@router.patch("/{case_id}/iot/devices/{device_id}", response_model=IoTDeviceOut)
async def update_device(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    payload: IoTDeviceUpdateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> IoTDeviceOut:
    """Update device metadata or status."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    device = await _get_device_or_404(case_id, device_id, session)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is not None:
            setattr(device, key, value)
    if "status" in updates and updates["status"] == "inactive":
        device.last_seen_at = None
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiHTTPException(
            409,
            CODE_DUPLICATE_DEVICE_SERIAL,
            f"serial_number {device.serial_number!r} is already registered for this case",
        ) from exc
    await session.refresh(device)
    await record_audit(
        session,
        actor_id=user.id,
        action="iot.device_updated",
        resource_type="iot_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"fields": list(updates.keys())},
    )
    await session.commit()
    counts = await _event_counts(session, case_id)
    return _to_device_out(device, counts.get(str(device.id), 0))


@router.delete("/{case_id}/iot/devices/{device_id}", status_code=204)
async def delete_device(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Unregister a device (removes its events with CASCADE)."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    device = await _get_device_or_404(case_id, device_id, session)
    await record_audit(
        session,
        actor_id=user.id,
        action="iot.device_removed",
        resource_type="iot_device",
        resource_id=device.id,
        case_id=case_id,
        metadata={"name": device.name},
    )
    await session.delete(device)
    await session.flush()
    await session.commit()


# ------------------------------- Events -------------------------------


@router.get("/{case_id}/iot/events", response_model=IoTEventListResponse)
async def list_events(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    device_id: uuid.UUID | None = Query(None),
    event_type: str | None = Query(None, max_length=32),
    session: AsyncSession = Depends(get_db_session),
) -> IoTEventListResponse:
    """List telemetry events for a case, optionally filtered by device."""
    await get_case_or_404(case_id, request, session)
    filters = [IoTEvent.case_id == case_id]
    if device_id:
        filters.append(IoTEvent.device_id == device_id)
    if event_type:
        filters.append(IoTEvent.event_type == event_type)

    base = select(IoTEvent).where(*filters)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.order_by(IoTEvent.event_time.desc()).limit(limit).offset(offset)
    )
    events = list(result.scalars())
    return IoTEventListResponse(
        items=[_to_event_out(e) for e in events],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/{case_id}/iot/events", response_model=IoTEventOut, status_code=201)
async def record_event(
    case_id: uuid.UUID,
    payload: IoTEventCreateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> IoTEventOut:
    """Record a single telemetry event against a registered device."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    device = await _get_device_or_404(case_id, payload.device_id, session)
    event = IoTEvent(
        case_id=case_id,
        device_id=device.id,
        ingested_by=user.id,
        **payload.model_dump(exclude={"device_id"}),
    )
    if device.last_seen_at is None or event.event_time > device.last_seen_at:
        device.last_seen_at = event.event_time
    session.add(event)
    await session.flush()
    await session.refresh(event)
    await record_audit(
        session,
        actor_id=user.id,
        action="iot.event_recorded",
        resource_type="iot_event",
        resource_id=event.id,
        case_id=case_id,
        metadata={
            "device_id": str(device.id),
            "event_type": event.event_type,
            "event_time": event.event_time.isoformat(),
        },
    )
    await session.commit()
    return _to_event_out(event)


@router.get("/{case_id}/iot/devices/{device_id}/stats", response_model=IoTDeviceStatsOut)
async def device_stats(
    case_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IoTDeviceStatsOut:
    """Summary statistics for a single device's telemetry."""
    await get_case_or_404(case_id, request, session)
    await _get_device_or_404(case_id, device_id, session)
    rows = await session.execute(
        select(IoTEvent.event_type).where(
            IoTEvent.case_id == case_id, IoTEvent.device_id == device_id
        )
    )
    types = Counter(row[0] for row in rows)
    bounds = await session.execute(
        select(func.min(IoTEvent.event_time), func.max(IoTEvent.event_time)).where(
            IoTEvent.case_id == case_id, IoTEvent.device_id == device_id
        )
    )
    first_at, last_at = bounds.one()
    return IoTDeviceStatsOut(
        device_id=device_id,
        event_count=sum(types.values()),
        by_type=dict(types),
        first_event_at=first_at,
        last_event_at=last_at,
    )

"""Field device service: registration, approval, revocation, and signature verification."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FieldDevice


def _derive_fingerprint(public_key_pem: str) -> str:
    return hashlib.sha256(public_key_pem.encode()).hexdigest()


async def register_device(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    user_id: uuid.UUID | None,
    platform: str,
    serial: str,
    model: str | None,
    firmware_version: str | None,
    public_key: str,
    signature_algorithm: str,
) -> FieldDevice:
    fingerprint = _derive_fingerprint(public_key)
    device = FieldDevice(
        case_id=str(case_id),
        user_id=str(user_id) if user_id else None,
        platform=platform,
        serial=serial,
        model=model,
        firmware_version=firmware_version,
        public_key=public_key,
        signature_algorithm=signature_algorithm,
        fingerprint=fingerprint,
        status="pending",
    )
    session.add(device)
    await session.flush()
    return device


async def get_device(
    session: AsyncSession,
    device_id: uuid.UUID,
) -> FieldDevice | None:
    return await session.get(FieldDevice, device_id)


async def list_devices(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[FieldDevice], int]:
    where = [FieldDevice.case_id == str(case_id)]
    if status is not None:
        where.append(FieldDevice.status == status)
    count_q = select(func.count()).select_from(FieldDevice).where(*where)
    total = (await session.execute(count_q)).scalar_one()
    q = (
        select(FieldDevice)
        .where(*where)
        .order_by(FieldDevice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(q)).scalars())
    return rows, total


async def approve_device(
    *,
    session: AsyncSession,
    device: FieldDevice,
    approved_by: uuid.UUID,
) -> FieldDevice:
    device.status = "approved"
    device.approved_by = str(approved_by)
    await session.flush()
    return device


async def revoke_device(
    *,
    session: AsyncSession,
    device: FieldDevice,
) -> FieldDevice:
    device.status = "revoked"
    device.revoked_at = datetime.now(UTC)
    await session.flush()
    return device


def _load_public_key(pem: str, algorithm: str) -> Any:
    loaded = serialization.load_pem_public_key(pem.encode())
    if algorithm == "Ed25519":
        if not isinstance(loaded, ed25519.Ed25519PublicKey):
            raise ValueError("key is not Ed25519")
        return loaded
    if algorithm == "RSA-SHA256":
        if not isinstance(loaded, rsa.RSAPublicKey):
            raise ValueError("key is not RSA")
        return loaded
    raise ValueError(f"unsupported algorithm: {algorithm}")


def verify_signature(
    public_key_pem: str,
    algorithm: str,
    data: bytes,
    signature: bytes,
) -> bool:
    key = _load_public_key(public_key_pem, algorithm)
    try:
        if algorithm == "Ed25519":
            assert isinstance(key, ed25519.Ed25519PublicKey)
            key.verify(signature, data)
            return True
        assert isinstance(key, rsa.RSAPublicKey)
        key.verify(
            signature,
            data,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


async def update_last_seen(
    *,
    session: AsyncSession,
    device: FieldDevice,
    at: datetime | None = None,
) -> FieldDevice:
    """Records an approved device's last-seen timestamp (heartbeat)."""
    device.last_seen_at = at or datetime.now(UTC)
    await session.flush()
    return device


async def delete_device(
    *,
    session: AsyncSession,
    device: FieldDevice,
) -> None:
    await session.delete(device)
    await session.flush()

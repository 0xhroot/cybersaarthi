"""Desktop/USB import package verification and ingestion.

Server-side, this service is the single authority for what enters the system.
It validates: (1) manifest schema, (2) device identity + status, (3) signature
over the canonical manifest bytes, (4) per-file SHA-256 hash check, (5) replay
detection (hash uniqueness), and (6) structural duplication within a single
manifest. Every check is non-bypassable. The CLI importer is just a transport
helper that recomputes hashes for local UX only.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiHTTPException
from app.core.config import Settings
from app.db.storage import Storage
from app.models import (
    EvidenceFile,
    FieldDevice,
)
from app.repositories.evidence_repository import EvidenceRepository
from app.services import audit as audit_svc
from app.services.devices import verify_signature
from app.services.timeline import record_event

_CODE_DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
_CODE_DEVICE_REVOKED = "DEVICE_REVOKED"
_CODE_DEVICE_UNAPPROVED = "DEVICE_UNAPPROVED"
_CODE_SIGNATURE_INVALID = "SIGNATURE_INVALID"
_CODE_HASH_MISMATCH = "HASH_MISMATCH"
_CODE_REPLAY = "REPLAY_DETECTED"
_CODE_MANIFEST_INVALID = "MANIFEST_INVALID"
_CODE_DUPLICATE_FILENAME = "DUPLICATE_FILENAME_IN_MANIFEST"

_MAX_MANIFEST_SIZE = 1024 * 1024  # 1 MiB


def _load_manifest(raw: bytes) -> dict[str, Any]:
    if len(raw) > _MAX_MANIFEST_SIZE:
        raise ApiHTTPException(413, _CODE_MANIFEST_INVALID, "manifest too large")
    try:
        data = json.loads(raw)
    except Exception:
        raise ApiHTTPException(422, _CODE_MANIFEST_INVALID, "manifest is not valid JSON") from None
    for key in ("schema_version", "case_id", "device_serial", "collection_name", "evidence_files"):
        if key not in data:
            raise ApiHTTPException(422, _CODE_MANIFEST_INVALID, f"missing manifest key: {key}")
    files = data.get("evidence_files")
    if not isinstance(files, list) or not files:
        raise ApiHTTPException(
            422, _CODE_MANIFEST_INVALID, "evidence_files must be a non-empty list"
        )
    for i, entry in enumerate(files):
        for fld in ("filename", "sha256", "size_bytes"):
            if fld not in entry:
                raise ApiHTTPException(
                    422, _CODE_MANIFEST_INVALID, f"evidence_files[{i}] missing '{fld}'"
                )
    return data


def _manifest_canonical(manifest: dict[str, Any]) -> bytes:
    canonical = {
        "schema_version": manifest.get("schema_version"),
        "case_id": manifest.get("case_id"),
        "device_serial": manifest.get("device_serial"),
        "collection_name": manifest.get("collection_name"),
        "evidence_files": manifest.get("evidence_files"),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()


async def _resolve_device(
    session: AsyncSession,
    case_id: uuid.UUID,
    serial: str,
) -> FieldDevice:
    result = await session.execute(
        select(FieldDevice).where(
            FieldDevice.case_id == str(case_id),
            FieldDevice.serial == serial,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise ApiHTTPException(
            404, _CODE_DEVICE_NOT_FOUND, f"device '{serial}' not registered in this case"
        )
    if device.status == "revoked":
        raise ApiHTTPException(403, _CODE_DEVICE_REVOKED, "device has been revoked")
    if device.status != "approved":
        raise ApiHTTPException(403, _CODE_DEVICE_UNAPPROVED, "device is not approved")
    return device


async def _check_replay(session: AsyncSession, case_id: uuid.UUID, sha256: str) -> None:
    existing = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.case_id == str(case_id),
            EvidenceFile.sha256 == sha256,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ApiHTTPException(409, _CODE_REPLAY, f"evidence with sha256 {sha256} already exists")


async def _verify_single_file(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    manifest_entry: dict[str, Any],
    file_bytes: bytes,
) -> None:
    expected = manifest_entry["sha256"]
    actual = hashlib.sha256(file_bytes).hexdigest()
    if actual != expected:
        raise ApiHTTPException(
            422,
            _CODE_HASH_MISMATCH,
            f"hash mismatch for {manifest_entry['filename']}: expected {expected}, got {actual}",
        )


async def import_package(
    *,
    session: AsyncSession,
    storage: Storage,
    settings: Settings,
    case_id: uuid.UUID,
    manifest_bytes: bytes,
    manifest_signature: bytes,
    file_slices: list[tuple[str, bytes]],
    actor_id: uuid.UUID | None,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_bytes)
    if str(manifest.get("case_id")) != str(case_id):
        raise ApiHTTPException(
            422, _CODE_MANIFEST_INVALID, "case_id in manifest does not match URL"
        )

    device = await _resolve_device(session, case_id, manifest["device_serial"])

    canonical = _manifest_canonical(manifest)
    if not verify_signature(
        device.public_key, device.signature_algorithm, canonical, manifest_signature
    ):
        raise ApiHTTPException(
            403, _CODE_SIGNATURE_INVALID, "manifest signature verification failed"
        )

    seen_hashes: set[str] = set()
    seen_filenames: set[str] = set()
    for entry in manifest["evidence_files"]:
        if entry["filename"] in seen_filenames:
            raise ApiHTTPException(
                422, _CODE_DUPLICATE_FILENAME, f"duplicate filename: {entry['filename']}"
            )
        seen_filenames.add(entry["filename"])
        if entry["sha256"] in seen_hashes:
            raise ApiHTTPException(
                422, _CODE_REPLAY, f"duplicate hash in manifest: {entry['sha256']}"
            )
        seen_hashes.add(entry["sha256"])

    evidence_repo = EvidenceRepository(session)

    manifest_entry_map = {e["filename"]: e for e in manifest["evidence_files"]}

    # Phase 1: pre-verify every file before any object is stored so a failure
    # cannot leave orphaned MinIO objects behind.
    verified: list[tuple[str, bytes, dict[str, Any]]] = []
    for filename, file_bytes in file_slices:
        entry = manifest_entry_map.get(filename)
        if entry is None:
            continue
        await _check_replay(session, case_id, entry["sha256"])
        await _verify_single_file(
            session=session,
            case_id=case_id,
            manifest_entry=entry,
            file_bytes=file_bytes,
        )
        verified.append((filename, file_bytes, entry))

    # Phase 2: store every verified file and record per-file events.
    imported_count = 0
    evidence_ids: list[str] = []

    for filename, file_bytes, entry in verified:
        stored_key = f"evidence/{case_id}/{uuid.uuid4().hex}/{filename}"
        storage.client().put_object(
            Bucket=storage.bucket_name(),
            Key=stored_key,
            Body=file_bytes,
            ContentType="application/octet-stream",
        )
        ev = await evidence_repo.create_evidence_file(
            case_id=case_id,
            data_source_id=None,
            original_filename=filename,
            stored_key=stored_key,
            content_type="application/octet-stream",
            file_size=len(file_bytes),
            sha256=entry["sha256"],
            metadata_json=entry.get("metadata"),
        )
        imported_count += 1
        evidence_ids.append(str(ev.id))
        await record_event(
            session=session,
            case_id=case_id,
            occurred_at=datetime.now(UTC),
            kind="evidence_uploaded",
            title=f"Field evidence '{filename}' imported from device '{manifest['device_serial']}'",
            description=(
                f"Package {manifest.get('collection_name', 'unknown collection')} · "
                "per-file SHA-256 verified"
            ),
            evidence_file_id=ev.id,
            device_id=uuid.UUID(str(device.id)),
            actor_user_id=actor_id,
        )

    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=datetime.now(UTC),
        kind="package_imported",
        title=f"Import package received from device '{manifest['device_serial']}'",
        description=(
            f"{imported_count} evidence file(s) · "
            f"collection '{manifest.get('collection_name', 'unknown collection')}' · "
            "signature and per-file SHA-256 verified"
        ),
        device_id=uuid.UUID(str(device.id)),
        actor_user_id=actor_id,
        payload={"imported_evidence_count": imported_count, "evidence_ids": evidence_ids},
    )
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action="import.package",
        resource_type="package",
        resource_id=case_id,
        case_id=case_id,
        metadata={
            "device_serial": manifest["device_serial"],
            "evidence_count": imported_count,
            "evidence_ids": evidence_ids,
        },
    )
    return {
        "case_id": str(case_id),
        "device_serial": manifest["device_serial"],
        "imported_evidence_count": imported_count,
        "evidence_ids": evidence_ids,
        "collection_name": manifest.get("collection_name"),
    }

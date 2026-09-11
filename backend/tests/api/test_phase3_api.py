"""API contract tests for Phase 3 features: collections, devices, hypotheses,
timeline, reports, search, evidence restore, entity resolution, and import.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case, Entity, EntityCandidate, EntityMatch, SourceRecord
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import delete

from tests.api.conftest import ApiUser

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    b"Rajesh Kumar,9876543211,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
).decode()


@pytest.fixture
async def p3_case(database: Database, api_user: ApiUser) -> tuple[uuid.UUID, Database]:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"P3-{uuid.uuid4().hex[:8]}",
        title="phase-3 api test case",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
    yield case.id, database
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case.id))
        await session.commit()


@pytest.fixture
async def admin_http_client(user_factory):
    """Client authenticated as an ADMIN (device approve/revoke needs users.manage)."""
    import httpx
    from app.main import app

    admin = await user_factory(role="ADMIN")
    headers = {"Authorization": f"Bearer {admin.token}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers
    ) as client:
        yield client


async def _upload_one(http_client, case_id: uuid.UUID) -> dict:
    prefix = get_settings().API_V1_PREFIX
    response = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _evidence_objects(storage, case_id: uuid.UUID) -> list[str]:
    from asyncio import to_thread

    return list(await to_thread(storage.list_keys, f"evidence/{case_id}/"))


async def _graph_entity_count(graph_store, case_id: uuid.UUID) -> int:
    async with graph_store.driver().session() as session:
        result = await session.run(
            "MATCH (n:Entity) WHERE n.case_id = $cid RETURN count(n) AS cnt",
            cid=str(case_id),
        )
        record = await result.single()
        return int(record["cnt"])


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


async def test_collection_lifecycle(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/collections",
        json={"name": "Phone Records", "description": "call logs"},
    )
    assert resp.status_code == 201, resp.text
    col = resp.json()
    assert col["name"] == "Phone Records"
    assert col["status"] == "draft"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/collections")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await http_client.get(f"{prefix}/cases/{case_id}/collections/{col['id']}")
    assert resp.status_code == 200
    assert resp.json()["description"] == "call logs"

    resp = await http_client.patch(
        f"{prefix}/cases/{case_id}/collections/{col['id']}",
        json={"name": "Phone Records v2"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Phone Records v2"

    resp = await http_client.post(f"{prefix}/cases/{case_id}/collections/{col['id']}/seal")
    assert resp.status_code == 200
    sealed = resp.json()
    assert sealed["status"] == "sealed"
    assert sealed["sealed_at"] is not None

    # Sealed collections are immutable: patching them is rejected (409).
    resp = await http_client.patch(
        f"{prefix}/cases/{case_id}/collections/{col['id']}",
        json={"description": "late change"},
    )
    assert resp.status_code == 409, resp.text

    resp = await http_client.delete(f"{prefix}/cases/{case_id}/collections/{col['id']}")
    assert resp.status_code == 204

    resp = await http_client.get(f"{prefix}/cases/{case_id}/collections")
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Field Devices
# ---------------------------------------------------------------------------

_KEY_PATH = "/tmp/_cybersaarthi_test_key.pem"
RSA_PUBLIC_KEY_PEM: str | None = None
_RSA_PRIVATE_KEY: rsa.RSAPrivateKey | None = None


def _gen_rsa():
    global RSA_PUBLIC_KEY_PEM, _RSA_PRIVATE_KEY
    if RSA_PUBLIC_KEY_PEM is not None:
        return
    _RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    RSA_PUBLIC_KEY_PEM = (
        _RSA_PRIVATE_KEY.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def _sign_data(data: bytes) -> str:
    assert _RSA_PRIVATE_KEY is not None
    sig = _RSA_PRIVATE_KEY.sign(data, padding.PKCS1v15(), hashes.SHA256())
    return sig.hex()


async def test_device_register_approve_revoke(http_client, admin_http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "DEV-001",
            "model": "Pixel 8",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    assert resp.status_code == 201, resp.text
    dev = resp.json()
    assert dev["status"] == "pending"
    assert dev["serial"] == "DEV-001"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/devices")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{dev['id']}/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    resp = await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{dev['id']}/revoke")
    assert resp.status_code == 200, resp.text
    revoked = resp.json()
    assert revoked["status"] == "revoked"


async def test_device_verify_key(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "DEV-VERIFY",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    dev_id = resp.json()["id"]

    data = b"test data to sign"
    good_sig = _sign_data(data)

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices/{dev_id}/verify-key",
        json={"data": data.decode(), "signature": good_sig},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid"] is True

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices/{dev_id}/verify-key",
        json={"data": data.decode(), "signature": "00" * 64},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------


async def test_hypothesis_lifecycle(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/hypotheses",
        json={
            "kind": "hypothesis",
            "title": "Fake call log",
            "statement": "Rajesh used burner phones",
            "confidence": 0.8,
        },
    )
    assert resp.status_code == 201, resp.text
    hyp = resp.json()
    assert hyp["status"] == "proposed"
    assert hyp["evidence_weight"] == 0

    resp = await http_client.get(f"{prefix}/cases/{case_id}/hypotheses")
    assert resp.json()["total"] == 1

    resp = await http_client.get(f"{prefix}/cases/{case_id}/hypotheses/{hyp['id']}")
    assert resp.status_code == 200

    # valid transition: proposed -> under_review
    resp = await http_client.patch(
        f"{prefix}/cases/{case_id}/hypotheses/{hyp['id']}/status",
        json={"status": "under_review"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "under_review"

    # invalid transition: under_review -> proposed
    resp = await http_client.patch(
        f"{prefix}/cases/{case_id}/hypotheses/{hyp['id']}/status",
        json={"status": "proposed"},
    )
    assert resp.status_code == 409

    # link evidence
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/hypotheses/{hyp['id']}/evidence",
        json={"evidence_id": str(uuid.uuid4()), "support": True},
    )
    assert resp.status_code == 200
    assert resp.json()["evidence_weight"] == 1

    # delete
    resp = await http_client.delete(f"{prefix}/cases/{case_id}/hypotheses/{hyp['id']}")
    assert resp.status_code == 204

    resp = await http_client.get(f"{prefix}/cases/{case_id}/hypotheses")
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


async def test_timeline_create_and_list(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    now = datetime.now(UTC).isoformat()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/timeline",
        json={
            "occurred_at": now,
            "kind": "case_event",
            "title": "Witness interview #1",
            "description": "Primary witness statement",
        },
    )
    assert resp.status_code == 201, resp.text
    ev = resp.json()
    assert ev["kind"] == "case_event"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    assert resp.json()["total"] == 1

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline?kind=case_event")
    assert resp.json()["total"] == 1

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline?kind=arrest")
    assert resp.json()["total"] == 0


async def test_timeline_created_by_operations(http_client, p3_case) -> None:
    """Collection and device operations should record timeline events."""
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    await http_client.post(
        f"{prefix}/cases/{case_id}/collections",
        json={"name": "Audit Trail Col"},
    )
    await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "TL-DEV-1",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    kinds = [ev["kind"] for ev in resp.json()["items"]]
    assert "collection_created" in kinds
    assert "device_registered" in kinds


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


async def test_report_json_generate_and_download(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/reports",
        json={"report_type": "case_summary", "format": "json", "title": "Summary JSON"},
    )
    assert resp.status_code == 201, resp.text
    rpt = resp.json()
    assert rpt["status"] == "ready"
    assert rpt["format"] == "json"
    assert (rpt["byte_size"] or 0) > 0

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports")
    assert resp.json()["total"] == 1

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports/{rpt['id']}")
    assert resp.status_code == 200

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports/{rpt['id']}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    body = resp.json()
    assert body["case_id"] == str(case_id)


async def test_report_csv_shape(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/reports",
        json={"report_type": "case_summary", "format": "csv"},
    )
    assert resp.status_code == 201, resp.text
    rpt = resp.json()

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports/{rpt['id']}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


async def test_report_pdf_shape(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/reports",
        json={"report_type": "timeline", "format": "pdf", "title": "Timeline PDF"},
    )
    assert resp.status_code == 201, resp.text
    rpt = resp.json()

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports/{rpt['id']}/download")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert len(resp.content) > 100  # PDF magic bytes


async def test_report_not_ready_returns_409(http_client, p3_case) -> None:
    """Report in 'failed' status should return 409 on download."""
    from app.models import Report

    case_id, database = p3_case
    prefix = get_settings().API_V1_PREFIX
    factory = database.session_factory()

    report_id = uuid.uuid4()
    async with factory() as session:
        r = Report(
            id=report_id,
            case_id=str(case_id),
            report_type="case_summary",
            format="json",
            title="Failed Report",
            status="failed",
            failure_reason="simulated",
        )
        session.add(r)
        await session.commit()

    resp = await http_client.get(f"{prefix}/cases/{case_id}/reports/{report_id}/download")
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def test_search_finds_ingested_entities(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    evidence = await _upload_one(http_client, case_id)
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/ingest",
        json={"evidence_file_id": evidence["id"], "metadata": {"source": "test"}},
    )
    assert resp.status_code == 200

    resp = await http_client.get(f"{prefix}/cases/{case_id}/search", params={"q": "rajesh"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    kinds = [item["kind"] for item in resp.json()["items"]]
    assert "entity" in kinds


# ---------------------------------------------------------------------------
# Evidence Restore
# ---------------------------------------------------------------------------


async def test_evidence_restore_lifecycle(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    evidence = await _upload_one(http_client, case_id)
    eid = evidence["id"]

    resp = await http_client.delete(f"{prefix}/cases/{case_id}/evidence/{eid}")
    assert resp.status_code == 204

    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence/{eid}")
    assert resp.status_code == 404

    resp = await http_client.post(f"{prefix}/cases/{case_id}/evidence/{eid}/restore")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] is True
    assert body["content_restored"] is True

    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence/{eid}")
    assert resp.status_code == 200


async def test_evidence_restore_active_returns_409(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    evidence = await _upload_one(http_client, case_id)
    resp = await http_client.post(f"{prefix}/cases/{case_id}/evidence/{evidence['id']}/restore")
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Async Ingest
# ---------------------------------------------------------------------------


async def test_async_ingest_returns_running(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    evidence = await _upload_one(http_client, case_id)
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/ingest",
        params={"async": "true"},
        json={"evidence_file_id": evidence["id"], "metadata": {}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job"]["status"] == "running"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/ingest-jobs")
    assert resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Entity Resolution (accept/reject/merge)
# ---------------------------------------------------------------------------


async def test_entity_accept_and_reject_match(http_client, p3_case) -> None:
    case_id, database = p3_case
    prefix = get_settings().API_V1_PREFIX
    factory = database.session_factory()

    evidence = await _upload_one(http_client, case_id)
    target_id = uuid.uuid4()
    match_id = uuid.uuid4()
    async with factory() as session:
        record = SourceRecord(
            evidence_file_id=str(evidence["id"]), record_no=1, raw_data={"name": "alice"}
        )
        session.add(record)
        await session.flush()
        candidate = EntityCandidate(
            source_record_id=str(record.id),
            entity_type="person",
            raw_value="alice smith",
            normalized_value="alice smith",
            blocking_key="alice smith",
            resolution_status="review",
        )
        target = Entity(
            id=target_id,
            case_id=str(case_id),
            entity_type="person",
            canonical_value="alice",
            display_value="Alice",
            blocking_key="alice",
        )
        session.add_all([candidate, target])
        await session.flush()
        match = EntityMatch(
            id=match_id,
            case_id=str(case_id),
            source_candidate_id=str(candidate.id),
            target_entity_id=str(target.id),
            decision="review",
            score=0.92,
            status="review",
        )
        session.add(match)
        await session.commit()

    resp = await http_client.post(f"{prefix}/cases/{case_id}/resolution/matches/{match_id}/accept")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"

    async with factory() as session:
        m = await session.get(EntityMatch, match_id)
    assert m is not None and m.status == "active"


async def test_entity_merge(http_client, p3_case) -> None:
    case_id, database = p3_case
    prefix = get_settings().API_V1_PREFIX
    factory = database.session_factory()

    primary = uuid.uuid4()
    doomed = uuid.uuid4()
    async with factory() as session:
        p = Entity(
            id=primary,
            case_id=str(case_id),
            entity_type="person",
            canonical_value="bob",
            display_value="Bob",
            blocking_key="bob",
        )
        d = Entity(
            id=doomed,
            case_id=str(case_id),
            entity_type="person",
            canonical_value="robert",
            display_value="Robert",
            blocking_key="robert",
        )
        session.add_all([p, d])
        await session.commit()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/entities/merge",
        json={
            "primary_entity_id": str(primary),
            "merge_entity_id": str(doomed),
        },
    )
    assert resp.status_code == 200, resp.text
    merged = resp.json()
    assert merged["id"] == str(primary)

    async with factory() as session:
        row = await session.get(Entity, doomed)
    assert row is not None
    assert str(row.merged_into_id) == str(primary)


# ---------------------------------------------------------------------------
# Import Packages
# ---------------------------------------------------------------------------


async def test_import_package_valid(http_client, admin_http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "IMPORT-001",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    resp = await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")
    assert resp.status_code == 200

    evidence_content = b"name,amount\na,1\n"
    evidence_hash = hashlib.sha256(evidence_content).hexdigest()

    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "IMPORT-001",
        "collection_name": "USB Import",
        "evidence_files": [
            {"filename": "trans.csv", "sha256": evidence_hash, "size_bytes": len(evidence_content)}
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode(), "application/json"),
            "manifest_signature": (
                "sig.bin",
                bytes.fromhex(manifest_sig),
                "application/octet-stream",
            ),
            "files": ("trans.csv", evidence_content, "text/csv"),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["imported_evidence_count"] == 1
    assert body["device_serial"] == "IMPORT-001"

    # Imported evidence surfaces on the case timeline, linked to the device.
    timeline = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    assert timeline.status_code == 200
    imported = [
        e for e in timeline.json()["items"]
        if e["kind"] == "evidence_uploaded" and "IMPORT-001" in (e["title"] or "")
    ]
    assert imported, "package import must record a timeline event"
    assert imported[0]["evidence_file_id"] == body["evidence_ids"][0]
    assert imported[0]["device_id"] == device["id"]


async def test_import_package_bad_signature(http_client, admin_http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "IMPORT-BADSIG",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "IMPORT-BADSIG",
        "collection_name": "Bad Sig",
        "evidence_files": [{"filename": "f.csv", "sha256": "a" * 64, "size_bytes": 10}],
    }
    bad_sig = b"\x00" * 256

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode(), "application/json"),
            "manifest_signature": ("sig.bin", bad_sig, "application/octet-stream"),
            "files": ("f.csv", b"x" * 10, "text/csv"),
        },
    )
    assert resp.status_code == 403, resp.text


async def test_import_package_revoked_device(http_client, admin_http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "IMPORT-REVOKED",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/revoke")

    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "IMPORT-REVOKED",
        "collection_name": "Revoked",
        "evidence_files": [{"filename": "f.csv", "sha256": "b" * 64, "size_bytes": 5}],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode(), "application/json"),
            "manifest_signature": (
                "sig.bin",
                bytes.fromhex(manifest_sig),
                "application/octet-stream",
            ),
            "files": ("f.csv", b"y" * 5, "text/csv"),
        },
    )
    assert resp.status_code == 403, resp.text


async def test_import_package_tampered_file_rejected(
    http_client, admin_http_client, p3_case
) -> None:
    """A file whose bytes differ from the manifest digest must be rejected.

    The signature is valid (it covers the manifest) but the uploaded content has
    been tampered with, so the per-file SHA-256 check has to block the import.
    """
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "IMPORT-TAMPER",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    original = b"name,amount\na,1\n"
    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "IMPORT-TAMPER",
        "collection_name": "USB Import",
        "evidence_files": [
            {
                "filename": "trans.csv",
                "sha256": hashlib.sha256(original).hexdigest(),
                "size_bytes": len(original),
            }
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    tampered = original + b"evil"
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode(), "application/json"),
            "manifest_signature": (
                "sig.bin",
                bytes.fromhex(manifest_sig),
                "application/octet-stream",
            ),
            "files": ("trans.csv", tampered, "text/csv"),
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "HASH_MISMATCH"


async def test_import_package_multifile_tampered_first_no_orphans(
    http_client, admin_http_client, p3_case, storage, graph_store
) -> None:
    """Tampered FIRST file in a 3-file package → 422 HASH_MISMATCH.

    All 0 evidence rows, 0 timeline events, 0 MinIO orphans.
    """
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "MULTIFILE-T1",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    content1 = b"file1-data"
    content2 = b"file2-data"
    content3 = b"file3-data"
    h1 = hashlib.sha256(content1).hexdigest()
    h2 = hashlib.sha256(content2).hexdigest()
    h3 = hashlib.sha256(content3).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "MULTIFILE-T1",
        "collection_name": "MultiTamper",
        "evidence_files": [
            {"filename": "f1.csv", "sha256": h1, "size_bytes": len(content1)},
            {"filename": "f2.csv", "sha256": h2, "size_bytes": len(content2)},
            {"filename": "f3.csv", "sha256": h3, "size_bytes": len(content3)},
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    tampered1 = b"EVIL-f1"
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files=[
            ("manifest", ("manifest.json", json.dumps(manifest).encode(), "application/json")),
            (
                "manifest_signature",
                ("sig.bin", bytes.fromhex(manifest_sig), "application/octet-stream"),
            ),
            ("files", ("f1.csv", tampered1, "text/csv")),
            ("files", ("f2.csv", content2, "text/csv")),
            ("files", ("f3.csv", content3, "text/csv")),
        ],
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "HASH_MISMATCH"

    # No evidence rows
    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert resp.json()["total"] == 0

    # No timeline events
    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    kinds = [e["kind"] for e in resp.json()["items"]]
    assert "evidence_uploaded" not in kinds, "failed import must not emit evidence events"
    assert "package_imported" not in kinds, "failed import must not emit package events"

    # No MinIO orphans, no graph nodes
    assert await _evidence_objects(storage, case_id) == []
    assert await _graph_entity_count(graph_store, case_id) == 0


async def test_import_package_multifile_tampered_middle_no_orphans(
    http_client, admin_http_client, p3_case, storage, graph_store
) -> None:
    """Tampered MIDDLE file in a 3-file package → 422 HASH_MISMATCH, zero orphans."""
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "MULTIFILE-T2",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    content1 = b"file1-data"
    content2 = b"file2-data"
    content3 = b"file3-data"
    h1 = hashlib.sha256(content1).hexdigest()
    h2 = hashlib.sha256(content2).hexdigest()
    h3 = hashlib.sha256(content3).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "MULTIFILE-T2",
        "collection_name": "MultiTamper",
        "evidence_files": [
            {"filename": "f1.csv", "sha256": h1, "size_bytes": len(content1)},
            {"filename": "f2.csv", "sha256": h2, "size_bytes": len(content2)},
            {"filename": "f3.csv", "sha256": h3, "size_bytes": len(content3)},
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    tampered2 = b"EVIL-f2"
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files=[
            ("manifest", ("manifest.json", json.dumps(manifest).encode(), "application/json")),
            (
                "manifest_signature",
                ("sig.bin", bytes.fromhex(manifest_sig), "application/octet-stream"),
            ),
            ("files", ("f1.csv", content1, "text/csv")),
            ("files", ("f2.csv", tampered2, "text/csv")),
            ("files", ("f3.csv", content3, "text/csv")),
        ],
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "HASH_MISMATCH"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert resp.json()["total"] == 0

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    kinds = [e["kind"] for e in resp.json()["items"]]
    assert "evidence_uploaded" not in kinds, "failed import must not emit evidence events"
    assert "package_imported" not in kinds, "failed import must not emit package events"

    # No MinIO orphans, no graph nodes
    assert await _evidence_objects(storage, case_id) == []
    assert await _graph_entity_count(graph_store, case_id) == 0


async def test_import_package_multifile_tampered_last_no_orphans(
    http_client, admin_http_client, p3_case, storage, graph_store
) -> None:
    """Tampered LAST file in a 3-file package → 422 HASH_MISMATCH, zero orphans."""
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "MULTIFILE-T3",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    content1 = b"file1-data"
    content2 = b"file2-data"
    content3 = b"file3-data"
    h1 = hashlib.sha256(content1).hexdigest()
    h2 = hashlib.sha256(content2).hexdigest()
    h3 = hashlib.sha256(content3).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "MULTIFILE-T3",
        "collection_name": "MultiTamper",
        "evidence_files": [
            {"filename": "f1.csv", "sha256": h1, "size_bytes": len(content1)},
            {"filename": "f2.csv", "sha256": h2, "size_bytes": len(content2)},
            {"filename": "f3.csv", "sha256": h3, "size_bytes": len(content3)},
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    tampered3 = b"EVIL-f3"
    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files=[
            ("manifest", ("manifest.json", json.dumps(manifest).encode(), "application/json")),
            (
                "manifest_signature",
                ("sig.bin", bytes.fromhex(manifest_sig), "application/octet-stream"),
            ),
            ("files", ("f1.csv", content1, "text/csv")),
            ("files", ("f2.csv", content2, "text/csv")),
            ("files", ("f3.csv", tampered3, "text/csv")),
        ],
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "HASH_MISMATCH"

    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert resp.json()["total"] == 0

    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    kinds = [e["kind"] for e in resp.json()["items"]]
    assert "evidence_uploaded" not in kinds, "failed import must not emit evidence events"
    assert "package_imported" not in kinds, "failed import must not emit package events"

    # No MinIO orphans, no graph nodes
    assert await _evidence_objects(storage, case_id) == []
    assert await _graph_entity_count(graph_store, case_id) == 0


async def test_import_package_multifile_intact_3files(
    http_client, admin_http_client, p3_case, storage
) -> None:
    """Intact 3-file package → 201, 3 evidence IDs, zero orphans."""
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX
    _gen_rsa()

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": "MULTIFILE-OK",
            "public_key": RSA_PUBLIC_KEY_PEM,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    device = resp.json()
    await admin_http_client.post(f"{prefix}/cases/{case_id}/devices/{device['id']}/approve")

    content1 = b"file1-data-ok"
    content2 = b"file2-data-ok"
    content3 = b"file3-data-ok"
    h1 = hashlib.sha256(content1).hexdigest()
    h2 = hashlib.sha256(content2).hexdigest()
    h3 = hashlib.sha256(content3).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "case_id": str(case_id),
        "device_serial": "MULTIFILE-OK",
        "collection_name": "MultiOK",
        "evidence_files": [
            {"filename": "f1.csv", "sha256": h1, "size_bytes": len(content1)},
            {"filename": "f2.csv", "sha256": h2, "size_bytes": len(content2)},
            {"filename": "f3.csv", "sha256": h3, "size_bytes": len(content3)},
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sig = _sign_data(canonical)

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files=[
            ("manifest", ("manifest.json", json.dumps(manifest).encode(), "application/json")),
            (
                "manifest_signature",
                ("sig.bin", bytes.fromhex(manifest_sig), "application/octet-stream"),
            ),
            ("files", ("f1.csv", content1, "text/csv")),
            ("files", ("f2.csv", content2, "text/csv")),
            ("files", ("f3.csv", content3, "text/csv")),
        ],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["imported_evidence_count"] == 3
    assert len(body["evidence_ids"]) == 3

    # 3 evidence rows
    resp = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert resp.json()["total"] == 3

    # 3 evidence_uploaded + 1 package_imported = 4 timeline events
    resp = await http_client.get(f"{prefix}/cases/{case_id}/timeline")
    kinds = [e["kind"] for e in resp.json()["items"]]
    assert kinds.count("evidence_uploaded") == 3
    assert kinds.count("package_imported") == 1

    # Zero orphans (objects exist = exactly 3, matching 3 evidence rows)
    from asyncio import to_thread
    keys = await to_thread(storage.list_keys, f"evidence/{case_id}/")
    assert len(keys) == 3


async def test_import_package_invalid_manifest_missing_key(http_client, p3_case) -> None:
    case_id, _ = p3_case
    prefix = get_settings().API_V1_PREFIX

    resp = await http_client.post(
        f"{prefix}/cases/{case_id}/import/packages",
        files={
            "manifest": (
                "manifest.json",
                json.dumps({"schema_version": "1.0"}).encode(),
                "application/json",
            ),
            "manifest_signature": ("sig.bin", b"\x00", "application/octet-stream"),
            "files": ("f.csv", b"data", "text/csv"),
        },
    )
    assert resp.status_code == 422, resp.text

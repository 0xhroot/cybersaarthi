"""Heartbeat / last-seen tests for approved field devices.

Covers the signed-liveness contract: only an approved device in case scope,
proving identity with its registered key, may write ``last_seen_at``. No
credential, token or sensitive payload is ever transmitted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from app.core.config import get_settings
from app.models import AuditLog, Case
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import delete, func, select

PREFIX = get_settings().API_V1_PREFIX

# Case ids created via ``_make_case`` during this module; consumed by the
# ``_case_hygiene`` teardown fixture.
_created_case_ids: list[str] = []


def _new_rsa() -> tuple[str, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return pem, key


def _sign(priv: rsa.RSAPrivateKey, message: bytes) -> str:
    sig = priv.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return sig.hex()


def _heartbeat_message(case_id, device_id, epoch_ms: int) -> bytes:
    return (
        f"cybersaarthi-heartbeat/1\ncase_id={case_id}\ndevice_id={device_id}\ntimestamp={epoch_ms}"
    ).encode()


@pytest.fixture
async def admin_http_client(user_factory):
    admin = await user_factory(role="ADMIN")
    headers = {"Authorization": f"Bearer {admin.token}"}
    transport = httpx.ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers
    ) as client:
        yield client


async def _make_case(http_client) -> str:
    """Create a synthetic case AND register it for guaranteed teardown.

    The API suite runs against the shared dev database and the API exposes
    no case-delete endpoint, so every case created here must be removed by
    the module hygiene fixture below; untracked creation used to leak
    ``heartbeat <id>`` cases into the admin's case list (424 accumulated).
    """
    resp = await http_client.post(
        f"{PREFIX}/cases",
        json={"title": f"heartbeat {uuid.uuid4().hex[:8]}", "description": None, "status": "open"},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]
    _created_case_ids.append(case_id)
    return case_id


@pytest.fixture(scope="module", autouse=True)
async def _case_hygiene(database):
    """Delete every case this module creates and prove none were left behind.

    Teardown removes the tracked cases together with their audit rows (the
    ``audit_logs.case_id`` FK is ON DELETE SET NULL, which would otherwise
    orphan synthetic audit entries); field devices and other case-scoped
    children cascade at the database. The final assertion is the regression
    guard: if any test in this module creates a case without going through
    ``_make_case``, the shared database ends up fuller than it started and
    the suite fails loudly.
    """
    factory = database.session_factory()
    async with factory() as session:
        before = await session.scalar(
            select(func.count(Case.id)).where(Case.title.like("heartbeat %"))
        )
    _created_case_ids.clear()
    yield
    ids = [uuid.UUID(c) for c in _created_case_ids]
    if ids:
        async with factory() as session:
            await session.execute(delete(AuditLog).where(AuditLog.case_id.in_(ids)))
            await session.execute(delete(Case).where(Case.id.in_(ids)))
            await session.commit()
    async with factory() as session:
        after = await session.scalar(
            select(func.count(Case.id)).where(Case.title.like("heartbeat %"))
        )
    assert after <= before, (
        f"device heartbeat tests leaked {after - before} 'heartbeat %' case(s) "
        f"into the shared database (before={before}, after={after})"
    )


async def _register_device(http_client, case_id: str, pem: str, serial: str) -> dict:
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices",
        json={
            "platform": "android_mobile",
            "serial": serial,
            "model": "Pixel-9",
            "public_key": pem,
            "signature_algorithm": "RSA-SHA256",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approve(admin_http_client, case_id: str, device_id: str) -> None:
    resp = await admin_http_client.post(f"{PREFIX}/cases/{case_id}/devices/{device_id}/approve")
    assert resp.status_code == 200, resp.text


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


async def test_heartbeat_updates_last_seen(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-1")
    await _approve(admin_http_client, case_id, device["id"])

    ts = _now_ms()
    sig = _sign(priv, _heartbeat_message(case_id, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": sig},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "approved"
    assert body["last_seen_at"] is not None

    listed = await http_client.get(f"{PREFIX}/cases/{case_id}/devices", params={"limit": 100})
    item = next(d for d in listed.json()["items"] if d["id"] == device["id"])
    assert item["last_seen_at"] is not None


async def test_heartbeat_rejects_wrong_signature(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    other_pem, other_priv = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-2")
    await _approve(admin_http_client, case_id, device["id"])

    ts = _now_ms()
    wrong = _sign(other_priv, _heartbeat_message(case_id, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": wrong},
    )
    assert resp.status_code == 403, resp.text


async def test_heartbeat_rejects_non_hex_signature(http_client, admin_http_client) -> None:
    pem, _ = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-3")
    await _approve(admin_http_client, case_id, device["id"])
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": _now_ms(), "signature": "not-hex"},
    )
    assert resp.status_code == 400, resp.text


async def test_heartbeat_rejects_stale_timestamp(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-4")
    await _approve(admin_http_client, case_id, device["id"])
    ts = _now_ms() - 10 * 60 * 1000  # 10 minutes in the past
    sig = _sign(priv, _heartbeat_message(case_id, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": sig},
    )
    assert resp.status_code == 400, resp.text


async def test_heartbeat_requires_approved_device(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-5")
    ts = _now_ms()
    sig = _sign(priv, _heartbeat_message(case_id, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": sig},
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert "pending" in body.get("error", {}).get("message", body.get("detail", ""))


async def test_heartbeat_rejects_revoked_device(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    case_id = await _make_case(http_client)
    device = await _register_device(http_client, case_id, pem, "HB-PHONE-6")
    await _approve(admin_http_client, case_id, device["id"])
    revoke = await admin_http_client.post(f"{PREFIX}/cases/{case_id}/devices/{device['id']}/revoke")
    assert revoke.status_code == 200, revoke.text
    ts = _now_ms()
    sig = _sign(priv, _heartbeat_message(case_id, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_id}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": sig},
    )
    assert resp.status_code == 403, resp.text


async def test_heartbeat_cannot_cross_case(http_client, admin_http_client) -> None:
    pem, priv = _new_rsa()
    case_a = await _make_case(http_client)
    case_b = await _make_case(http_client)
    device = await _register_device(http_client, case_a, pem, "HB-PHONE-7")
    await _approve(admin_http_client, case_a, device["id"])
    ts = _now_ms()
    sig = _sign(priv, _heartbeat_message(case_a, device["id"], ts))
    resp = await http_client.post(
        f"{PREFIX}/cases/{case_b}/devices/{device['id']}/heartbeat",
        json={"timestamp_epoch_ms": ts, "signature": sig},
    )
    assert resp.status_code == 404, resp.text


async def test_heartbeat_requires_auth() -> None:
    transport = httpx.ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            f"{PREFIX}/cases/{uuid.uuid4()}/devices/{uuid.uuid4()}/heartbeat",
            json={"timestamp_epoch_ms": _now_ms(), "signature": "00" * 128},
        )
    assert resp.status_code == 401, resp.text

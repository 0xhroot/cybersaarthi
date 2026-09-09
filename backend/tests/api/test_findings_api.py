"""API contract tests: the human-driven findings lifecycle.

The engine only ever produces NEW findings; REVIEWED/DISMISSED/CONFIRMED require
a human acting with the matching permission. Closed findings are immutable for
everyone except ADMIN.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import Case
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from tests.api.conftest import ApiUser

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    b"Rajesh Kumar,9876543211,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
).decode()


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


@pytest.fixture
async def _findings_case(
    http_client, database: Database, api_user: ApiUser
) -> tuple[uuid.UUID, Database, uuid.UUID]:
    """A case owned by api_user with evidence ingested and analytics run."""
    prefix = get_settings().API_V1_PREFIX
    created = await http_client.post(f"{prefix}/cases", json={"title": "findings workflow case"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    uploaded = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv"},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()["id"]

    ingested = await http_client.post(
        f"{prefix}/cases/{case_id}/ingest",
        json={"evidence_file_id": evidence_id},
    )
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()["job"]["status"] == "completed"

    ran = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert ran.status_code == 201, ran.text
    assert ran.json()["status"] == "completed"

    factory = database.session_factory()
    yield case_id, database, evidence_id
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_engine_findings_start_as_new_and_are_readable(http_client, _findings_case) -> None:
    case_id, _, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX

    listed = await http_client.get(f"{prefix}/cases/{case_id}/findings")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 1
    new_findings = [f for f in body["items"] if f["status"] == "NEW"]
    assert new_findings, "the engine must only produce NEW findings"

    stats = await http_client.get(f"{prefix}/cases/{case_id}/findings/stats")
    assert stats.status_code == 200
    assert stats.json()["by_status"]["NEW"] == len(new_findings)

    finding_id = new_findings[0]["id"]
    detail = await http_client.get(f"{prefix}/cases/{case_id}/findings/{finding_id}")
    assert detail.status_code == 200
    assert detail.json()["reviewed_by"] is None
    assert detail.json()["explanation"]  # explainable by construction


async def test_owner_drives_review_then_confirm_with_audit(http_client, _findings_case) -> None:
    case_id, _, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX

    finding_id = await _new_finding_id(http_client, case_id)

    # NEW -> REVIEWED (findings.review).
    reviewed = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "REVIEWED", "reason": "checked the call records"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "REVIEWED"
    assert reviewed.json()["review_comment"] == "checked the call records"
    assert reviewed.json()["reviewed_by"] is not None

    # REPEAT REVIEWED -> no-op, idempotent, no audit row, reviewer unchanged.
    before = await http_client.get(
        f"{prefix}/audit-logs",
        params={"case_id": case_id, "action": "finding.status_changed"},
    )
    before_total = before.json()["total"]
    again = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "REVIEWED"},
    )
    assert again.status_code == 200, again.text
    after = await http_client.get(
        f"{prefix}/audit-logs",
        params={"case_id": case_id, "action": "finding.status_changed"},
    )
    assert after.json()["total"] == before_total
    assert again.json()["reviewed_by"] == reviewed.json()["reviewed_by"]

    # REVIEWED -> CONFIRMED (findings.confirm) records the human verdict.
    confirmed = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "CONFIRMED", "reason": "triangulated with phone records"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"

    events = await http_client.get(
        f"{prefix}/audit-logs",
        params={"case_id": case_id, "action": "finding.status_changed"},
    )
    metadata_by_to = {item["metadata_"]["to"]: item for item in events.json()["items"]}
    assert metadata_by_to["REVIEWED"]["metadata_"]["from"] == "NEW"
    assert metadata_by_to["CONFIRMED"]["metadata_"]["from"] == "REVIEWED"


async def test_closed_findings_are_immutable_for_non_admins(http_client, _findings_case) -> None:
    case_id, _, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX

    finding_id = await _new_finding_id(http_client, case_id)
    confirmed = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200

    rollback = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "REVIEWED"},
    )
    assert rollback.status_code == 422, rollback.text


async def test_invalid_statuses_and_missing_findings_are_rejected(
    http_client, _findings_case
) -> None:
    case_id, _, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX

    finding_id = await _new_finding_id(http_client, case_id)
    for status in ("RESOLVED", "PENDING"):
        response = await http_client.patch(
            f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
            json={"status": status},
        )
        assert response.status_code == 422, (status, response.text)

    missing = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{uuid.uuid4()}/status",
        json={"status": "REVIEWED"},
    )
    assert missing.status_code == 404


async def test_status_permission_gates_review_by_role(
    http_client, _findings_case, user_factory, database: Database
) -> None:
    """Transfer ownership to an ANALYST: review allowed but confirm/dismiss not."""
    case_id, database, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX
    analyst = await user_factory(role="ANALYST")

    # Resolve a target finding while still acting as the owner.
    finding_id = await _new_finding_id(http_client, case_id)

    factory = database.session_factory()
    async with factory() as session:
        await session.execute(update(Case).where(Case.id == case_id).values(owner_id=analyst.id))
        await session.commit()

    # The original owner is now locked out by the IDOR guard.
    locked_out = await http_client.get(f"{prefix}/cases/{case_id}/findings/{finding_id}")
    assert locked_out.status_code == 403

    async with _client(analyst.token) as client:
        reviewed = await client.patch(
            f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
            json={"status": "REVIEWED"},
        )
        assert reviewed.status_code == 200, reviewed.text

        denied_confirm = await client.patch(
            f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
            json={"status": "CONFIRMED"},
        )
        assert denied_confirm.status_code == 403

        denied_dismiss = await client.patch(
            f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
            json={"status": "DISMISSED"},
        )
        assert denied_dismiss.status_code == 403


async def test_admin_can_override_a_closed_finding(
    http_client, _findings_case, user_factory
) -> None:
    case_id, _, _ = _findings_case
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")

    finding_id = await _new_finding_id(http_client, case_id)
    dismissed = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "DISMISSED"},
    )
    assert dismissed.status_code == 200

    async with _client(admin.token) as client:
        reopened = await client.patch(
            f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
            json={"status": "REVIEWED", "reason": "admin found corroborating data"},
        )
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "REVIEWED"


async def _new_finding_id(http_client, case_id: str) -> str:
    prefix = get_settings().API_V1_PREFIX
    listed = await http_client.get(f"{prefix}/cases/{case_id}/findings")
    for finding in listed.json()["items"]:
        if finding["status"] == "NEW":
            return finding["id"]
    raise AssertionError("no NEW finding available for the workflow")

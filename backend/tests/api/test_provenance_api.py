"""API contract tests: evidence detail and provenance (chain of custody)."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case
from sqlalchemy import delete

from tests.api.conftest import ApiUser

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    b"Rajesh Kumar,9876543211,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
).decode()


@pytest.fixture
async def _provenance_case(
    http_client, database: Database, api_user: ApiUser
) -> tuple[uuid.UUID, uuid.UUID, Database]:
    prefix = get_settings().API_V1_PREFIX
    created = await http_client.post(f"{prefix}/cases", json={"title": "provenance case"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    uploaded = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv", "metadata": '{"team": "unit-1"}'},
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

    factory = database.session_factory()
    yield case_id, evidence_id, database
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_evidence_detail_round_trip(http_client, _provenance_case) -> None:
    case_id, evidence_id, _ = _provenance_case
    prefix = get_settings().API_V1_PREFIX

    detail = await http_client.get(f"{prefix}/cases/{case_id}/evidence/{evidence_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == evidence_id
    assert body["original_filename"] == "citizens.csv"
    assert body["sha256"]
    assert body["record_count"] == 2
    assert body["metadata_json"] == {"team": "unit-1"}


async def test_evidence_provenance_counts_after_ingest_and_run(
    http_client, _provenance_case
) -> None:
    case_id, evidence_id, _ = _provenance_case
    prefix = get_settings().API_V1_PREFIX

    response = await http_client.get(f"{prefix}/cases/{case_id}/evidence/{evidence_id}/provenance")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evidence"]["id"] == evidence_id
    assert body["record_count"] == 2
    assert sum(body["records_by_status"].values()) == 2
    assert body["records_by_status"].get("resolved") == 2
    assert body["entity_count"] >= 1
    assert body["relationship_count"] >= 1
    assert body["related_entity_ids"]
    assert body["related_relationship_ids"]
    # The analytics run must have tied this evidence to at least one finding.
    assert body["finding_count"] >= 1
    assert body["finding_ids"]


async def test_evidence_routes_respect_ownership_gates(
    http_client, _provenance_case, user_factory
) -> None:
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    case_id, evidence_id, _ = _provenance_case
    prefix = get_settings().API_V1_PREFIX
    stranger = await user_factory(role="INVESTIGATOR")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {stranger.token}"},
    ) as client:
        assert (
            await client.get(f"{prefix}/cases/{case_id}/evidence/{evidence_id}")
        ).status_code == 403
        assert (
            await client.get(f"{prefix}/cases/{case_id}/evidence/{evidence_id}/provenance")
        ).status_code == 403

    wrong_case = uuid.uuid4()
    response = await http_client.get(
        f"{prefix}/cases/{wrong_case}/evidence/{evidence_id}/provenance"
    )
    assert response.status_code == 404

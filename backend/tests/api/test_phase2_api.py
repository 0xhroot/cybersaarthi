"""API contract tests for the Phase 2 evidence / entity / graph endpoints.

The cases used here are created directly in PostgreSQL and removed afterwards,
so the demo seed data is never touched.
"""

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
async def phase2_case(database: Database, api_user: ApiUser) -> tuple[uuid.UUID, Database]:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"API-{uuid.uuid4().hex[:8]}",
        title="phase-2 api test case",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    yield case_id, database
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_evidence_upload_and_ingest_api(http_client, phase2_case) -> None:
    case_id, database = phase2_case
    prefix = get_settings().API_V1_PREFIX

    response = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv"},
    )
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["sha256"]
    assert evidence["file_size"] == len(CSV_BYTES.encode())
    assert evidence["status"] == "stored"
    evidence_id = evidence["id"]

    response = await http_client.post(
        f"{prefix}/cases/{case_id}/ingest",
        json={"evidence_file_id": evidence_id, "metadata": {"source": "test"}},
    )
    assert response.status_code == 200, response.text
    job = response.json()["job"]
    assert job["status"] == "completed"
    assert job["graph_sync_status"] == "synced"

    response = await http_client.get(f"{prefix}/cases/{case_id}/ingest-jobs")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_entity_graph_and_review_endpoints(http_client, phase2_case) -> None:
    case_id, _ = phase2_case
    prefix = get_settings().API_V1_PREFIX

    response = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv"},
    )
    assert response.status_code == 201, response.text
    evidence_id = response.json()["id"]

    response = await http_client.post(
        f"{prefix}/cases/{case_id}/ingest",
        json={"evidence_file_id": evidence_id, "metadata": {"source": "test"}},
    )
    assert response.status_code == 200, response.text
    job = response.json()["job"]
    assert job["status"] == "completed"

    response = await http_client.get(f"{prefix}/cases/{case_id}/entities")
    assert response.status_code == 200, response.text
    entities = response.json()
    assert entities["total"] == 6
    person = next(item for item in entities["items"] if item["canonical_value"] == "rajesh kumar")

    response = await http_client.get(f"{prefix}/cases/{case_id}/entities/{person['id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["entity_type"] == "person"
    assert [alias["alias_value"] for alias in detail["aliases"]] == ["rajesh kumar"]

    response = await http_client.get(f"{prefix}/cases/{case_id}/relationships")
    assert response.status_code == 200
    assert response.json()["total"] == 9

    response = await http_client.get(f"{prefix}/cases/{case_id}/graph")
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["case_id"] == str(case_id)
    assert len(graph["nodes"]) == 6
    assert len(graph["edges"]) == 9
    rajesh_node = next(node for node in graph["nodes"] if node["canonical_value"] == "rajesh kumar")
    assert "rajesh kumar" in rajesh_node["aliases"]

    response = await http_client.get(f"{prefix}/cases/{case_id}/graph/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["node_count"] == 6
    assert stats["edge_count"] == 9
    assert stats["synced"] is True

    graph_node_id = graph["nodes"][0]["id"]
    response = await http_client.get(f"{prefix}/cases/{case_id}/graph/entity/{graph_node_id}")
    assert response.status_code == 200
    assert response.json()["centre"] == graph_node_id

    response = await http_client.get(f"{prefix}/cases/{case_id}/resolution/review")
    assert response.status_code == 200
    assert response.json()["total"] == 0

    missing = "00000000-0000-0000-0000-000000000000"
    response = await http_client.get(f"{prefix}/cases/{missing}/entities")
    assert response.status_code == 404


async def _upload_one(http_client, case_id: uuid.UUID) -> dict:
    prefix = get_settings().API_V1_PREFIX
    response = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
        data={"data_source": "police_csv"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _evidence_objects(app, case_id: uuid.UUID) -> list[str]:
    return app.state.storage.list_keys(f"cases/{case_id}/evidence/")


async def test_evidence_delete_removes_row_and_object(
    http_client, phase2_case, monkeypatch
) -> None:
    """DELETE /cases/:id/evidence/:id purges the DB row and the object (A03)."""
    from app.main import app

    case_id, _ = phase2_case
    prefix = get_settings().API_V1_PREFIX
    evidence = await _upload_one(http_client, case_id)
    evidence_id = evidence["id"]
    assert len(_evidence_objects(app, case_id)) == 1

    # parenthesise: request.app.state is the same object as the imported app
    response = await http_client.delete(f"{prefix}/cases/{case_id}/evidence/{evidence_id}")
    assert response.status_code == 204, response.text

    response = await http_client.get(f"{prefix}/cases/{case_id}/evidence")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert _evidence_objects(app, case_id) == []

    # deleting an unknown evidence row is a 404, not a 500
    response = await http_client.delete(f"{prefix}/cases/{case_id}/evidence/{evidence_id}")
    assert response.status_code == 404


async def test_evidence_delete_scoped_to_case(http_client, phase2_case, user_factory) -> None:
    """An evidence row from another case cannot be deleted via this case (A03)."""
    from app.main import app

    case_id, database = phase2_case
    prefix = get_settings().API_V1_PREFIX
    other_owner = await user_factory()
    other_case = Case(
        id=uuid.uuid4(),
        case_number=f"API-{uuid.uuid4().hex[:8]}",
        title="other case",
        owner_id=other_owner.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other_case)
        await session.commit()
    try:
        import httpx

        other_headers = {"Authorization": f"Bearer {other_owner.token}"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers=other_headers,
        ) as other_client:
            evidence = await _upload_one(other_client, other_case.id)
            evidence_id = evidence["id"]

            response = await http_client.delete(f"{prefix}/cases/{case_id}/evidence/{evidence_id}")
            assert response.status_code == 404, response.text
            # the row and object survive (listed via the owner's client)
            response = await other_client.get(f"{prefix}/cases/{other_case.id}/evidence")
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 1
            assert len(_evidence_objects(app, other_case.id)) == 1
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == other_case.id))
            await session.commit()


async def test_evidence_delete_requires_permission(http_client, phase2_case, user_factory) -> None:
    """viewer has no evidence.delete, so the request is rejected (A03)."""
    import httpx
    from app.main import app

    case_id, _ = phase2_case
    prefix = get_settings().API_V1_PREFIX
    evidence = await _upload_one(http_client, case_id)
    viewer = await user_factory(role="VIEWER")
    viewer_headers = {"Authorization": f"Bearer {viewer.token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=viewer_headers
    ) as client:
        response = await client.delete(f"{prefix}/cases/{case_id}/evidence/{evidence['id']}")
    assert response.status_code == 403, response.text


async def test_evidence_upload_failure_cleans_up_object(
    http_client, phase2_case, monkeypatch
) -> None:
    """A03 compensating delete: an object uploaded before a failed insert is
    removed, so the bucket holds no orphan for the failed upload."""
    from app.main import app
    from app.repositories.evidence_repository import EvidenceRepository

    case_id, _ = phase2_case
    prefix = get_settings().API_V1_PREFIX

    async def _boom(self, **kwargs):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(EvidenceRepository, "create_evidence_file", _boom)
    with pytest.raises(RuntimeError):
        await http_client.post(
            f"{prefix}/cases/{case_id}/evidence",
            files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
            data={"data_source": "police_csv"},
        )
    assert _evidence_objects(app, case_id) == []

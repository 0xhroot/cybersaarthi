"""API contract tests for the Phase 3 analytics and findings endpoints.

Each test uses its own ephemeral case created directly in PostgreSQL and
removed afterwards, so the demo seed data is never touched.  A small shared-
identifier CSV is ingested so structural patterns, hypotheses, communities and
paths all have real material to work with.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case
from sqlalchemy import delete

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Arjun Mehta,7000000001,TechSecure Pvt Ltd,MH12AB1111,Mumbai\n"
    b"Vikram Jamwal,7000000001,TechSecure Pvt Ltd,MH12AB2222,Noida\n"
    b"Priya Nair,7000000001,Zenith Technologies,DL09CD3333,Noida\n"
    b"Sameer Bhat,7000000002,Zenith Technologies,DL09CD3333,Delhi\n"
).decode()


@pytest.fixture
async def phase3_case(database: Database) -> tuple[uuid.UUID, Database]:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"ANL-{uuid.uuid4().hex[:8]}",
        title="phase-3 analytics api test case",
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


async def _ingested_case(http_client, case_id: uuid.UUID) -> None:
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
    assert response.json()["job"]["status"] == "completed"


async def test_analytics_summary_and_run_lifecycle(http_client, phase3_case) -> None:
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/summary")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["case_id"] == str(case_id)
    assert summary["entity_count"] >= 8
    assert summary["relationship_count"] >= 6
    assert summary["community_count"] >= 0
    assert "profile_tiers" in summary and "priority_tiers" in summary
    assert "findings_by_type" in summary and "findings_by_severity" in summary

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["stage"] == "done"
    run_id = run["id"]

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/runs")
    assert response.status_code == 200, response.text
    runs = response.json()
    assert runs["total"] >= 1
    assert any(item["id"] == run_id for item in runs["items"])


async def test_findings_endpoints_and_status_lifecycle(http_client, phase3_case) -> None:
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text

    response = await http_client.get(f"{prefix}/cases/{case_id}/findings")
    assert response.status_code == 200, response.text
    listing = response.json()
    assert listing["total"] >= 1
    finding = next(item for item in listing["items"] if item["finding_type"] == "pattern")
    assert isinstance(finding["evidence_ids"], list)
    assert "approach" in finding["explanation"] or "signals" in finding["explanation"]
    finding_id = finding["id"]

    response = await http_client.get(f"{prefix}/cases/{case_id}/findings/{finding_id}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == finding_id
    assert response.json()["status"] == "NEW"
    assert response.json()["case_id"] == str(case_id)

    response = await http_client.get(f"{prefix}/cases/{case_id}/findings?status=NEW&limit=2")
    assert response.status_code == 200
    assert len(response.json()["items"]) <= 2

    response = await http_client.get(f"{prefix}/cases/{case_id}/findings/stats")
    assert response.status_code == 200, response.text
    stats = response.json()
    assert stats["by_status"].get("NEW", 0) >= 1

    response = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "REVIEWED"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REVIEWED"
    assert response.json()["id"] == finding_id

    response = await http_client.patch(
        f"{prefix}/cases/{case_id}/findings/{finding_id}/status",
        json={"status": "TOO_MUCH"},
    )
    assert response.status_code == 422


async def test_analytics_read_endpoints(http_client, phase3_case) -> None:
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/centrality?metric=pagerank&limit=3"
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) >= 1

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/communities")
    assert response.status_code == 200, response.text
    communities = response.json()
    assert len(communities) >= 1
    assert all(c["member_count"] >= 1 for c in communities)
    assert "dominant_entity_types" in communities[0]

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/priorities?limit=5")
    assert response.status_code == 200, response.text
    assert response.json()[0]["tier"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/network-dna?limit=3")
    assert response.status_code == 200, response.text
    assert response.json()[0]["tier"] in {"FOCAL", "SIGNIFICANT", "MONITORED", "PERIPHERAL"}

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/strength?limit=3")
    assert response.status_code == 200, response.text
    assert 0.0 <= response.json()[0]["strength"] <= 1.0

    entities = (await http_client.get(f"{prefix}/cases/{case_id}/entities")).json()["items"]
    persons = [e for e in entities if e["entity_type"] == "person"]
    assert len(persons) >= 2
    source, target = persons[0]["id"], persons[1]["id"]

    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths?source_id={source}&target_id={target}&max_hops=3"
    )
    assert response.status_code == 200, response.text
    pair = response.json()
    assert "paths" in pair and "paths_count" in pair
    assert all(p["hops"] >= 2 for p in pair["paths"])

    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths/entity/{source}?max_hops=2&limit=10"
    )
    assert response.status_code == 200, response.text
    ego = response.json()
    assert ego["paths_count"] >= 0
    assert all(p["hops"] <= 2 for p in ego["paths"])

    entity_id = persons[0]["id"]
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/entities/{entity_id}/analytics"
    )
    assert response.status_code == 200, response.text
    entity_analysis = response.json()
    assert "priority_tier" in entity_analysis
    assert "centrality" in entity_analysis


async def test_analytics_not_found_and_isolation(http_client, phase3_case) -> None:
    case_id, database = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    missing = uuid.uuid4()
    response = await http_client.get(f"{prefix}/cases/{missing}/analytics/summary")
    assert response.status_code == 404
    response = await http_client.post(f"{prefix}/cases/{missing}/analytics/run")
    assert response.status_code == 404
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/entities/{missing}/analytics"
    )
    assert response.status_code == 404
    response = await http_client.get(f"{prefix}/cases/{case_id}/findings/{missing}")
    assert response.status_code == 404

    other = Case(
        id=uuid.uuid4(),
        case_number=f"ANL-{uuid.uuid4().hex[:8]}",
        title="phase-3 isolated empty case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other)
        await session.commit()
    other_id = other.id
    try:
        response = await http_client.get(f"{prefix}/cases/{other_id}/findings")
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == other_id))
            await session.commit()

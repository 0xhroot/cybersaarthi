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
from app.main import app
from app.models import RELATIONSHIP_TYPES, Case, Entity, Relationship
from sqlalchemy import delete

from tests.api.conftest import ApiUser

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Arjun Mehta,7000000001,TechSecure Pvt Ltd,MH12AB1111,Mumbai\n"
    b"Vikram Jamwal,7000000001,TechSecure Pvt Ltd,MH12AB2222,Noida\n"
    b"Priya Nair,7000000001,Zenith Technologies,DL09CD3333,Noida\n"
    b"Sameer Bhat,7000000002,Zenith Technologies,DL09CD3333,Delhi\n"
).decode()


@pytest.fixture
async def phase3_case(database: Database, api_user: ApiUser) -> tuple[uuid.UUID, Database]:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"ANL-{uuid.uuid4().hex[:8]}",
        title="phase-3 analytics api test case",
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


async def test_findings_snapshot_semantics_across_runs(http_client, phase3_case) -> None:
    """Each analytics run persists its own finding snapshot under its run_id.

    Findings accumulate intentionally (audit history); a run_id filter isolates
    exactly one run's snapshot so current and historical findings remain
    distinguishable.
    """
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text
    first_run_id = response.json()["id"]
    first_total = (await http_client.get(f"{prefix}/cases/{case_id}/findings")).json()["total"]
    assert first_total >= 1

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text
    second_run_id = response.json()["id"]

    all_findings = await http_client.get(f"{prefix}/cases/{case_id}/findings")
    assert all_findings.status_code == 200, all_findings.text
    history = all_findings.json()
    assert history["total"] >= first_total
    assert {item["run_id"] for item in history["items"]} <= {first_run_id, second_run_id}

    scoped = await http_client.get(f"{prefix}/cases/{case_id}/findings?run_id={first_run_id}")
    assert scoped.status_code == 200, scoped.text
    first_snapshot = scoped.json()
    assert first_snapshot["total"] >= 1
    assert all(item["run_id"] == first_run_id for item in first_snapshot["items"])

    scoped_stats = await http_client.get(
        f"{prefix}/cases/{case_id}/findings/stats?run_id={first_run_id}"
    )
    assert scoped_stats.status_code == 200, scoped_stats.text
    assert scoped_stats.json()["by_status"].get("NEW", 0) == first_snapshot["total"]


async def test_hypotheses_are_candidates_not_facts(http_client, phase3_case) -> None:
    """A missing-link hypothesis must never create a graph relationship.

    The engine reports the candidate edge (with signals, supported relationships
    and evidence) but the persisted relationship set is unchanged by an
    analytics run.
    """
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    before = await http_client.get(f"{prefix}/cases/{case_id}/analytics/summary")
    assert before.status_code == 200, before.text
    relationship_count_before = before.json()["relationship_count"]

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text

    after = await http_client.get(f"{prefix}/cases/{case_id}/analytics/summary")
    assert after.status_code == 200, after.text
    assert after.json()["relationship_count"] == relationship_count_before

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/hypotheses?limit=25")
    assert response.status_code == 200, response.text
    hypotheses = response.json()

    findings = (await http_client.get(f"{prefix}/cases/{case_id}/findings")).json()["items"]
    hypothesis_findings = [
        finding for finding in findings if finding["finding_type"] == "hypothesis"
    ]
    assert hypothesis_findings, "expected at least one hypothesis finding"

    for hypothesis in hypotheses:
        assert hypothesis["candidate_relation_type"] in {*RELATIONSHIP_TYPES, None}
        assert hypothesis["affected_entities"]
        assert hypothesis["signals"], "hypothesis must explain its signals"
        assert "shared_neighbors" in {signal["name"] for signal in hypothesis["signals"]}

    sample = hypothesis_findings[0]
    limitation = "".join(sample["explanation"].get("limitations") or [])
    assert "never creates a graph edge" in limitation
    assert all(key in sample["explanation"] for key in ("approach", "signals", "evidence"))


async def test_paths_validation_and_openapi_contract(
    http_client, phase3_case, api_user: ApiUser
) -> None:
    case_id, database = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    entities = (await http_client.get(f"{prefix}/cases/{case_id}/entities")).json()["items"]
    persons = [e for e in entities if e["entity_type"] == "person"]
    assert len(persons) >= 2
    source, target = persons[0]["id"], persons[1]["id"]

    # Required query parameters: omitted source_id/target_id -> 422.
    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/paths")
    assert response.status_code == 422

    # Same source and target are rejected with a clear 422.
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths?source_id={source}&target_id={source}"
    )
    assert response.status_code == 422

    # Hop bounds are enforced against MAX_HOPS_LIMIT.
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths?source_id={source}&target_id={target}&max_hops=9"
    )
    assert response.status_code == 422
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths?source_id={source}&target_id={target}&max_hops=1"
    )
    assert response.status_code == 422
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths/entity/{source}?max_hops=9"
    )
    assert response.status_code == 422

    # Nonexistent / foreign entities yield an empty path set, never an error.
    missing = str(uuid.uuid4())
    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/paths?source_id={missing}&target_id={target}"
    )
    assert response.status_code == 200, response.text
    assert response.json()["paths_count"] == 0
    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/paths/entity/{missing}")
    assert response.status_code == 200, response.text
    assert response.json()["paths_count"] == 0

    # OpenAPI marks source_id/target_id as required parameters.
    spec = app.openapi()
    path_spec = spec["paths"][f"{prefix}/cases/{{case_id}}/analytics/paths"]["get"]
    required = {param["name"] for param in path_spec["parameters"] if param.get("required")}
    assert {"source_id", "target_id"} <= required

    # Case isolation: a case with no data returns empty findings and paths.
    other = Case(
        id=uuid.uuid4(),
        case_number=f"ANL-{uuid.uuid4().hex[:8]}",
        title="phase-3 path isolation case",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other)
        await session.commit()
    other_id = other.id
    try:
        response = await http_client.get(
            f"{prefix}/cases/{other_id}/analytics/paths/entity/{source}"
        )
        assert response.status_code == 200, response.text
        assert response.json()["paths_count"] == 0
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == other_id))
            await session.commit()


async def test_analytics_handles_graph_beyond_recursion_depth(http_client, phase3_case) -> None:
    """Regression for A01: analytics over a >1000-node graph must not crash.

    Articulation detection is a depth-first Tarjan pass that used to recurse
    once per node, overflowing the interpreter stack on deep graphs (a long
    relationship chain) and surfacing as a 500 from the analytics endpoints.
    DFS is now explicit-stack, so a 1200-node chain resolves cleanly.
    """
    case_id, database = phase3_case
    prefix = get_settings().API_V1_PREFIX

    size = 1200
    factory = database.session_factory()
    async with factory() as session:
        entities = [
            Entity(
                case_id=str(case_id),
                entity_type="person",
                canonical_value=f"chain-person-{i:04d}",
                blocking_key=f"bk-{case_id}-chain-{i:04d}",
                display_value=f"Chain Person {i:04d}",
                status="active",
            )
            for i in range(size)
        ]
        session.add_all(entities)
        await session.flush()
        ids = [entity.id for entity in entities]
        relationships = [
            Relationship(
                case_id=str(case_id),
                source_entity_id=ids[i],
                target_entity_id=ids[i + 1],
                relationship_type="called",
            )
            for i in range(size - 1)
        ]
        session.add_all(relationships)
        await session.commit()

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/summary")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["entity_count"] == size
    assert summary["relationship_count"] == size - 1
    assert summary["exact_graph"] is True

    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/centrality?metric=betweenness&limit=5"
    )
    assert response.status_code == 200, response.text
    assert all(entry["exact"] is True for entry in response.json())


async def test_analytics_summary_exact_flag_defaults(http_client, phase3_case) -> None:
    """Small cases run exact analytics; the summary surfaces no approximation
    notice and the centrality payloads report exact=True."""
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.get(f"{prefix}/cases/{case_id}/analytics/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["exact_graph"] is True
    assert payload["approximation_notice"] is None

    response = await http_client.get(
        f"{prefix}/cases/{case_id}/analytics/centrality?metric=degree&limit=5"
    )
    assert response.status_code == 200, response.text
    assert all(entry["exact"] is True for entry in response.json())


async def test_analytics_not_found_and_isolation(
    http_client, phase3_case, api_user: ApiUser
) -> None:
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
        owner_id=api_user.id,
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


async def test_findings_do_not_duplicate_across_unchanged_runs(http_client, phase3_case) -> None:
    """A09: re-running analytics over unchanged data must not inflate the
    findings table. Unchanged signals are collapsed, so the total stays flat."""
    case_id, _ = phase3_case
    prefix = get_settings().API_V1_PREFIX
    await _ingested_case(http_client, case_id)

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text
    first_total = (await http_client.get(f"{prefix}/cases/{case_id}/findings")).json()["total"]
    assert first_total >= 1

    response = await http_client.post(f"{prefix}/cases/{case_id}/analytics/run")
    assert response.status_code == 201, response.text

    after = (await http_client.get(f"{prefix}/cases/{case_id}/findings")).json()
    # Deterministic engine: an unchanged case yields the same findings, so the
    # second run must not add a second copy of every finding.
    assert after["total"] == first_total

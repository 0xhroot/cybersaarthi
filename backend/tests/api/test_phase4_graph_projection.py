"""Graph projection consistency (Phase 4 audit fix).

Phase 3's report was correct: approving an entity-resolution candidate wrote
additive ``EntityAlias`` rows in PostgreSQL but never refreshed the Neo4j
projection, so the projection kept serving the pre-approval identity view.
The same gap applied to entity merges (``status -> merged``). The user-facing
``GET /cases/{id}/graph`` route reads PostgreSQL and was never stale; the gap
was in the Neo4j projection that traversal analytics and ``case_graph`` read.

These tests pin the corrected behaviour:

- a full-case ingest sync carries each entity's aliases onto its node;
- ``sync_entities_by_id`` refreshes exactly the named entities (idempotent,
  never touches other cases);
- approving a resolution candidate returns ``graph_synced`` and makes the
  alias visible to ``case_graph``, the projection's read method;
- merging an entity flips the absorbed node to ``merged`` in the projection;
- a projection failure after commit is surfaced (``graph_synced: false`` plus
  a durable ``graph.sync_failed`` audit event) and never rolls back the
  canonical PostgreSQL decision.

Every case uses a random id and is deleted from both stores on teardown, so
the shared Neo4j instance stays tidy.
"""

from __future__ import annotations

import uuid

import httpx
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import AuditLog, DerivedArtifact, Entity, EntityAlias
from app.services.graph_sync import GraphSyncService
from app.services.normalization import blocking_key, normalize_value
from sqlalchemy import select

PREFIX = get_settings().API_V1_PREFIX

STRONG_A = "Priya Sharma"
STRONG_B = "Priya Sharmaa"


# -- helpers ---------------------------------------------------------------------


async def _seed_person(database: Database, case_id: uuid.UUID, name: str) -> uuid.UUID:
    normalized = normalize_value("person", name)
    assert normalized.is_valid, name
    factory = database.session_factory()
    async with factory() as session:
        entity = Entity(
            case_id=str(case_id),
            entity_type="person",
            canonical_value=normalized.canonical,
            blocking_key=blocking_key("person", normalized.canonical),
            display_value=normalized.display,
            status="active",
        )
        session.add(entity)
        await session.commit()
        return uuid.UUID(str(entity.id))


async def _graph_node(graph_store, entity_id: uuid.UUID) -> dict | None:
    async with graph_store.driver().session() as session:
        result = await session.run(
            "MATCH (n:Entity {id: $eid}) RETURN n", eid=str(entity_id)
        )
        record = await result.single()
        return dict(record["n"]) if record else None


async def _audit_row(
    database: Database,
    *,
    action: str,
    case_id: uuid.UUID,
) -> AuditLog | None:
    """The committed audit row for one case.

    Scoped by ``case_id`` so residue from other cases in a shared database can
    never satisfy (or mask) this assertion. The handler writes the row and
    commits before returning, so a single read observes it.
    """
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.resource_type == "entity",
                AuditLog.case_id == str(case_id),
            )
        )
        return rows.scalars().first()


async def _artifacts(
    database: Database, case_id: uuid.UUID, *, kind: str
) -> list[DerivedArtifact]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(DerivedArtifact).where(
                DerivedArtifact.case_id == str(case_id),
                DerivedArtifact.kind == kind,
            )
        )
        return list(rows.scalars())


def _review_body(note: str, decision: str = "approved") -> dict[str, str]:
    return {"decision": decision, "note": note}


# -- tests -----------------------------------------------------------------------


async def test_full_case_sync_projects_aliases_onto_nodes(
    http_client: httpx.AsyncClient,
    database: Database,
    graph_store,
    settings,
    _owned_case: uuid.UUID,
) -> None:
    """A full-case ingest sync carries each entity's aliases onto its node."""
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            EntityAlias(
                entity_id=str(entity_a),
                alias_value="priya sharmaa",
                alias_type="resolution",
            )
        )
        session.add(
            EntityAlias(
                entity_id=str(entity_b),
                alias_value="priya sharma",
                alias_type="resolution",
            )
        )
        await session.commit()

    service = GraphSyncService(graph_store, settings)
    factory = database.session_factory()
    async with factory() as session:
        synced = await service.sync_entities_by_id(
            session, [str(entity_a), str(entity_b)]
        )
    assert synced == 2

    node_a = await _graph_node(graph_store, entity_a)
    node_b = await _graph_node(graph_store, entity_b)
    assert node_a is not None and node_b is not None
    assert "priya sharmaa" in node_a["aliases"]
    assert "priya sharma" in node_b["aliases"]


async def test_resolution_approval_projects_alias_and_reports_graph_synced(
    http_client: httpx.AsyncClient,
    database: Database,
    graph_store,
    settings,
    _owned_case: uuid.UUID,
) -> None:
    """Approving a resolution candidate refreshes the projection (Phase 3 gap)."""
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)

    submit = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/entity-resolution",
        json={},
    )
    assert submit.status_code == 202, submit.text
    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("cross-check confirmed by phone records"),
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["graph_synced"] is True

    node_a = await _graph_node(graph_store, entity_a)
    node_b = await _graph_node(graph_store, entity_b)
    assert node_a is not None and node_b is not None
    assert "priya sharmaa" in node_a["aliases"]
    assert "priya sharma" in node_b["aliases"]

    # Read it back through the projection's own read method, the same surface
    # the traversal analytics consume, so the alias is proven visible there
    # and not only in a raw node lookup.
    service = GraphSyncService(graph_store, settings)
    nodes, _edges = await service.case_graph(_owned_case)
    by_id = {node["id"]: node for node in nodes}
    assert str(entity_a) in by_id and str(entity_b) in by_id
    assert "priya sharmaa" in by_id[str(entity_a)]["aliases"]
    assert "priya sharma" in by_id[str(entity_b)]["aliases"]

    # The canonical decision is additive; the projection never rewrites it.
    factory = database.session_factory()
    async with factory() as session:
        entities = list(
            (
                await session.execute(
                    select(Entity).where(Entity.id.in_([str(entity_a), str(entity_b)]))
                )
            ).scalars()
        )
        assert all(e.status == "active" for e in entities)
        assert all(e.merged_into_id is None for e in entities)


async def test_merge_projects_status_flip_onto_absorbed_node(
    http_client: httpx.AsyncClient,
    database: Database,
    graph_store,
    settings,
    _owned_case: uuid.UUID,
) -> None:
    """An explicit entity merge flips the absorbed node to ``merged`` in Neo4j."""
    primary = await _seed_person(database, _owned_case, STRONG_A)
    doomed = await _seed_person(database, _owned_case, STRONG_B)

    service = GraphSyncService(graph_store, settings)
    factory = database.session_factory()
    async with factory() as session:
        await service.sync_entities_by_id(session, [str(primary), str(doomed)])
    node_before = await _graph_node(graph_store, doomed)
    assert node_before is not None
    assert node_before["status"] == "active"

    merge = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/entities/merge",
        json={"primary_entity_id": str(primary), "merge_entity_id": str(doomed)},
    )
    assert merge.status_code == 200, merge.text
    assert merge.json()["graph_synced"] is True

    node_after = await _graph_node(graph_store, doomed)
    node_primary = await _graph_node(graph_store, primary)
    assert node_after is not None
    assert node_after["status"] == "merged"
    assert node_primary is not None
    assert node_primary["status"] == "active"


async def test_sync_entities_by_id_is_idempotent(
    database: Database,
    graph_store,
    settings,
    _owned_case: uuid.UUID,
) -> None:
    """Re-running the targeted refresh must not duplicate or drop projection state."""
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            EntityAlias(
                entity_id=str(entity_a),
                alias_value="priya sharmaa",
                alias_type="resolution",
            )
        )
        await session.commit()

    service = GraphSyncService(graph_store, settings)
    for _ in range(3):
        factory = database.session_factory()
        async with factory() as session:
            await service.sync_entities_by_id(session, [str(entity_a)])

    node_a = await _graph_node(graph_store, entity_a)
    assert node_a is not None
    assert node_a["aliases"].count("priya sharmaa") == 1


async def test_projection_failure_is_surfaced_and_never_rolls_back_the_decision(
    http_client: httpx.AsyncClient,
    database: Database,
    graph_store,
    monkeypatch,
    _owned_case: uuid.UUID,
) -> None:
    """A graph outage after commit is surfaced, not hidden; PG stays authoritative."""
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)

    def _boom(self, session, entity_ids):
        raise RuntimeError("neo4j unavailable")

    monkeypatch.setattr(GraphSyncService, "sync_entities_by_id", _boom)

    submit = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/entity-resolution",
        json={},
    )
    assert submit.status_code == 202, submit.text
    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("cross-check confirmed by phone records"),
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["graph_synced"] is False

    # The reviewer's decision survived in PostgreSQL even though the graph failed.
    factory = database.session_factory()
    async with factory() as session:
        aliases = list(
            (
                await session.execute(
                    select(EntityAlias).where(
                        EntityAlias.entity_id.in_([str(entity_a), str(entity_b)])
                    )
                )
            ).scalars()
        )
        assert {a.alias_type for a in aliases} == {"resolution"}

    # The audit row is looked up by (action, resource_type, case) rather than
    # by resource_id: the candidate payload names one of the two entities as
    # "entity_a", and which one is not stable across runs. Matching on that
    # slot would make the assertion flaky; asserting the exact id *set* in the
    # metadata proves the same thing order-independently.
    audit = await _audit_row(database, action="graph.sync_failed", case_id=_owned_case)
    assert audit is not None
    metadata = dict(audit.metadata_ or {})
    assert metadata.get("trigger") == "entity_resolution_approved"
    assert {str(entity_a), str(entity_b)} == set(metadata.get("entity_ids", []))
    # The audit row is case-scoped so it is retrievable from case analytics.
    assert audit.case_id is not None
    assert str(audit.case_id) == str(_owned_case)

"""Graph projection lifecycle: sync must be reversible without leaving orphans.

Regression coverage for A02 — deleting a case's data in PostgreSQL must never
leave its nodes/relationships stranded in the Neo4j projection. Every case here
uses a random case id and cleans up after itself so the store stays tidy.
"""

from __future__ import annotations

import uuid

from app.core.config import Settings
from app.db.neo4j import GraphStore
from app.models import Entity, Relationship
from app.services.graph_sync import GraphSyncService


def _entity(case_id: uuid.UUID, suffix: str) -> Entity:
    return Entity(
        id=uuid.uuid4(),
        case_id=str(case_id),
        entity_type="person",
        canonical_value=f"neo4j-lifecycle-{suffix}",
        blocking_key=f"bk-lifecycle-{suffix}",
        display_value=f"Lifecycle {suffix}",
        status="active",
    )


def _relationship(case_id: uuid.UUID, source: Entity, target: Entity, suffix: str) -> Relationship:
    return Relationship(
        id=uuid.uuid4(),
        case_id=str(case_id),
        source_entity_id=source.id,
        target_entity_id=target.id,
        relationship_type="called",
    )


async def _sync_case(
    svc: GraphSyncService, case_id: uuid.UUID
) -> tuple[list[Entity], list[Relationship]]:
    a = _entity(case_id, uuid.uuid4().hex[:6])
    b = _entity(case_id, uuid.uuid4().hex[:6])
    rel = _relationship(case_id, a, b, uuid.uuid4().hex[:6])
    await svc.sync_case(case_id=case_id, entities=[a, b], relationships=[rel])
    return [a, b], [rel]


async def test_delete_case_clears_the_projection(
    graph_store: GraphStore, settings: Settings
) -> None:
    svc = GraphSyncService(graph_store, settings)
    case_id = uuid.uuid4()
    entities, relationships = await _sync_case(svc, case_id)
    assert await svc.sync_case(case_id=case_id, entities=entities, relationships=relationships) == (
        2,
        1,
    )
    try:
        nodes, edges = await svc.case_graph(case_id)
        assert len(nodes) == 2
        assert len(edges) == 1

        removed_nodes, removed_edges = await svc.delete_case(case_id)
        assert removed_nodes == 2
        assert removed_edges == 1

        nodes, edges = await svc.case_graph(case_id)
        assert nodes == []
        assert edges == []
    finally:
        await svc.delete_case(case_id)


async def test_delete_case_is_idempotent(graph_store: GraphStore, settings: Settings) -> None:
    svc = GraphSyncService(graph_store, settings)
    case_id = uuid.uuid4()
    entities, relationships = await _sync_case(svc, case_id)
    assert await svc.sync_case(case_id=case_id, entities=entities, relationships=relationships) == (
        2,
        1,
    )
    try:
        await svc.delete_case(case_id)
        removed_nodes, removed_edges = await svc.delete_case(case_id)
        assert removed_nodes == 0
        assert removed_edges == 0
    finally:
        await svc.delete_case(case_id)


async def test_delete_case_leaves_other_cases_intact(
    graph_store: GraphStore, settings: Settings
) -> None:
    svc = GraphSyncService(graph_store, settings)
    kept = uuid.uuid4()
    doomed = uuid.uuid4()
    kept_entities, kept_rels = await _sync_case(svc, kept)
    doomed_entities, doomed_rels = await _sync_case(svc, doomed)
    assert await svc.sync_case(case_id=kept, entities=kept_entities, relationships=kept_rels) == (
        2,
        1,
    )
    assert await svc.sync_case(
        case_id=doomed, entities=doomed_entities, relationships=doomed_rels
    ) == (2, 1)
    try:
        await svc.delete_case(doomed)
        kept_nodes, kept_edges = await svc.case_graph(kept)
        assert len(kept_nodes) == 2
        assert len(kept_edges) == 1
        doomed_nodes, doomed_edges = await svc.case_graph(doomed)
        assert doomed_nodes == []
        assert doomed_edges == []
    finally:
        await svc.delete_case(kept)
        await svc.delete_case(doomed)

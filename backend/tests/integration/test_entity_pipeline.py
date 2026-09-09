"""End-to-end ingestion pipeline tests against real PostgreSQL, Neo4j and MinIO.

Each test creates a fresh, uniquely named case and cleans up every row, object
and graph node afterwards, so repeated runs stay deterministic even when
PostgreSQL and Neo4j already contain seed data.
"""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import Case
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.services.entity_service import EntityQueryService
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService
from app.services.validation import detect_format, fingerprint
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    b"Rajesh Kumar,9876543211,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
)

TXT_BYTES = (
    b"Arjun Mehra coordinated the operation for months, travelled to Pune and "
    b"was seen in the vehicle MH12AB1234 driving near the warehouse.\n"
)

# A single structured record whose relationships the TXT free-text below
# re-discovers through the co-occurrence mechanism (same canonical entities).
CSV_SINGLE_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure,MH12AB1234,Mumbai\n"
)

# Free text co-occurrence: repeats the CSV's person/phone/org/location facts in
# one sentence window (person via NER, phone via the rule extractor). It must
# NOT introduce any relationship the structured record did not already create.
TXT_REPEAT_BYTES = (
    b"Rajesh Kumar used phone 9876543210 while working with TechSecure near Mumbai on Monday.\n"
)


def _ingestion(
    session: AsyncSession, storage: Storage, graph_store: GraphStore
) -> IngestionService:
    settings = get_settings()
    return IngestionService(
        session=session,
        evidence_repository=EvidenceRepository(session),
        entity_repository=EntityRepository(session),
        relationship_repository=RelationshipRepository(session),
        storage=storage,
        graph_sync=GraphSyncService(graph_store, settings),
        settings=settings,
    )


async def _new_case(database: Database) -> uuid.UUID:
    case_id = uuid.uuid4()
    case = Case(
        id=case_id,
        case_number=f"INT-{uuid.uuid4().hex[:8]}",
        title="phase-2 integration test case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
    return case_id


async def _cleanup(
    database: Database,
    storage: Storage,
    graph_store: GraphStore,
    case_id: uuid.UUID,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        evidence_repo = EvidenceRepository(session)
        evidence_items, _ = await evidence_repo.list_evidence(case_id)
        for evidence in evidence_items:
            storage.delete(evidence.stored_key)
    async with graph_store.driver().session() as session:
        await session.run("MATCH (n:Entity {case_id: $id}) DETACH DELETE n", {"id": str(case_id)})
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_csv_ingestion_resolves_and_syncs(
    database: Database, graph_store: GraphStore, storage: Storage
) -> None:
    settings = get_settings()
    case_id = await _new_case(database)
    try:
        object_key = f"cases/{case_id}/evidence/int.csv"
        storage.upload(object_key, CSV_BYTES, "text/csv")
        fmt = detect_format("int.csv", CSV_BYTES)

        factory = database.session_factory()
        async with factory() as session:
            evidence_repo = EvidenceRepository(session)
            source = await evidence_repo.get_or_create_data_source("integration-test")
            evidence = await evidence_repo.create_evidence_file(
                case_id=case_id,
                data_source_id=source.id,
                original_filename="int.csv",
                stored_key=object_key,
                content_type="text/csv",
                file_size=len(CSV_BYTES),
                sha256=fingerprint(CSV_BYTES),
                metadata_json={"format": fmt.value},
            )
            await session.commit()
            evidence_id = evidence.id

        async with factory() as session:
            job = await _ingestion(session, storage, graph_store).ingest(
                case_id=case_id, evidence_file_id=evidence_id
            )
            assert job.status == "completed"
            assert job.graph_sync_status == "synced"
            assert job.summary is not None
            assert job.summary["records"] == 2

            entity_counts = await EntityRepository(session).count_entities_by_type(case_id)
            assert entity_counts == {
                "person": 1,
                "phone": 2,
                "organization": 1,
                "vehicle": 1,
                "location": 1,
            }

            relationship_types = await RelationshipRepository(session).count_by_type(case_id)
            assert relationship_types == {
                "called": 2,
                "owns": 1,
                "works_for": 1,
                "located_at": 2,
                "visited": 3,
            }
            assert await RelationshipRepository(session).count_relationships(case_id) == 9

            # The duplicate-name record auto-matched rather than duplicating.
            matches = await EntityRepository(session).list_matches(case_id, decision="auto_match")
            assert len(matches) == 4

        # Re-sync the graph explicitly: MERGE keeps node/edge counts stable.
        graph_sync = GraphSyncService(graph_store, settings)
        async with factory() as session:
            entity_repo = EntityRepository(session)
            rel_repo = RelationshipRepository(session)
            entities, _ = await entity_repo.list_entities(case_id=case_id, limit=1000)
            relationships = await rel_repo.list_relationships(case_id, limit=1000)
        nodes, edges = await graph_sync.sync_case(
            case_id=case_id, entities=entities, relationships=relationships
        )
        assert nodes == 6
        assert edges == 9

        graph_nodes, graph_edges = await graph_sync.case_graph(case_id)
        assert len(graph_nodes) == 6
        assert len(graph_edges) == 9
    finally:
        await _cleanup(database, storage, graph_store, case_id)


async def test_ingestion_is_idempotent_and_free_text_works(
    database: Database, graph_store: GraphStore, storage: Storage
) -> None:
    case_id = await _new_case(database)
    try:
        object_key = f"cases/{case_id}/evidence/int.txt"
        storage.upload(object_key, TXT_BYTES, "text/plain")

        factory = database.session_factory()
        async with factory() as session:
            evidence_repo = EvidenceRepository(session)
            source = await evidence_repo.get_or_create_data_source("integration-test")
            evidence = await evidence_repo.create_evidence_file(
                case_id=case_id,
                data_source_id=source.id,
                original_filename="int.txt",
                stored_key=object_key,
                content_type="text/plain",
                file_size=len(TXT_BYTES),
                sha256=fingerprint(TXT_BYTES),
                metadata_json=None,
            )
            await session.commit()
            evidence_id = evidence.id

        async with factory() as session:
            service = _ingestion(session, storage, graph_store)
            job = await service.ingest(case_id=case_id, evidence_file_id=evidence_id)
            assert job.status == "completed"
            assert job.graph_sync_status == "synced"
            engine = EntityRepository(session)
            first_counts = await engine.count_entities_by_type(case_id)
            assert first_counts.get("vehicle", 0) == 1  # rule-detected, deterministic

            job_two = await service.ingest(case_id=case_id, evidence_file_id=evidence_id)
            assert job_two.status == "completed"
            assert job_two.graph_sync_status == "synced"
            # A08: a second ingest of the same evidence file reuses the existing
            # job (unique on case_id + evidence_file_id) instead of queuing a
            # redundant one.
            assert job_two.id == job.id

            second_counts = await engine.count_entities_by_type(case_id)
            assert dict(second_counts) == dict(first_counts)
            jobs, _ = await EvidenceRepository(session).list_jobs(case_id)
            assert len(jobs) == 1
    finally:
        await _cleanup(database, storage, graph_store, case_id)


async def test_same_relationship_via_structured_and_co_occurrence_is_single_edge(
    database: Database, graph_store: GraphStore, storage: Storage
) -> None:
    """One logical edge regardless of which evidence mechanism found it.

    A relationship between the same case, entity pair and type must produce
    exactly one database row, one graph API edge and one Neo4j relationship even
    when first discovered through structured fields and then re-discovered
    through free-text co-occurrence. Evidence for both mechanisms is preserved
    under the single canonical relationship.
    """
    case_id = await _new_case(database)
    try:
        factory = database.session_factory()
        rel_repo = RelationshipRepository
        async with factory() as session:
            evidence_repo = EvidenceRepository(session)
            source = await evidence_repo.get_or_create_data_source("integration-test")

            csv_key = f"cases/{case_id}/evidence/csv-single.csv"
            storage.upload(csv_key, CSV_SINGLE_BYTES, "text/csv")
            csv_evidence = await evidence_repo.create_evidence_file(
                case_id=case_id,
                data_source_id=source.id,
                original_filename="csv-single.csv",
                stored_key=csv_key,
                content_type="text/csv",
                file_size=len(CSV_SINGLE_BYTES),
                sha256=fingerprint(CSV_SINGLE_BYTES),
                metadata_json={"format": "csv"},
            )

            txt_key = f"cases/{case_id}/evidence/txt-repeat.txt"
            storage.upload(txt_key, TXT_REPEAT_BYTES, "text/plain")
            txt_evidence = await evidence_repo.create_evidence_file(
                case_id=case_id,
                data_source_id=source.id,
                original_filename="txt-repeat.txt",
                stored_key=txt_key,
                content_type="text/plain",
                file_size=len(TXT_REPEAT_BYTES),
                sha256=fingerprint(TXT_REPEAT_BYTES),
                metadata_json={"format": "txt"},
            )
            await session.commit()
            csv_evidence_id = csv_evidence.id
            txt_evidence_id = txt_evidence.id

        # 1. Structured discovery alone: 7 logical relationships, all field-based.
        async with factory() as session:
            service = _ingestion(session, storage, graph_store)
            job = await service.ingest(case_id=case_id, evidence_file_id=csv_evidence_id)
            assert job.status == "completed"
            assert job.summary is not None
            assert job.summary["relationships"] == 7

            relationships = await rel_repo(session).list_relationships(case_id, limit=1000)
            assert len(relationships) == 7
            evidence_rows: list[str] = []
            for relationship in relationships:
                items = await rel_repo(session).list_evidence(relationship.id)
                evidence_rows.extend(item.evidence_type for item in items)
            assert sorted(evidence_rows) == ["field"] * 7

        # 2. Co-occurrence re-discovers those same facts in free text.
        async with factory() as session:
            service = _ingestion(session, storage, graph_store)
            job_two = await service.ingest(case_id=case_id, evidence_file_id=txt_evidence_id)
            assert job_two.status == "completed"
            assert job_two.summary is not None
            assert job_two.summary["relationships"] == 7

            relationships = await rel_repo(session).list_relationships(case_id, limit=1000)
            assert len(relationships) == 7

            entities, _ = await EntityRepository(session).list_entities(case_id=case_id, limit=1000)
            by_type_and_value = {
                (entity.entity_type, entity.canonical_value): entity.id for entity in entities
            }
            person_id = by_type_and_value[("person", "rajesh kumar")]
            phone_id = by_type_and_value[("phone", "919876543210")]

            called = [
                rel
                for rel in relationships
                if rel.relationship_type == "called"
                and str(rel.source_entity_id) == str(person_id)
                and str(rel.target_entity_id) == str(phone_id)
            ]
            assert len(called) == 1
            called_provenance = await rel_repo(session).list_evidence(called[0].id)
            assert {item.evidence_type for item in called_provenance} == {
                "field",
                "co_occurrence",
            }

            owns = [
                rel
                for rel in relationships
                if rel.relationship_type == "owns" and str(rel.source_entity_id) == str(person_id)
            ]
            assert len(owns) == 1
            owns_provenance = await rel_repo(session).list_evidence(owns[0].id)
            assert {item.evidence_type for item in owns_provenance} == {"field"}

        # 3. Graph API: canonical edges, no logical duplicates.
        async with factory() as session:
            graph = await EntityQueryService(
                session,
                entity_repository=EntityRepository(session),
                evidence_repository=EvidenceRepository(session),
                relationship_repository=RelationshipRepository(session),
            ).build_graph(case_id)
            assert len(graph["nodes"]) == 5
            assert len(graph["edges"]) == 7
            seen: set[tuple[str, str, str]] = set()
            for edge in graph["edges"]:
                key = (edge["source"], edge["target"], edge["relationship_type"])
                assert key not in seen
                seen.add(key)

        # 4. Neo4j projection mirrors the canonical edges exactly.
        holograph = GraphSyncService(graph_store, get_settings())
        graph_nodes, graph_edges = await holograph.case_graph(case_id)
        assert len(graph_nodes) == 5
        assert len(graph_edges) == 7
        canonical_ids = {edge["id"] for edge in graph_edges}
        async with graph_store.driver().session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {case_id: $cid})-[r]->(b:Entity {case_id: $cid})
                RETURN a.id AS source, b.id AS target, type(r) AS rel_type, r.id AS edge_id
                """,
                {"cid": str(case_id)},
            )
            neo4j_edges = [record.data() async for record in result]
        assert len(neo4j_edges) == 7
        neo4j_keys = {(e["source"], e["target"], e["rel_type"]) for e in neo4j_edges}
        assert len(neo4j_keys) == 7
        assert all(e["edge_id"] in canonical_ids for e in neo4j_edges)

        # 5. A legacy duplicate edge (same endpoints/type, foreign id) is pruned
        #    back to the canonical one on the next sync.
        async with graph_store.driver().session() as session:
            await session.run(
                """
                MATCH (a:Entity {case_id: $cid, id: $person})
                MATCH (b:Entity {case_id: $cid, id: $phone})
                MERGE (a)-[r:CALLED]->(b)
                ON CREATE SET r.id = 'legacy-dup-edge', r.case_id = $cid
                """,
                {"cid": str(case_id), "person": str(person_id), "phone": str(phone_id)},
            )
        async with factory() as session:
            entities, _ = await EntityRepository(session).list_entities(case_id=case_id, limit=1000)
            relationships = await rel_repo(session).list_relationships(case_id, limit=1000)
        await holograph.sync_case(case_id=case_id, entities=entities, relationships=relationships)
        _, pruned_edges = await holograph.case_graph(case_id)
        assert len(pruned_edges) == 7
        async with graph_store.driver().session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {case_id: $cid})-[r]->(b:Entity {case_id: $cid})
                RETURN collect(r.id) AS edge_ids
                """,
                {"cid": str(case_id)},
            )
            record = await result.single()
            assert record is not None
            assert sorted(record["edge_ids"]) == sorted(canonical_ids)
    finally:
        await _cleanup(database, storage, graph_store, case_id)

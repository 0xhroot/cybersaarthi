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
        for evidence in await evidence_repo.list_evidence(case_id):
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
                "owns": 2,
                "works_for": 2,
                "located_at": 4,
                "visited": 4,
            }

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
        assert edges == 14

        graph_nodes, graph_edges = await graph_sync.case_graph(case_id)
        assert len(graph_nodes) == 6
        assert len(graph_edges) == 14
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

            second_counts = await engine.count_entities_by_type(case_id)
            assert dict(second_counts) == dict(first_counts)
            jobs = await EvidenceRepository(session).list_jobs(case_id)
            assert len(jobs) == 2
    finally:
        await _cleanup(database, storage, graph_store, case_id)

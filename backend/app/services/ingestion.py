"""End-to-end evidence ingestion pipeline for one evidence file.

By default this runs synchronously in the API request (single-worker local
mode). Every step is idempotent: records and candidates use PostgreSQL unique
constraints, so re-running a job never duplicates state. After PostgreSQL
settles, the graph projection is synced to Neo4j (MERGE) and the job's
``graph_sync_status`` reflects the outcome.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import EvidenceFormat
from app.db.storage import Storage
from app.models import DataSource, Entity, EvidenceFile, IngestionJob, Relationship
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.services.extraction import Mention, extract_record_mentions
from app.services.graph_sync import GraphSyncService
from app.services.parsing import parse
from app.services.relationships import extract_relationships
from app.services.resolution import build_record_context, resolve_candidate
from app.services.validation import detect_encoding, detect_format

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        evidence_repository: EvidenceRepository,
        entity_repository: EntityRepository,
        relationship_repository: RelationshipRepository,
        storage: Storage,
        graph_sync: GraphSyncService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._evidence_repository = evidence_repository
        self._entity_repository = entity_repository
        self._relationship_repository = relationship_repository
        self._storage = storage
        self._graph_sync = graph_sync
        self._settings = settings

    async def ensure_data_source(self, name: str, description: str | None = None) -> DataSource:
        return await self._evidence_repository.get_or_create_data_source(name, description)

    async def ingest(
        self,
        *,
        case_id: uuid.UUID,
        evidence_file_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionJob:
        evidence = await self._evidence_repository.get_evidence(evidence_file_id)
        if evidence is None:
            raise ValueError(f"evidence file {evidence_file_id} does not exist")
        if str(evidence.case_id) != str(case_id):
            raise ValueError("evidence file belongs to a different case")

        job = await self._evidence_repository.create_job(
            case_id=case_id,
            evidence_file_id=evidence_file_id,
            status="pending",
        )
        await self._session.commit()

        stage = "created"
        try:
            await self._run(job, evidence)
        except Exception as exc:
            logger.exception("ingestion job failed", extra={"job_id": str(job.id), "stage": stage})
            await self._evidence_repository.fail_job(job.id, error=str(exc), stage=stage)
            await self._session.commit()

        final_job = await self._evidence_repository.get_job(job.id)
        assert final_job is not None
        return final_job

    async def _run(
        self,
        job: IngestionJob,
        evidence: EvidenceFile,
    ) -> None:
        case_id = uuid.UUID(str(job.case_id))
        raw_data = await asyncio.to_thread(self._storage.download, evidence.stored_key)
        fmt = detect_format(evidence.original_filename, raw_data)
        encoding = detect_encoding(raw_data)
        records = parse(raw_data, fmt, encoding)
        await self._evidence_repository.update_evidence(
            evidence.id,
            format=fmt.value,
            encoding=encoding,
            record_count=len(records),
            status="processing",
        )
        await self._evidence_repository.mark_job_running(
            job.id, total_records=len(records), stage="parsed"
        )
        await self._session.flush()

        is_structured = fmt != EvidenceFormat.TXT
        created_records = 0
        for record_no, raw in enumerate(records, start=1):
            source_record = await self._evidence_repository.create_source_record(
                evidence_file_id=evidence.id,
                record_no=record_no,
                raw_data=raw,
            )
            if source_record is None:
                source_record = await self._evidence_repository.get_source_record(
                    evidence.id, record_no
                )
                if source_record is None:
                    continue
            else:
                created_records += 1

            mentions = extract_record_mentions(raw, self._settings.SPA_MODEL)
            record_signals = [m.canonical for m in mentions]
            await self._evidence_repository.update_source_record(
                source_record.id,
                normalized_data={"format": fmt.value, "mention_count": len(mentions)},
                entity_mentions=[asdict(mention) for mention in mentions],
                status="extracted",
            )

            resolved: dict[tuple[str, str], uuid.UUID | None] = {}
            for mention in mentions:
                outcome = await self._resolve_mention(
                    source_record.id, mention, case_id, record_signals
                )
                if outcome is not None:
                    resolved[(mention.entity_type, mention.canonical)] = outcome
            await self._session.flush()

            text = str(raw.get("text", "")) if not is_structured else ""
            extracted = extract_relationships(
                mentions,
                {key: tid for key, tid in resolved.items() if tid is not None},
                is_structured=is_structured,
                text=text,
            )
            persisted_rel = 0
            for rel in extracted:
                source_id = resolved.get(rel.source_key)
                target_id = resolved.get(rel.target_key)
                if source_id is None or target_id is None:
                    continue
                row = await self._relationship_repository.create_relationship(
                    case_id=case_id,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relationship_type=rel.relationship_type,
                    confidence=rel.context.get("confidence"),
                    source_record_id=source_record.id,
                    context=rel.context,
                    explanation=rel.explanation,
                )
                if row is not None:
                    persisted_rel += 1
                    await self._relationship_repository.create_relationship_evidence(
                        relationship_id=row.id,
                        source_record_id=source_record.id,
                        evidence_type=rel.evidence_type,
                        snippet=rel.snippet,
                    )
            await self._evidence_repository.update_source_record(
                source_record.id,
                relationships_data=[
                    {
                        "relationship_type": rel.relationship_type,
                        "source": list(rel.source_key),
                        "target": list(rel.target_key),
                        "evidence_type": rel.evidence_type,
                    }
                    for rel in extracted
                ],
                status="resolved",
            )
            await self._evidence_repository.tick_job_progress(
                job.id, processed_records=record_no, stage=f"record-{record_no}"
            )
            await self._session.flush()

        await self._sync_graph(case_id, job)

        entity_types = await self._entity_repository.count_entities_by_type(case_id)
        relationship_types = await self._relationship_repository.count_by_type(case_id)
        relationship_total = await self._relationship_repository.count_relationships(case_id)
        summary = {
            "records": len(records),
            "created_records": created_records,
            "entities": sum(entity_types.values()),
            "entity_types": entity_types,
            "relationships": relationship_total,
            "relationship_types": relationship_types,
        }
        final_job = await self._evidence_repository.get_job(job.id)
        graph_status = str(final_job.graph_sync_status) if final_job else "pending"
        await self._evidence_repository.complete_job(
            job.id,
            summary=summary,
            graph_sync_status=graph_status,
        )
        await self._evidence_repository.update_evidence(evidence.id, status="parsed")
        await self._session.commit()

    async def _resolve_mention(
        self,
        source_record_id: uuid.UUID,
        mention: Mention,
        case_id: uuid.UUID,
        record_signals: list[str],
    ) -> uuid.UUID | None:
        context_signals = [signal for signal in record_signals if signal != mention.canonical]
        candidate = await self._entity_repository.create_candidate(
            source_record_id=source_record_id,
            entity_type=mention.entity_type,
            raw_value=mention.raw,
            normalized_value=mention.canonical,
            blocking_key=mention.blocking_key,
            confidence=mention.confidence,
            source=mention.source,
            context=build_record_context(context_signals),
        )
        if candidate is None:
            candidate = await self._entity_repository.get_candidate_by_record_and_value(
                source_record_id, mention.entity_type, mention.canonical
            )
            if candidate is None or candidate.resolution_status != "pending":
                if candidate is not None and candidate.entity_id is not None:
                    return uuid.UUID(str(candidate.entity_id))
                return None
        outcome = await resolve_candidate(
            candidate_id=candidate.id,
            case_id=case_id,
            entity_type=mention.entity_type,
            canonical=mention.canonical,
            blocking_key=mention.blocking_key,
            display=mention.display,
            candidate_signals=context_signals,
            confidence=mention.confidence,
            settings=self._settings,
            repository=self._entity_repository,
        )
        await self._session.flush()
        return outcome.entity.id if outcome.entity else None

    async def _sync_graph(self, case_id: uuid.UUID, job: IngestionJob) -> tuple[int, int]:
        try:
            entities = await self._list_entities(case_id)
            relationships = await self._list_relationships(case_id)
            nodes, edges = await self._graph_sync.sync_case(
                case_id=case_id,
                entities=entities,
                relationships=relationships,
            )
            await self._evidence_repository.mark_graph_sync(job.id, status="synced")
            if job.summary is None:
                job.summary = {}
            job.summary = {**job.summary, "graph_nodes": nodes, "graph_edges": edges}
            await self._session.flush()
            return nodes, edges
        except Exception as exc:
            logger.exception("graph sync failed", extra={"case_id": str(case_id)})
            await self._evidence_repository.mark_graph_sync(
                job.id, status="failed", error=str(exc)[:2000]
            )
            return 0, 0

    async def retry_graph_sync(self, job_id: uuid.UUID) -> tuple[int, int]:
        job = await self._evidence_repository.get_job(job_id)
        if job is None:
            raise ValueError(f"job {job_id} does not exist")
        case_id = uuid.UUID(str(job.case_id))
        await self._evidence_repository.mark_graph_sync(job.id, status="pending")
        result = await self._sync_graph(case_id, job)
        await self._session.commit()
        return result

    async def get_job(self, job_id: uuid.UUID) -> IngestionJob | None:
        return await self._evidence_repository.get_job(job_id)

    async def _list_entities(self, case_id: uuid.UUID) -> list[Entity]:
        result, _ = await self._entity_repository.list_entities(case_id=case_id, limit=10000)
        return result

    async def _list_relationships(self, case_id: uuid.UUID) -> list[Relationship]:
        return await self._relationship_repository.list_relationships(case_id, limit=10000)

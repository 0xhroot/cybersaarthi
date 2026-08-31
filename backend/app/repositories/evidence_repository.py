"""Data access for evidence files, source records and ingestion jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource, EvidenceFile, IngestionJob, SourceRecord


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Data sources ---------------------------------------------------------
    async def get_or_create_data_source(
        self, name: str, description: str | None = None
    ) -> DataSource:
        """Return an existing data source or create it (A08).

        Concurrency-safe: two workers simultaneously seeding the same named
        source race on the ``name`` unique index; ``on_conflict_do_nothing``
        lets one insert win and the other refetch instead of raising a 500.
        """
        statement = (
            pg_insert(DataSource)
            .values(name=name, description=description)
            .on_conflict_do_nothing(index_elements=["name"])
            .returning(DataSource.id)
        )
        result = await self._session.execute(statement)
        source_id = result.scalar_one_or_none()
        if source_id is not None:
            return await self._session.get(DataSource, source_id)  # type: ignore[return-value]
        existing = await self._session.scalar(select(DataSource).where(DataSource.name == name))
        return existing  # type: ignore[return-value]

    # Evidence files -------------------------------------------------------
    async def get_evidence(self, evidence_file_id: uuid.UUID) -> EvidenceFile | None:
        return await self._session.get(EvidenceFile, evidence_file_id)

    async def delete_evidence(self, evidence_file_id: uuid.UUID) -> EvidenceFile | None:
        """Delete the row; DB-level cascades remove source records, and
        ingestion jobs get their evidence reference set to NULL."""
        evidence = await self.get_evidence(evidence_file_id)
        if evidence is None:
            return None
        await self._session.delete(evidence)
        return evidence

    async def get_by_sha(self, case_id: uuid.UUID, sha256: str) -> EvidenceFile | None:
        result = await self._session.execute(
            select(EvidenceFile).where(
                EvidenceFile.case_id == str(case_id),
                EvidenceFile.sha256 == sha256,
            )
        )
        return result.scalar_one_or_none()

    async def create_evidence_file(
        self,
        *,
        case_id: uuid.UUID,
        data_source_id: uuid.UUID | None,
        original_filename: str,
        stored_key: str,
        content_type: str,
        file_size: int,
        sha256: str,
        metadata_json: dict[str, object] | None,
    ) -> EvidenceFile:
        evidence = EvidenceFile(
            case_id=str(case_id),
            data_source_id=str(data_source_id) if data_source_id else None,
            original_filename=original_filename,
            stored_key=stored_key,
            content_type=content_type,
            file_size=file_size,
            sha256=sha256,
            metadata_json=metadata_json,
        )
        self._session.add(evidence)
        await self._session.flush()
        return evidence

    async def update_evidence(
        self,
        evidence_file_id: uuid.UUID,
        *,
        format: str | None = None,
        encoding: str | None = None,
        record_count: int | None = None,
        status: str = "stored",
        status_detail: str | None = None,
    ) -> None:
        evidence = await self.get_evidence(evidence_file_id)
        if evidence is None:
            return
        if format is not None:
            evidence.format = format
        if encoding is not None:
            evidence.encoding = encoding
        if record_count is not None:
            evidence.record_count = record_count
        evidence.status = status
        evidence.status_detail = status_detail
        await self._session.flush()

    async def list_evidence(
        self, case_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[EvidenceFile], int]:
        base = select(EvidenceFile).where(EvidenceFile.case_id == str(case_id))
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(EvidenceFile.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)

    # Source records -------------------------------------------------------
    async def create_source_record(
        self,
        *,
        evidence_file_id: uuid.UUID,
        record_no: int,
        raw_data: dict[str, object],
        status: str = "parsed",
    ) -> SourceRecord | None:
        statement = (
            pg_insert(SourceRecord)
            .values(
                evidence_file_id=str(evidence_file_id),
                record_no=int(record_no),
                raw_data=raw_data,
                status=status,
            )
            .on_conflict_do_nothing(
                constraint="uq_source_records_file_record",
            )
            .returning(SourceRecord.id)
        )
        result = await self._session.execute(statement)
        record_id = result.scalar_one_or_none()
        if record_id is None:
            return None
        record = await self._session.get(SourceRecord, record_id)
        return record

    async def get_source_records(self, evidence_file_id: uuid.UUID) -> list[SourceRecord]:
        result = await self._session.execute(
            select(SourceRecord)
            .where(SourceRecord.evidence_file_id == str(evidence_file_id))
            .order_by(SourceRecord.record_no)
        )
        return list(result.scalars())

    async def get_source_record(
        self, evidence_file_id: uuid.UUID, record_no: int
    ) -> SourceRecord | None:
        result = await self._session.execute(
            select(SourceRecord).where(
                SourceRecord.evidence_file_id == str(evidence_file_id),
                SourceRecord.record_no == int(record_no),
            )
        )
        return result.scalar_one_or_none()

    async def update_source_record(
        self,
        source_record_id: uuid.UUID,
        *,
        normalized_data: dict[str, object] | None = None,
        entity_mentions: list[dict[str, object]] | None = None,
        relationships_data: list[dict[str, object]] | None = None,
        status: str = "parsed",
        error: str | None = None,
    ) -> None:
        record = await self._session.get(SourceRecord, source_record_id)
        if record is None:
            return
        if normalized_data is not None:
            record.normalized_data = normalized_data
        if entity_mentions is not None:
            record.entity_mentions = entity_mentions
        if relationships_data is not None:
            record.relationships_data = relationships_data
        record.status = status
        record.error = error
        await self._session.flush()

    async def count_source_records(self, evidence_file_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count(SourceRecord.id)).where(
                SourceRecord.evidence_file_id == str(evidence_file_id)
            )
        )
        return int(result.scalar_one())

    # Ingestion jobs -------------------------------------------------------
    async def create_job(
        self,
        *,
        case_id: uuid.UUID,
        evidence_file_id: uuid.UUID,
        status: str = "pending",
        actor_id: uuid.UUID | None = None,
    ) -> IngestionJob:
        """Create or return the existing ingestion job for this evidence (A08).

        Two concurrent ingests of the same evidence file race on
        ``uq_ingestion_jobs_case_evidence``; ``on_conflict_do_nothing`` makes
        the first queued job win and the second refetch it rather than queuing
        a redundant job.
        """
        statement = (
            pg_insert(IngestionJob)
            .values(
                case_id=str(case_id),
                evidence_file_id=str(evidence_file_id),
                status=status,
                actor_id=actor_id,
            )
            .on_conflict_do_nothing(constraint="uq_ingestion_jobs_case_evidence")
            .returning(IngestionJob.id)
        )
        result = await self._session.execute(statement)
        job_id = result.scalar_one_or_none()
        if job_id is not None:
            return await self._session.get(IngestionJob, job_id)  # type: ignore[return-value]
        existing = await self._session.scalar(
            select(IngestionJob).where(
                IngestionJob.case_id == str(case_id),
                IngestionJob.evidence_file_id == str(evidence_file_id),
            )
        )
        return existing  # type: ignore[return-value]

    async def get_job(self, job_id: uuid.UUID) -> IngestionJob | None:
        # Loaded with a real SELECT (not ``session.get``) so server-generated
        # columns such as ``updated_at`` are always fresh: commit() expires
        # onupdate values, and the async ORM cannot lazy-load expired columns.
        result = await self._session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_jobs(
        self, case_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[IngestionJob], int]:
        base = select(IngestionJob).where(IngestionJob.case_id == str(case_id))
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(IngestionJob.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)

    async def mark_job_running(
        self,
        job_id: uuid.UUID,
        *,
        total_records: int = 0,
        stage: str,
    ) -> None:
        job = await self._session.get(IngestionJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.stage = stage
        job.total_records = total_records
        job.started_at = datetime.now(UTC)
        await self._session.flush()

    async def tick_job_progress(
        self,
        job_id: uuid.UUID,
        *,
        processed_records: int,
        stage: str,
    ) -> None:
        job = await self._session.get(IngestionJob, job_id)
        if job is None:
            return
        job.processed_records = processed_records
        job.stage = stage
        if job.total_records > 0:
            job.progress = min(99, round(processed_records / job.total_records * 100))
        await self._session.flush()

    async def complete_job(
        self,
        job_id: uuid.UUID,
        *,
        summary: dict[str, object],
        graph_sync_status: str = "pending",
    ) -> None:
        job = await self._session.get(IngestionJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.summary = summary
        job.graph_sync_status = graph_sync_status
        job.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def fail_job(self, job_id: uuid.UUID, *, error: str, stage: str) -> None:
        job = await self._session.get(IngestionJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.stage = stage
        job.error = error[:2000]
        job.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_graph_sync(
        self, job_id: uuid.UUID, *, status: str, error: str | None = None
    ) -> None:
        job = await self._session.get(IngestionJob, job_id)
        if job is None:
            return
        job.graph_sync_status = status
        job.graph_error = error
        await self._session.flush()

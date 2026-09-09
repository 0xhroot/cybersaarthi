"""The ingestion job lifecycle is a state machine: a job starts ``pending``,
moves to ``running``, and ends in ``completed``/``failed``/``partial``. Terminal
jobs are never put back into ``running`` (which would happen if a re-ingest
re-ran an already-processed evidence file)."""

from __future__ import annotations

import uuid

import pytest
from app.db.postgres import Database
from app.models import Case, EvidenceFile, IngestionJob
from app.repositories.evidence_repository import EvidenceRepository, JobTransitionError
from sqlalchemy import delete


@pytest.fixture
async def job(database: Database) -> IngestionJob:
    """A pending ingestion job wired to a throwaway case + evidence row."""
    case = Case(
        id=uuid.uuid4(),
        case_number=f"SM-{uuid.uuid4().hex[:8]}",
        title="state-machine test case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        evidence = EvidenceFile(
            id=uuid.uuid4(),
            case_id=str(case.id),
            original_filename="sm.csv",
            stored_key=f"cases/{case.id}/evidence/sm.csv",
            content_type="text/csv",
            file_size=0,
            sha256=uuid.uuid4().hex,
        )
        session.add(evidence)
        await session.commit()
        created = await EvidenceRepository(session).create_job(
            case_id=case.id,
            evidence_file_id=evidence.id,
            status="pending",
            actor_id=None,
        )
        await session.commit()
        evidence_id = evidence.id
        case_id = case.id
    yield created
    async with factory() as session:
        await session.execute(delete(IngestionJob).where(IngestionJob.case_id == str(case_id)))
        await session.execute(delete(EvidenceFile).where(EvidenceFile.id == evidence_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_pending_job_can_start(database: Database, job: IngestionJob) -> None:
    factory = database.session_factory()
    async with factory() as session:
        await EvidenceRepository(session).mark_job_running(job.id, total_records=5, stage="parsed")
        await session.commit()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "running"


async def test_running_job_can_complete(database: Database, job: IngestionJob) -> None:
    factory = database.session_factory()
    async with factory() as session:
        repo = EvidenceRepository(session)
        await repo.mark_job_running(job.id, total_records=5, stage="parsed")
        await repo.complete_job(job.id, summary={"records": 5}, graph_sync_status="synced")
        await session.commit()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "completed"
    assert status.graph_sync_status == "synced"


async def test_running_job_can_fail(database: Database, job: IngestionJob) -> None:
    factory = database.session_factory()
    async with factory() as session:
        repo = EvidenceRepository(session)
        await repo.mark_job_running(job.id, total_records=5, stage="parsed")
        await repo.fail_job(job.id, error="boom", stage="parsed")
        await session.commit()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "failed"


async def test_running_job_can_be_marked_partial(database: Database, job: IngestionJob) -> None:
    factory = database.session_factory()
    async with factory() as session:
        repo = EvidenceRepository(session)
        await repo.mark_job_running(job.id, total_records=5, stage="parsed")
        await repo.tick_job_progress(job.id, processed_records=2, stage="record-2")
        await repo.mark_job_partial(job.id, error="interrupted after 2", stage="record-2")
        await session.commit()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "partial"


async def test_terminal_job_cannot_return_to_running(database: Database, job: IngestionJob) -> None:
    """Regression: a completed job must never bounce back to ``running``.

    A re-ingest of an already-processed evidence file used to re-run the whole
    pipeline, dragging the job through ``running`` again. The state machine now
    forbids that transition.
    """
    factory = database.session_factory()
    async with factory() as session:
        repo = EvidenceRepository(session)
        await repo.mark_job_running(job.id, total_records=1, stage="parsed")
        await repo.complete_job(job.id, summary={"records": 1}, graph_sync_status="synced")
        await session.commit()

    async with factory() as session:
        repo = EvidenceRepository(session)
        with pytest.raises(JobTransitionError):
            await repo.mark_job_running(job.id, total_records=1, stage="parsed")
        await session.rollback()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "completed"


async def test_terminal_job_cannot_be_completed_again(
    database: Database, job: IngestionJob
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        repo = EvidenceRepository(session)
        await repo.mark_job_running(job.id, total_records=1, stage="parsed")
        await repo.complete_job(job.id, summary={"records": 1}, graph_sync_status="synced")
        await session.commit()

    async with factory() as session:
        repo = EvidenceRepository(session)
        with pytest.raises(JobTransitionError):
            await repo.complete_job(job.id, summary={"records": 1}, graph_sync_status="synced")
        await session.rollback()
        status = await EvidenceRepository(session).get_job(job.id)
    assert status is not None
    assert status.status == "completed"


async def test_latest_job_graph_status_reflects_newest_job(database: Database) -> None:
    """``graph/stats`` reports the current projection state: the newest job, not
    any historical success. If an older job synced but a newer one failed, the
    Neo4j projection is stale and must report unsynced."""
    from datetime import UTC, datetime

    case = Case(
        id=uuid.uuid4(),
        case_number=f"SM-{uuid.uuid4().hex[:8]}",
        title="graph-state test case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id

        old_evidence = EvidenceFile(
            id=uuid.uuid4(),
            case_id=str(case_id),
            original_filename="old.csv",
            stored_key=f"cases/{case_id}/evidence/old.csv",
            content_type="text/csv",
            file_size=0,
            sha256=uuid.uuid4().hex,
        )
        new_evidence = EvidenceFile(
            id=uuid.uuid4(),
            case_id=str(case_id),
            original_filename="new.csv",
            stored_key=f"cases/{case_id}/evidence/new.csv",
            content_type="text/csv",
            file_size=0,
            sha256=uuid.uuid4().hex,
        )
        session.add_all([old_evidence, new_evidence])
        await session.commit()

        repo = EvidenceRepository(session)
        old_job = await repo.create_job(
            case_id=case_id, evidence_file_id=old_evidence.id, status="pending"
        )
        new_job = await repo.create_job(
            case_id=case_id, evidence_file_id=new_evidence.id, status="pending"
        )
        # pin explicit, ordered created_at so the newest job is deterministic
        old_job.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        new_job.created_at = datetime(2026, 1, 2, tzinfo=UTC)
        await repo.mark_job_running(old_job.id, total_records=1, stage="parsed")
        await repo.complete_job(old_job.id, summary={"records": 1}, graph_sync_status="synced")
        await session.commit()

        # newest job is created later and its graph sync failed
        await repo.mark_job_running(new_job.id, total_records=1, stage="parsed")
        await repo.mark_graph_sync(new_job.id, status="failed", error="bolt timeout")
        await session.commit()

        assert await repo.latest_job_graph_status(case_id) == "failed"

        # a single-job case that synced reports synced
        await repo.mark_graph_sync(new_job.id, status="synced")
        await session.commit()
        assert await repo.latest_job_graph_status(case_id) == "synced"

    async with factory() as session2:
        await session2.execute(delete(IngestionJob).where(IngestionJob.case_id == str(case_id)))
        await session2.execute(delete(EvidenceFile).where(EvidenceFile.case_id == str(case_id)))
        await session2.execute(delete(Case).where(Case.id == case_id))
        await session2.commit()

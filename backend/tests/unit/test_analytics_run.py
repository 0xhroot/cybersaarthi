"""The analytics-run lifecycle is a state machine: a run is created ``pending``,
started to ``running``, and ends in ``completed``/``failed``. Terminal runs are
never transitioned again and always get a ``completed_at`` stamp."""

from __future__ import annotations

import uuid

import pytest
from app.db.postgres import Database
from app.models import AnalyticsRun, Case, Finding
from app.repositories.analytics_repository import (
    AnalyticsDataRepository,
    RunTransitionError,
)
from sqlalchemy import delete


@pytest.fixture
async def case_id(database: Database) -> uuid.UUID:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"AR-{uuid.uuid4().hex[:8]}",
        title="analytics-run state-machine test case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
    yield case.id
    async with factory() as session:
        await session.execute(delete(AnalyticsRun).where(AnalyticsRun.case_id == str(case.id)))
        await session.execute(delete(Case).where(Case.id == case.id))
        await session.commit()


async def _create_pending(database: Database, case_id: uuid.UUID) -> AnalyticsRun:
    factory = database.session_factory()
    async with factory() as session:
        run = await AnalyticsDataRepository(session).create_run(case_id)
        await session.commit()
    return run


async def test_run_starts_pending_then_running_then_completed(
    database: Database, case_id: uuid.UUID
) -> None:
    run = await _create_pending(database, case_id)
    factory = database.session_factory()
    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        assert run.status == "pending"
        await repo.start_run(run.id, stage="compute")
        await repo.update_run(run.id, status="completed", stage="done", summary={})
        await session.commit()
        row = await session.get(AnalyticsRun, run.id)
        assert row is not None
        assert row.status == "completed"
        assert row.started_at is not None
        assert row.completed_at is not None


async def test_run_can_fail_after_starting(database: Database, case_id: uuid.UUID) -> None:
    run = await _create_pending(database, case_id)
    factory = database.session_factory()
    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        await repo.start_run(run.id, stage="compute")
        await repo.update_run(run.id, status="failed", stage="error", error="boom")
        await session.commit()
        row = await session.get(AnalyticsRun, run.id)
        assert row is not None
        assert row.status == "failed"
        assert row.completed_at is not None


async def test_terminal_run_cannot_be_transitioned_again(
    database: Database, case_id: uuid.UUID
) -> None:
    run = await _create_pending(database, case_id)
    factory = database.session_factory()
    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        await repo.start_run(run.id, stage="compute")
        await repo.update_run(run.id, status="completed", stage="done", summary={})
        await session.commit()

    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        with pytest.raises(RunTransitionError):
            await repo.update_run(run.id, status="failed", stage="error", error="boom")
        await session.rollback()
        row = await session.get(AnalyticsRun, run.id)
        assert row is not None
        assert row.status == "completed"


async def test_pending_run_cannot_jump_to_terminal(database: Database, case_id: uuid.UUID) -> None:
    run = await _create_pending(database, case_id)
    factory = database.session_factory()
    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        with pytest.raises(RunTransitionError):
            await repo.update_run(run.id, status="completed", stage="done", summary={})
        await session.rollback()
        row = await session.get(AnalyticsRun, run.id)
        assert row is not None
        assert row.status == "pending"


async def test_findings_are_run_versioned_current_vs_historical(
    database: Database, case_id: uuid.UUID
) -> None:
    """A09 + run-versioning: an unchanged signal across runs stays a single row
    attached to the run that first produced it (HISTORICAL). Repeated runs do not
    inflate the findings table (CURRENT dedup), so ``?run_id=<run>`` can isolate
    exactly one run's snapshot without accumulating duplicates."""
    from sqlalchemy import func, select

    factory = database.session_factory()
    async with factory() as session:
        repo = AnalyticsDataRepository(session)
        run1 = await repo.create_run(case_id)
        await repo.start_run(run1.id, stage="compute")
        findings = [
            {
                "finding_type": "pattern",
                "title": "isolated hub",
                "summary": "summary",
                "severity": "HIGH",
                "score": 0.8,
                "confidence": 0.9,
                "explanation": {"why": "central"},
                "affected_entities": [],
                "affected_relationships": [],
                "evidence_ids": [],
            }
        ]
        inserted1 = await repo.save_findings(case_id, run1.id, findings)
        await repo.update_run(run1.id, status="completed", stage="done", summary={})
        await session.commit()
        assert inserted1 == 1

        run2 = await repo.create_run(case_id)
        await repo.start_run(run2.id, stage="compute")
        inserted2 = await repo.save_findings(case_id, run2.id, findings)
        await repo.update_run(run2.id, status="completed", stage="done", summary={})
        await session.commit()
        assert inserted2 == 0

        total = await session.scalar(
            select(func.count()).select_from(Finding).where(Finding.case_id == str(case_id))
        )
        assert total == 1
        all_rows = (
            (await session.execute(select(Finding).where(Finding.case_id == str(case_id))))
            .scalars()
            .all()
        )
        assert all_rows[0].run_id == run1.id

    async with factory() as session:
        await session.execute(delete(Finding).where(Finding.case_id == str(case_id)))

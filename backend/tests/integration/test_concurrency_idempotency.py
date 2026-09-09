"""A08 regression: idempotent, concurrency-safe row creation.

Verifies that the three double-insert race points now use
``on_conflict_do_nothing`` + refetch instead of a plain INSERT that would raise
``IntegrityError`` (and surface as a 500 / a failed job) when two workers race.
Run with two sessions in parallel to reproduce the real double-insert race.

Each case here uses a random id and cleans up its rows so the store stays tidy.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from app.core.config import Settings, get_settings
from app.db.postgres import Database
from app.models import Case, DataSource, Entity, EvidenceFile, IngestionJob
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _new_case(database: Database, settings: Settings) -> uuid.UUID:
    case_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            Case(
                id=case_id,
                case_number=f"a08-{uuid.uuid4().hex[:10]}",
                title="a08-concurrency",
                status="open",
            )
        )
        await session.commit()
    return case_id


async def _delete_case(database: Database, case_id: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        model = await session.get(Case, case_id)
        if model is not None:
            await session.delete(model)
        await session.commit()


@pytest.fixture
async def a08_case(
    database: Database,
) -> AsyncGenerator[uuid.UUID, None]:
    """Yield a freshly-created case id, deleting its rows on teardown."""
    case_id = await _new_case(database, get_settings())
    yield case_id
    await _delete_case(database, case_id)


async def _create_entity(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    case_id: uuid.UUID,
    suffix: str,
) -> Entity:
    async with session_factory() as session:
        repo = EntityRepository(session)
        entity = await repo.create_entity(
            case_id=case_id,
            entity_type="person",
            canonical_value=f"a08-canonical-{suffix}",
            blocking_key=f"a08-bk-{suffix}",
            display_value=f"A08 person {suffix}",
            confidence=0.9,
        )
        await session.commit()
    return entity


async def test_entity_create_is_idempotent_under_concurrency(
    database: Database, a08_case: uuid.UUID
) -> None:
    factory = database.session_factory()
    case_id = str(a08_case)
    suffix = uuid.uuid4().hex[:8]

    # Two workers race to insert the same new canonical value concurrently.
    a, b = await asyncio.gather(
        _create_entity(factory, case_id=a08_case, suffix=suffix),
        _create_entity(factory, case_id=a08_case, suffix=suffix),
    )

    assert a.id == b.id  # both resolved to the same single row
    async with factory() as session:
        count = (
            (
                await session.execute(
                    select(Entity).where(
                        Entity.case_id == case_id,
                        Entity.canonical_value == f"a08-canonical-{suffix}",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(count) == 1


async def test_data_source_get_or_create_is_concurrency_safe(
    database: Database, a08_case: uuid.UUID
) -> None:
    factory = database.session_factory()
    name = f"a08-source-{uuid.uuid4().hex[:8]}"

    async def _get_or_create() -> DataSource:
        async with factory() as session:
            repo = EvidenceRepository(session)
            source = await repo.get_or_create_data_source(name, "a08 concurrency")
            await session.commit()
            return source

    a, b = await asyncio.gather(_get_or_create(), _get_or_create())
    assert a.id == b.id
    async with factory() as session:
        count = await session.scalar(select(DataSource).where(DataSource.name == name))
    assert count is not None

    async with factory() as session:
        rows = (
            (await session.execute(select(DataSource).where(DataSource.name == name)))
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_ingestion_job_is_concurrency_safe(database: Database, a08_case: uuid.UUID) -> None:
    factory = database.session_factory()
    case_id = str(a08_case)
    evidence_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            EvidenceFile(
                id=evidence_id,
                case_id=case_id,
                original_filename=f"a08-{uuid.uuid4().hex[:8]}.csv",
                stored_key=f"a08/{evidence_id}",
                content_type="text/csv",
                file_size=10,
                sha256=uuid.uuid4().hex,
                status="stored",
            )
        )
        await session.commit()

    async def _create_job() -> IngestionJob:
        async with factory() as session:
            repo = EvidenceRepository(session)
            job = await repo.create_job(
                case_id=a08_case, evidence_file_id=evidence_id, status="pending"
            )
            await session.commit()
            return job

    first, second = await asyncio.gather(_create_job(), _create_job())
    assert first.id == second.id

    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(IngestionJob).where(
                        IngestionJob.case_id == case_id,
                        IngestionJob.evidence_file_id == str(evidence_id),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1

"""Service-level tests: the extraction runner's safety rails (feature 1).

These drive ``execute_extraction`` directly against live PostgreSQL/MinIO with
a scripted extractor, covering what HTTP timing cannot: authorization
revocation between submission and execution, stored-byte tampering, missing
objects, model outages (honest partial/failed states), cooperative
cancellation and timeout. Invariant under test everywhere: a job that stops
early can never report success, and no model call happens without fresh
authorization + verified source bytes.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_EXTRACTION_FAILED,
    CODE_INTEGRITY_MISMATCH,
    CODE_INTEGRITY_SOURCE_MISSING,
    CODE_OCR_REQUIRED,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import (
    AnalysisJob,
    AuditLog,
    CaseMember,
    DerivedArtifact,
    EvidenceFile,
    SourceRecord,
)
from app.services import analysis_jobs as jobs_svc
from app.services.evidence_extraction import execute_extraction
from app.services.validation import fingerprint
from fpdf import FPDF
from sqlalchemy import delete, select

from tests.api.phase2_fakes import FakeAI, extraction_reply

PARAGRAPHS = (
    "Access granted to Officer Nanda at gate two\n\n"
    "Boiler room inspection completed after hours"
)


async def _seed_evidence(
    database: Database,
    storage: Storage,
    case_id: uuid.UUID,
    *,
    data: bytes,
    name: str,
    content_type: str,
    format_: str,
) -> tuple[uuid.UUID, str]:
    key = f"cases/{case_id}/{uuid.uuid4().hex}/{name}"
    await asyncio.to_thread(storage.upload, key, data, content_type)
    factory = database.session_factory()
    async with factory() as session:
        evidence = EvidenceFile(
            case_id=str(case_id),
            original_filename=name,
            stored_key=key,
            content_type=content_type,
            file_size=len(data),
            sha256=fingerprint(data),
            format=format_,
            encoding="utf-8" if format_ == "txt" else None,
            status="stored",
        )
        session.add(evidence)
        await session.commit()
        return evidence.id, key


async def _make_job(
    database: Database,
    *,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    timeout_seconds: int = 600,
    cancel_requested: bool = False,
) -> uuid.UUID:
    factory = database.session_factory()
    async with factory() as session:
        job, _ = await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature="ingestion",
            idempotency_key=f"runner-{uuid.uuid4().hex[:12]}",
            actor_id=actor_id,
            evidence_file_id=evidence_id,
            timeout_seconds=timeout_seconds,
        )
        if cancel_requested:
            jobs_svc.request_cancel(job)
        await session.commit()
        return job.id


async def _run(
    database: Database,
    storage: Storage,
    job_id: uuid.UUID,
    extractor: Any,
) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        await execute_extraction(
            session,
            job_id=job_id,
            settings=get_settings(),
            storage=storage,
            extractor=extractor,
        )
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        await session.refresh(job)
        return job


async def _count(
    database: Database, model: Any, case_id: uuid.UUID
) -> int:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(model.id).where(model.case_id == str(case_id))
        )
        return len(list(rows.scalars()))


async def test_runner_rechecks_authorization_and_denies_revoked_member(
    database: Database,
    storage: Storage,
    user_factory,
    _owned_case: uuid.UUID,
) -> None:
    member = await user_factory(role="INVESTIGATOR")
    factory = database.session_factory()
    async with factory() as session:
        session.add(CaseMember(case_id=_owned_case, user_id=member.id, role="collaborator"))
        await session.commit()
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=PARAGRAPHS.encode(),
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=member.id
    )
    # Access revoked between submission and execution.
    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == member.id))
        await session.commit()

    fake = FakeAI()
    job = await _run(database, storage, job_id, fake)

    assert job.status == "failed"
    assert dict(job.result_summary or {})["error_code"] == CODE_CASE_ACCESS_DENIED
    assert "revoked" in (job.error or "")
    assert fake.extract_calls == []  # denied before any model context
    assert await _count(database, DerivedArtifact, _owned_case) == 0
    async with factory() as session:
        records = await session.execute(
            select(SourceRecord).where(SourceRecord.evidence_file_id == str(evidence_id))
        )
        assert list(records.scalars()) == []  # no parse either
        denied = await session.execute(
            select(AuditLog).where(AuditLog.action == "extraction.denied")
        )
        assert denied.scalars().first() is not None


async def test_runner_aborts_on_hash_mismatch_and_leaves_evidence_untouched(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    original = PARAGRAPHS.encode()
    evidence_id, key = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=original,
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    # Simulated tampering with the stored object (never with the evidence row).
    await asyncio.to_thread(storage.upload, key, b"different bytes entirely", "text/plain")
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=api_user.id
    )
    fake = FakeAI()
    try:
        job = await _run(database, storage, job_id, fake)
    finally:
        await asyncio.to_thread(storage.upload, key, original, "text/plain")

    assert job.status == "failed"
    assert dict(job.result_summary or {})["error_code"] == CODE_INTEGRITY_MISMATCH
    assert fake.extract_calls == []  # tampered bytes never reach the model
    assert await _count(database, DerivedArtifact, _owned_case) == 0
    factory = database.session_factory()
    async with factory() as session:
        evidence = await session.get(EvidenceFile, evidence_id)
        assert evidence is not None
        assert evidence.sha256 == fingerprint(original)  # row never rewritten


async def test_runner_reports_missing_source_bytes_as_inconclusive_failure(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, key = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=PARAGRAPHS.encode(),
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    await asyncio.to_thread(storage.delete, key)
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=api_user.id
    )
    fake = FakeAI()
    job = await _run(database, storage, job_id, fake)

    assert job.status == "failed"
    assert dict(job.result_summary or {})["error_code"] == CODE_INTEGRITY_SOURCE_MISSING
    assert fake.extract_calls == []


async def test_runner_fails_explicitly_when_model_layer_is_down(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=b"single paragraph evidence",
        name="note.txt",
        content_type="text/plain",
        format_="txt",
    )
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=api_user.id
    )
    fake = FakeAI(error=RuntimeError("simulated model outage"))
    job = await _run(database, storage, job_id, fake)

    assert job.status == "failed"
    summary = dict(job.result_summary or {})
    assert summary["error_code"] == CODE_EXTRACTION_FAILED
    assert summary["units_failed"] == 1
    assert "simulated model outage" in (job.error or "")


async def test_runner_partial_state_is_accurate_when_a_later_record_fails(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=PARAGRAPHS.encode(),
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=api_user.id
    )
    fake = FakeAI(
        replies=[extraction_reply(person_names=["Officer Nanda"])],
        error=RuntimeError("model died mid-run"),
        fail_after=1,
    )
    job = await _run(database, storage, job_id, fake)

    assert job.status == "partial"  # first record extracted, second honest-failed
    summary = dict(job.result_summary or {})
    assert summary["artifacts_created"] == 1
    assert summary["units_failed"] == 1
    assert "model died mid-run" in (job.error or "")
    assert await _count(database, DerivedArtifact, _owned_case) == 1


async def test_runner_timeout_never_succeeds_and_stops_before_any_model_call(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=PARAGRAPHS.encode(),
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    job_id = await _make_job(
        database,
        case_id=_owned_case,
        evidence_id=evidence_id,
        actor_id=api_user.id,
        timeout_seconds=0,  # already past budget when running starts
    )
    fake = FakeAI()
    job = await _run(database, storage, job_id, fake)

    assert job.status == "failed"
    assert "timed out" in (job.error or "")
    assert fake.extract_calls == []
    factory = database.session_factory()
    async with factory() as session:
        audit = await session.execute(
            select(AuditLog).where(AuditLog.action == "extraction.timed_out")
        )
        assert audit.scalars().first() is not None


async def test_runner_canceled_job_stays_canceled_and_cannot_transition_to_success(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=PARAGRAPHS.encode(),
        name="access-log.txt",
        content_type="text/plain",
        format_="txt",
    )
    job_id = await _make_job(
        database,
        case_id=_owned_case,
        evidence_id=evidence_id,
        actor_id=api_user.id,
        cancel_requested=True,
    )
    fake = FakeAI()
    job = await _run(database, storage, job_id, fake)

    assert job.status == "canceled"  # canceled, never "succeeded"
    assert fake.extract_calls == []
    assert await _count(database, DerivedArtifact, _owned_case) == 0

    factory = database.session_factory()
    async with factory() as session:
        row = await session.get(AnalysisJob, job_id)
        assert row is not None
        # The state machine refuses to launder a canceled job into success.
        try:
            jobs_svc.transition(row, "succeeded")
        except jobs_svc.InvalidJobTransition:
            pass
        else:  # pragma: no cover - guard must hold
            raise AssertionError("canceled job transitioned to succeeded")
        audit = await session.execute(
            select(AuditLog).where(AuditLog.action == "extraction.canceled")
        )
        assert audit.scalars().first() is not None


async def test_runner_requires_ocr_for_textless_pdf_and_says_so(
    database: Database,
    storage: Storage,
    api_user,
    _owned_case: uuid.UUID,
) -> None:
    doc = FPDF()
    doc.add_page()  # no text cells: an image-only style page
    pdf_bytes = bytes(doc.output())
    evidence_id, _ = await _seed_evidence(
        database,
        storage,
        _owned_case,
        data=pdf_bytes,
        name="scan.pdf",
        content_type="application/pdf",
        format_="pdf",
    )
    job_id = await _make_job(
        database, case_id=_owned_case, evidence_id=evidence_id, actor_id=api_user.id
    )
    fake = FakeAI()
    job = await _run(database, storage, job_id, fake)

    assert job.status == "failed"
    summary = dict(job.result_summary or {})
    assert summary["error_code"] == CODE_OCR_REQUIRED
    assert "OCR" in (job.error or "")
    assert "no OCR engine" in (job.error or "")
    assert fake.extract_calls == []  # nothing is invented without a text layer

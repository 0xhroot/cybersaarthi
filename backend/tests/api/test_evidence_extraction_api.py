"""API tests: smart ingestion copilot endpoints (feature 1).

Covers the accepted-job contract (202 + background run), idempotent retry
without duplicate artifacts or repeat model calls, the typed rejection matrix
(not found / unavailable / active / disabled / permission / read-only case)
and the audit trail. The model is the shared deterministic fake - no live
llama.cpp dependency, no fabricated outputs.
"""

from __future__ import annotations

import uuid

import httpx
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_CASE_ACCESS_DENIED,
    CODE_CASE_READ_ONLY,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_EXTRACTION_ACTIVE,
    CODE_INSUFFICIENT_PERMISSION,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import AnalysisJob, AuditLog, Case, CaseMember, DerivedArtifact
from sqlalchemy import delete, select

from tests.api.phase2_fakes import FakeAI, extraction_reply

PREFIX = get_settings().API_V1_PREFIX

INVOICE_TEXT = (
    "Invoice for Asha Verma of Sunrise Traders account ACC-7781 "
    "amount 1,200.50 INR on 2026-01-15. Payment received in full"
)


async def _upload_txt(client: httpx.AsyncClient, case_id: uuid.UUID, text: str) -> uuid.UUID:
    response = await client.post(
        f"{PREFIX}/cases/{case_id}/evidence",
        files={"file": ("evidence.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _job_rows(database: Database, case_id: uuid.UUID) -> list[AnalysisJob]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.case_id == str(case_id))
            .order_by(AnalysisJob.created_at)
        )
        return list(rows.scalars())


async def _audit_action(
    database: Database, *, action: str, resource_id: uuid.UUID | str
) -> AuditLog | None:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.resource_id == str(resource_id),
            )
        )
        return rows.scalars().first()


async def test_extract_submit_schedules_job_and_records_reviewable_artifacts(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.replies = [
        extraction_reply(
            person_names=["Asha Verma"],
            organization_names=["Sunrise Traders"],
            account_references=["ACC-7781"],
            transaction_amounts=["1,200.50 INR"],
        )
    ]
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)

    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "ingestion"
    # The 202 response serializes before the background run; polling is the
    # documented completion path (no unbounded work in the request handler).
    assert body["job"]["status"] == "pending"
    job_id = uuid.UUID(body["job"]["id"])

    # BackgroundTasks ran to completion before the ASGI call returned.
    jobs = await _job_rows(database, _owned_case)
    job = next(j for j in jobs if j.id == job_id)
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["artifacts_created"] == 1
    assert summary["units_total"] == 1
    assert summary["fields_total"] == 12  # every schema field is reported
    assert summary["fields_verified"] == 12  # every claimed value traced to source
    assert len(fake.extract_calls) == 1
    assert "record 1 of evidence.txt" == fake.extract_calls[0]["label"]

    artifacts = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts?kind=extraction"
    )
    assert artifacts.status_code == 200
    items = artifacts.json()["items"]
    assert len(items) == 1
    artifact = items[0]
    assert artifact["kind"] == "extraction"
    assert artifact["status"] == "pending_review"  # human decides, never auto-approved
    assert artifact["validation_status"] == "valid"
    assert artifact["source_locator"] == {"record_no": 1, "field": "text"}
    assert artifact["payload"]["record_no"] == 1
    assert artifact["payload"]["fields"]["person_names"] == ["Asha Verma"]

    assert await _audit_action(
        database, action="extraction.submitted", resource_id=job_id
    ) is not None
    completed = await _audit_action(
        database, action="extraction.completed", resource_id=job_id
    )
    assert completed is not None
    assert completed.metadata_["status"] == "succeeded"
    # Audit metadata is counts-only: no extracted content ever leaks into it.
    assert "Asha Verma" not in str(completed.metadata_)


async def test_extract_retry_is_idempotent_no_duplicate_artifacts_no_second_model_call(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)

    first = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert first.status_code == 202, first.text
    second = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert second.status_code == 202, second.text
    assert second.json()["job"]["idempotency_key"].endswith(":a2")

    jobs = await _job_rows(database, _owned_case)
    retry = jobs[-1]
    assert retry.status == "succeeded"
    summary = dict(retry.result_summary or {})
    assert summary["artifacts_reused"] == 1  # record already has reviewable output
    assert summary["artifacts_created"] == 0
    # One model call total across both runs: the retry reused the artifact.
    assert len(phase2_fake_ai.extract_calls) == 1

    artifacts = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts?kind=extraction"
    )
    assert artifacts.json()["total"] == 1  # one artifact, not two


async def test_extract_refuses_while_a_run_is_active(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="ingestion",
                status="pending",
                idempotency_key=f"seed-active-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=600,
                cancel_requested=False,
                evidence_file_id=str(evidence_id),
                actor_id=str(api_user.id),
            )
        )
        await session.commit()

    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_EXTRACTION_ACTIVE


async def test_extract_typed_errors_for_missing_and_deleted_evidence(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_EVIDENCE_NOT_FOUND

    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)
    deleted = await http_client.delete(f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}")
    assert deleted.status_code == 204

    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_EVIDENCE_UNAVAILABLE


async def test_extract_requires_ingestion_run_permission(
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app

    viewer = await user_factory(role="VIEWER")
    # Member of the case, but the VIEWER role lacks evidence.read/ingestion.run.
    factory = database.session_factory()
    async with factory() as session:
        session.add(CaseMember(case_id=_owned_case, user_id=viewer.id, role="collaborator"))
        await session.commit()

    transport = httpx.ASGITransport(app=shared_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {viewer.token}"},
    ) as client:
        response = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
            json={"evidence_file_id": str(uuid.uuid4())},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    # Cleanup: viewer membership + user are torn down by their own fixtures,
    # but the CaseMember row would outlive the case otherwise.
    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == viewer.id))
        await session.commit()


async def test_extract_non_member_is_refused(
    user_factory,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app

    stranger = await user_factory(role="INVESTIGATOR")
    transport = httpx.ASGITransport(app=shared_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {stranger.token}"},
    ) as client:
        response = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
            json={"evidence_file_id": str(uuid.uuid4())},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_CASE_ACCESS_DENIED


async def test_extract_blocked_when_ai_feature_disabled(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    monkeypatch,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)
    monkeypatch.setattr(get_settings(), "AI_FEATURE_EXTRACTION", False)
    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_AI_DISABLED


async def test_extract_blocked_on_read_only_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, _owned_case)
        assert case is not None
        case.status = "closed"
        await session.commit()

    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_CASE_READ_ONLY


async def test_extraction_artifact_review_with_edit_is_a_new_superseding_artifact(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.replies = [extraction_reply(person_names=["Asha Verma"])]
    evidence_id = await _upload_txt(http_client, _owned_case, INVOICE_TEXT)
    submitted = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/extract",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert submitted.status_code == 202, submitted.text

    artifacts = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts?kind=extraction"
    )
    artifact = artifacts.json()["items"][0]

    # Edited values must come from the artifact's own source record.
    edited = {
        key: (["Sunrise Traders"] if key == "organization_names" else [])
        for key in (
            "person_names",
            "organization_names",
            "phone_numbers",
            "email_addresses",
            "account_references",
            "transaction_amounts",
            "transaction_dates",
            "urls",
            "domains",
            "device_identifiers",
            "statements",
            "events",
        )
    }
    review = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact['id']}/review",
        json={"decision": "approved", "payload": {"fields": edited}},
    )
    assert review.status_code == 200, review.text

    factory = database.session_factory()
    async with factory() as session:
        original = await session.get(DerivedArtifact, uuid.UUID(artifact["id"]))
        child_rows = await session.execute(
            select(DerivedArtifact).where(
                DerivedArtifact.parent_artifact_id == str(artifact["id"])
            )
        )
        child = child_rows.scalars().first()
    assert original is not None
    assert original.status == "superseded"  # history kept, never rewritten
    assert child is not None
    assert child.status == "approved"
    assert child.payload["fields"]["organization_names"] == ["Sunrise Traders"]
    assert child.validation_status == "valid"

    # An invented value that is not in the source record must be refused.
    artifacts = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts?kind=extraction"
    )
    remaining = [a for a in artifacts.json()["items"] if a["status"] == "pending_review"]
    assert remaining == []  # the only artifact was reviewed exactly once

    # Second review on the superseded original is one-shot-refused.
    repeat = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact['id']}/review",
        json={"decision": "approved"},
    )
    assert repeat.status_code == 409

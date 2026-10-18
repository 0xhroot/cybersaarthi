"""API tests: integrity verification & chain-of-custody auditor (feature 9).

Covers deterministic verification outcomes (match / mismatch / missing source
as distinct 200 statuses - never fabricated green), append-only custody
event recording with typed policy refusals, the custody-audit job including
finding dedupe across runs, the facts-only AI explanation surface and the
cancellation contract. Hash state is driven by real MinIO object bytes.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_ARTIFACT_NOT_FOUND,
    CODE_CASE_ACCESS_DENIED,
    CODE_CASE_READ_ONLY,
    CODE_CUSTODY_AUDIT_ACTIVE,
    CODE_CUSTODY_FIELD_REQUIRED,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_INVALID_PAYLOAD,
    CODE_JOB_NOT_FOUND,
    CODE_JOB_TERMINAL,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.db.storage import Storage
from app.main import app
from app.models import AnalysisJob, AuditLog, Case, CaseMember, EvidenceFile
from sqlalchemy import select

from tests.api.phase2_fakes import FakeAI

PREFIX = get_settings().API_V1_PREFIX

LOG_TEXT = "Secure access log entry for server rack seven at 2026-01-10"


async def _upload_txt(client: httpx.AsyncClient, case_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    response = await client.post(
        f"{PREFIX}/cases/{case_id}/evidence",
        files={"file": ("integrity-log.txt", LOG_TEXT.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return uuid.UUID(body["id"]), body["sha256"]


async def _verify(client: httpx.AsyncClient, case_id: uuid.UUID, evidence_id: uuid.UUID):
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-integrity/verify",
        json={"evidence_file_id": str(evidence_id)},
    )


async def _recorded_artifacts(client: httpx.AsyncClient, case_id: uuid.UUID) -> list[dict]:
    response = await client.get(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/artifacts?kind=custody_finding"
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _past_iso(hours: float = 3.0) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


# -- deterministic verification ------------------------------------------------


async def test_verify_match_records_deterministic_fact_not_a_review_queue(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, sha = await _upload_txt(http_client, _owned_case)
    response = await _verify(http_client, _owned_case, evidence_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "match"
    assert body["algorithm"] == "sha256"
    assert body["expected_sha256"] == sha
    assert body["calculated_sha256"] == sha
    assert body["object_present"] is True
    assert body["file_size_bytes"] == len(LOG_TEXT.encode())

    artifacts = await _recorded_artifacts(http_client, _owned_case)
    verification = [a for a in artifacts if (a["payload"] or {}).get("type") == "hash_verification"]
    assert len(verification) == 1
    fact = verification[0]
    assert fact["status"] == "recorded"  # a fact, never queued for approval
    assert fact["origin"] == "deterministic"
    assert fact["payload"]["status"] == "match"
    assert fact["id"] == body["artifact_id"]

    factory = database.session_factory()
    async with factory() as session:
        audit = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "integrity.verified",
                        AuditLog.resource_id == str(evidence_id),
                    )
                )
            )
            .scalars()
            .first()
        )
    assert audit is not None
    assert audit.metadata_["status"] == "match"


async def test_verify_mismatch_when_object_bytes_change(
    http_client: httpx.AsyncClient,
    database: Database,
    storage: Storage,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, sha = await _upload_txt(http_client, _owned_case)
    factory = database.session_factory()
    async with factory() as session:
        evidence = await session.get(EvidenceFile, evidence_id)
        assert evidence is not None
        key = evidence.stored_key
    # Simulated storage-level tampering; the evidence row keeps its hash.
    await asyncio.to_thread(storage.upload, key, b"contents swapped after upload", "text/plain")
    try:
        response = await _verify(http_client, _owned_case, evidence_id)
    finally:
        await asyncio.to_thread(storage.upload, key, LOG_TEXT.encode(), "text/plain")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "mismatch"  # explicit, typed - not an exception
    assert body["expected_sha256"] == sha
    assert body["calculated_sha256"] != sha

    artifacts = await _recorded_artifacts(http_client, _owned_case)
    mismatch = [
        a
        for a in artifacts
        if (a["payload"] or {}).get("type") == "hash_verification"
        and (a["payload"] or {}).get("status") == "mismatch"
    ]
    assert len(mismatch) == 1


async def test_verify_missing_source_is_inconclusive_never_a_pass(
    http_client: httpx.AsyncClient,
    storage: Storage,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    factory = database.session_factory()
    async with factory() as session:
        evidence = await session.get(EvidenceFile, evidence_id)
        assert evidence is not None
        key = evidence.stored_key
    await asyncio.to_thread(storage.delete, key)

    response = await _verify(http_client, _owned_case, evidence_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "missing_source"
    assert body["object_present"] is False
    assert body["calculated_sha256"] is None  # explicit unknown, not a green check
    assert body["file_size_bytes"] is None

    artifacts = await _recorded_artifacts(http_client, _owned_case)
    fact = next(a for a in artifacts if (a["payload"] or {}).get("type") == "hash_verification")
    assert fact["payload"]["status"] == "missing_source"
    assert fact["payload"]["calculated_sha256"] is None


async def test_verify_typed_errors_for_missing_and_deleted_evidence(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
) -> None:
    unknown = await _verify(http_client, _owned_case, uuid.uuid4())
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_EVIDENCE_NOT_FOUND

    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    deleted = await http_client.delete(f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}")
    assert deleted.status_code == 204
    response = await _verify(http_client, _owned_case, evidence_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_EVIDENCE_UNAVAILABLE


# -- custody events (append-only, policy-validated) -----------------------------


async def test_custody_event_policy_validation_and_chronology(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, sha = await _upload_txt(http_client, _owned_case)
    events_url = f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody-events"

    missing_party = await http_client.post(
        events_url, json={"event_type": "collected", "occurred_at": await _past_iso()}
    )
    assert missing_party.status_code == 422
    assert missing_party.json()["error"]["code"] == CODE_CUSTODY_FIELD_REQUIRED

    naive = await http_client.post(
        events_url,
        json={"event_type": "collected", "occurred_at": "2026-03-01T10:00:00"},
    )
    assert naive.status_code == 422
    assert naive.json()["error"]["code"] == CODE_INVALID_PAYLOAD

    future = await http_client.post(
        events_url,
        json={
            "event_type": "collected",
            "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "collector": "Officer A",
        },
    )
    assert future.status_code == 422
    assert future.json()["error"]["code"] == CODE_INVALID_PAYLOAD

    bad_digest = await http_client.post(
        events_url,
        json={
            "event_type": "collected",
            "occurred_at": await _past_iso(),
            "collector": "Officer A",
            "recorded_sha256": "not-a-sha256",
        },
    )
    assert bad_digest.status_code == 422
    assert bad_digest.json()["error"]["code"] == CODE_INVALID_PAYLOAD

    created = await http_client.post(
        events_url,
        json={
            "event_type": "collected",
            "occurred_at": await _past_iso(),
            "collector": "Officer A",
            "location": "Rack room B",
        },
    )
    assert created.status_code == 201, created.text
    event = created.json()
    assert event["event_type"] == "collected"
    assert event["recorded_at"]  # documentation time recorded server-side

    chronology = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody"
    )
    assert chronology.status_code == 200, chronology.text
    body = chronology.json()
    assert body["event_count"] == 1
    assert body["events"][0]["event_type"] == "collected"
    assert body["sha256"] == sha
    assert body["algorithm"] == "sha256"
    assert body["deleted_at"] is None

    factory = database.session_factory()
    async with factory() as session:
        audit = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "custody.event_recorded",
                        AuditLog.resource_id == str(evidence_id),
                    )
                )
            )
            .scalars()
            .first()
        )
    assert audit is not None
    assert audit.metadata_["event_type"] == "collected"


async def test_custody_event_permission_and_case_boundaries(
    http_client: httpx.AsyncClient,
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    events_url = f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody-events"

    # VIEWER role lacks evidence.upload regardless of membership.
    viewer = await user_factory(role="VIEWER")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {viewer.token}"},
    ) as client:
        denied = await client.post(
            events_url,
            json={"event_type": "collected", "occurred_at": await _past_iso()},
        )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    # Non-member investigator: read boundary on the chronology.
    stranger = await user_factory(role="INVESTIGATOR")
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {stranger.token}"},
    ) as client:
        blocked = await client.get(f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody")
        post_blocked = await client.post(
            events_url,
            json={"event_type": "collected", "occurred_at": await _past_iso()},
        )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == CODE_CASE_ACCESS_DENIED
    assert post_blocked.status_code == 403

    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence/{uuid.uuid4()}/custody-events",
        json={"event_type": "collected", "occurred_at": await _past_iso()},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_EVIDENCE_NOT_FOUND


async def test_chronology_of_deleted_evidence_reports_deletion_explicitly(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    created = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody-events",
        json={
            "event_type": "collected",
            "occurred_at": await _past_iso(),
            "collector": "Officer A",
        },
    )
    assert created.status_code == 201, created.text
    deleted = await http_client.delete(f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}")
    assert deleted.status_code == 204

    chronology = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}/custody"
    )
    assert chronology.status_code == 200, chronology.text
    body = chronology.json()
    assert body["deleted_at"] is not None  # history survives; deletion is visible
    assert body["event_count"] == 1


# -- custody audit job ----------------------------------------------------------


async def _record_transferred(client: httpx.AsyncClient, case_id: uuid.UUID, eid: uuid.UUID):
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence/{eid}/custody-events",
        json={
            "event_type": "transferred",
            "occurred_at": await _past_iso(),
            "transferor": "Officer A",
            "recipient": "Forensics Lab B",
        },
    )


async def _audit(client: httpx.AsyncClient, case_id: uuid.UUID, evidence_id=None):
    payload = {} if evidence_id is None else {"evidence_file_id": str(evidence_id)}
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-integrity/custody-audit", json=payload
    )


async def test_custody_audit_clean_case_yields_zero_findings(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    """False-positive guard end-to-end: documented, hash-matching evidence
    with no custody events must produce no findings at all."""
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    response = await _audit(http_client, _owned_case, evidence_id)
    assert response.status_code == 202, response.text

    factory = database.session_factory()
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.case_id == str(_owned_case),
                    AnalysisJob.feature == "custody",
                )
            )
        ).scalars()
        job = list(jobs)[0]
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["evidence_checked"] == 1
    assert summary["hash_match"] == 1
    assert summary["findings_new"] == 0
    assert summary["findings_existing"] == 0
    assert await _recorded_artifacts(http_client, _owned_case) == []


async def test_custody_audit_flags_unacknowledged_transfer_and_dedupes_reruns(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    recorded = await _record_transferred(http_client, _owned_case, evidence_id)
    assert recorded.status_code == 201, recorded.text

    first = await _audit(http_client, _owned_case, evidence_id)
    assert first.status_code == 202, first.text

    factory = database.session_factory()
    async with factory() as session:
        jobs = list(
            (
                await session.execute(
                    select(AnalysisJob).where(
                        AnalysisJob.case_id == str(_owned_case),
                        AnalysisJob.feature == "custody",
                    )
                )
            ).scalars()
        )
    job = jobs[0]
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["findings_new"] == 1  # the unacknowledged hand-off
    assert summary["findings_existing"] == 0

    artifacts = await _recorded_artifacts(http_client, _owned_case)
    assert len(artifacts) == 1
    finding = artifacts[0]
    assert finding["status"] == "pending_review"  # a finding awaits a human
    assert finding["payload"]["rule"] == "custody.unacknowledged_transfer"
    assert finding["payload"]["severity"] == "warning"
    assert finding["evidence_file_id"] == str(evidence_id)
    assert finding["origin"] == "deterministic"

    # Re-running the audit converges on the same finding: no duplicates.
    second = await _audit(http_client, _owned_case, evidence_id)
    assert second.status_code == 202, second.text
    async with factory() as session:
        rerun = list(
            (
                await session.execute(
                    select(AnalysisJob)
                    .where(
                        AnalysisJob.case_id == str(_owned_case),
                        AnalysisJob.feature == "custody",
                    )
                    .order_by(AnalysisJob.created_at)
                )
            ).scalars()
        )[-1]
    assert rerun.status == "succeeded"
    rerun_summary = dict(rerun.result_summary or {})
    assert rerun_summary["findings_new"] == 0
    assert rerun_summary["findings_existing"] == 1
    assert len(await _recorded_artifacts(http_client, _owned_case)) == 1


async def test_custody_audit_refuses_while_one_is_active(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="custody",
                status="running",
                idempotency_key=f"seed-custody-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=300,
                cancel_requested=False,
                actor_id=str(api_user.id),
            )
        )
        await session.commit()
    response = await _audit(http_client, _owned_case)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_CUSTODY_AUDIT_ACTIVE


async def test_custody_job_cancellation_contract(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
) -> None:
    factory = database.session_factory()

    async def _seed(status: str, feature: str = "custody") -> uuid.UUID:
        async with factory() as session:
            job = AnalysisJob(
                case_id=str(_owned_case),
                feature=feature,
                status=status,
                idempotency_key=f"seed-cancel-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=300,
                cancel_requested=False,
                actor_id=str(api_user.id),
            )
            session.add(job)
            await session.commit()
            return job.id

    pending_id = await _seed("pending")
    canceled = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{pending_id}/cancel"
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["cancel_requested"] is True

    terminal_id = await _seed("canceled")
    again = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{terminal_id}/cancel"
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == CODE_JOB_TERMINAL

    # Phase 3 made entity_resolution/timeline/contradiction cancelable too, and
    # phase 4 added financial_flow and cross_case; a genuinely uncovered
    # feature (triage) still drives the 404 contract check.
    wrong_feature = await _seed("pending", feature="triage")
    refused = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{wrong_feature}/cancel"
    )
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == CODE_JOB_NOT_FOUND

    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{uuid.uuid4()}/cancel"
    )
    assert unknown.status_code == 404


# -- AI explanation (facts-only) ------------------------------------------------


async def test_explain_records_narration_without_certifying_anything(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    await _record_transferred(http_client, _owned_case, evidence_id)
    audit = await _audit(http_client, _owned_case, evidence_id)
    assert audit.status_code == 202, audit.text

    artifacts = await _recorded_artifacts(http_client, _owned_case)
    finding = artifacts[0]
    response = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{finding['id']}/explain"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rule"] == "custody.unacknowledged_transfer"
    assert body["text"] == phase2_fake_ai.explain_text

    explanation = body["explanation_artifact"]
    assert explanation["status"] == "recorded"  # never queued for approval
    assert explanation["validation_status"] == "flagged"  # amber: unverified AI text
    assert explanation["validation_errors"][0]["code"] == "ai_unverified"
    assert explanation["parent_artifact_id"] == finding["id"]
    assert explanation["payload"]["type"] == "ai_explanation"
    assert explanation["payload"]["for_artifact_id"] == finding["id"]

    # The model received the finding's facts only - nothing else.
    facts = phase2_fake_ai.explain_calls[0]
    assert facts["rule"] == "custody.unacknowledged_transfer"
    assert set(facts) <= {
        "rule",
        "severity",
        "observed",
        "missing",
        "message",
        "event_ids",
        "rule_set_version",
        "policy_version",
        "evidence_id",
    }

    factory = database.session_factory()
    async with factory() as session:
        logged = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "custody.explanation_generated",
                        AuditLog.resource_id == str(explanation["id"]),
                    )
                )
            )
            .scalars()
            .first()
        )
    assert logged is not None


async def test_explain_refuses_non_findings_and_disabled_ai(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    monkeypatch,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id, _ = await _upload_txt(http_client, _owned_case)
    verified = await _verify(http_client, _owned_case, evidence_id)
    assert verified.status_code == 200, verified.text
    fact_id = verified.json()["artifact_id"]

    wrong_kind = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{fact_id}/explain"
    )
    assert wrong_kind.status_code == 422  # hash results are facts, not findings
    assert wrong_kind.json()["error"]["code"] == CODE_ARTIFACT_KIND_UNSUPPORTED

    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{uuid.uuid4()}/explain"
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_ARTIFACT_NOT_FOUND

    # Find the finding artifact for the disabled-feature check.
    await _record_transferred(http_client, _owned_case, evidence_id)
    audit = await _audit(http_client, _owned_case, evidence_id)
    assert audit.status_code == 202, audit.text
    findings = [
        a
        for a in await _recorded_artifacts(http_client, _owned_case)
        if (a["payload"] or {}).get("type") == "custody_finding"
    ]
    assert len(findings) == 1
    finding = findings[0]

    monkeypatch.setattr(get_settings(), "AI_FEATURE_INTEGRITY_EXPLAIN", False)
    disabled = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{finding['id']}/explain"
    )
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == CODE_AI_DISABLED


# -- lifecycle guard -------------------------------------------------------------


async def test_custody_audit_blocked_on_read_only_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, _owned_case)
        assert case is not None
        case.status = "closed"
        await session.commit()

    response = await _audit(http_client, _owned_case)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_CASE_READ_ONLY


async def test_custody_audit_and_verify_require_ingestion_run_permission(
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
) -> None:
    viewer = await user_factory(role="VIEWER")
    factory = database.session_factory()
    async with factory() as session:
        session.add(CaseMember(case_id=_owned_case, user_id=viewer.id, role="collaborator"))
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {viewer.token}"},
    ) as client:
        audit = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-integrity/custody-audit", json={}
        )
        verify = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-integrity/verify",
            json={"evidence_file_id": str(uuid.uuid4())},
        )
    assert audit.status_code == 403
    assert audit.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION
    assert verify.status_code == 403
    assert verify.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

"""API tests: digital-forensics triage endpoints (feature 8).

Covers the accepted-job contract (202 + background run), deterministic
observation recording with record locators, hash-manifest re-verification
against stored object bytes, the typed no-structure refusal, honest partial
on model outage, retry dedupe reporting, the typed rejection matrix
(missing/deleted/active/disabled/permission/non-member/read-only) and
cancellation producing no artifacts. The model is the shared deterministic
fake - no live llama.cpp dependency.
"""

from __future__ import annotations

import hashlib
import uuid

import httpx
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_CASE_ACCESS_DENIED,
    CODE_CASE_READ_ONLY,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_TRIAGE_ACTIVE,
    CODE_TRIAGE_UNSUPPORTED_CONTENT,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import AnalysisJob, AuditLog, Case, CaseMember, DerivedArtifact
from sqlalchemy import delete, select

from tests.api.phase2_fakes import FakeAI, triage_reply

PREFIX = get_settings().API_V1_PREFIX

TRIAGE_URLS_TXT = (
    "Visit log:\n"
    "http://paypal.com@evil.test/login\n"
    "https://xn--pypal-4ve.com/verify/session\n"
    "https://cdn.example.org:8080/asset/bundle.js\n"
)
PROSE = (
    "I ordered a laptop from an online seller on the marketplace. "
    "The seller stopped replying after I transferred the amount from my "
    "savings account. I want to know what can be done about the pending "
    "delivery and my money."
)
EXPECTED_RULES = [
    "triage.url.userinfo",
    "triage.url.punycode",
    "triage.url.nonstandard_port",
]


async def _upload_bytes(
    client: httpx.AsyncClient,
    case_id: uuid.UUID,
    data: bytes,
    name: str,
) -> uuid.UUID:
    response = await client.post(
        f"{PREFIX}/cases/{case_id}/evidence",
        files={"file": (name, data, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _upload_txt(
    client: httpx.AsyncClient,
    case_id: uuid.UUID,
    text: str,
    name: str = "evidence.txt",
) -> uuid.UUID:
    return await _upload_bytes(client, case_id, text.encode(), name)


async def _job_rows(database: Database, case_id: uuid.UUID) -> list[AnalysisJob]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.case_id == str(case_id))
            .order_by(AnalysisJob.created_at)
        )
        return list(rows.scalars())


async def _artifacts(client: httpx.AsyncClient, case_id: uuid.UUID, kind: str) -> list[dict]:
    response = await client.get(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/artifacts?kind={kind}"
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


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


async def _submit_triage(client: httpx.AsyncClient, case_id: uuid.UUID, evidence: uuid.UUID):
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/triage",
        json={"evidence_file_id": str(evidence)},
    )


async def test_triage_submit_records_observation_artifact(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.triage_explain_replies = [triage_reply("three structural url findings")]
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT, name="nav.txt")

    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "triage"
    assert body["job"]["status"] == "pending"
    job_id = uuid.UUID(body["job"]["id"])

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["urls_analyzed"] == 3
    assert summary["observations_total"] == 3
    assert summary["artifacts_created"] == 1
    assert summary["units_failed"] == 0

    artifacts = await _artifacts(http_client, _owned_case, "triage_observation")
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["status"] == "pending_review"
    assert artifact["origin"] == "llm"
    assert artifact["validation_status"] == "valid"
    assert artifact["model_profile"] == "triage"
    assert artifact["prompt_version"] == "1.0.0"
    assert artifact["source_locator"] == {"scope": "evidence_file", "records_scanned": 1}
    assert str(artifact["evidence_file_id"]) == str(evidence_id)

    payload = artifact["payload"]
    assert payload["format_profile"]["urls_found"] == 3
    assert payload["format_profile"]["records_scanned"] == 1
    assert [obs["rule"] for obs in payload["observations"]] == EXPECTED_RULES
    assert all(obs["locator"] == {"record_no": 1} for obs in payload["observations"])
    assert [u["host"] for u in payload["fields"]["urls"]] == [
        "evil.test",
        "xn--pypal-4ve.com",
        "cdn.example.org",
    ]
    assert payload["fields"]["manifest"] is None  # no manifest in this evidence
    assert payload["explanation"]["summary"] == "three structural url findings"
    assert payload["explanation_failed"] is False
    assert "no URL was fetched" in payload["analysis_scope"]
    assert payload["rules_version"] == "1.0.0"

    # the model received only recorded observations + bounded excerpts
    assert len(fake.triage_explain_calls) == 1
    seen = fake.triage_explain_calls[0]
    assert "paypal.com@evil.test" in str(seen)
    assert seen["format_profile"]["urls_found"] == 3

    # audits: submitted carries identifiers only; completed carries counts only
    submitted = await _audit_action(database, action="triage.submitted", resource_id=job_id)
    assert submitted is not None
    assert dict(submitted.metadata_) == {"evidence_file_id": str(evidence_id), "duplicate": False}
    completed = await _audit_action(database, action="triage.completed", resource_id=job_id)
    assert completed is not None
    completed_meta = dict(completed.metadata_)
    assert completed_meta["observations_total"] == 3
    assert completed_meta["artifacts_created"] == 1
    assert all(isinstance(value, int) for value in completed_meta.values())


async def test_triage_manifest_verdicts_against_stored_bytes(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    target = b"chain of custody target bytes"
    victim = b"unrelated victim bytes"
    sha_target = hashlib.sha256(target).hexdigest()
    sha_victim = hashlib.sha256(victim).hexdigest()
    await _upload_bytes(http_client, _owned_case, target, name="target.txt")
    await _upload_bytes(http_client, _owned_case, victim, name="victim.txt")
    manifest_text = (
        f"target.txt {sha_target}\n\n"  # matches stored bytes
        f"victim.txt {sha_target}\n\n"  # victim exists but its bytes differ
        f"absent.txt {sha_target}\n\n"  # no such file in the case
    )
    manifest_id = await _upload_bytes(
        http_client, _owned_case, manifest_text.encode(), "manifest.txt"
    )

    response = await _submit_triage(http_client, _owned_case, manifest_id)
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "succeeded", job.error
    summary = dict(job.result_summary or {})
    assert summary["manifest_entries_verified"] == 3
    assert summary["observations_total"] == 2  # mismatch + missing, never a verdict

    artifacts = await _artifacts(http_client, _owned_case, "triage_observation")
    assert len(artifacts) == 1
    payload = artifacts[0]["payload"]
    verdicts = {row["filename"]: row for row in payload["fields"]["manifest"]}
    assert verdicts["target.txt"]["verdict"] == "match"
    assert verdicts["target.txt"]["computed_sha256"] == sha_target
    assert verdicts["victim.txt"]["verdict"] == "mismatch"
    assert verdicts["victim.txt"]["computed_sha256"] == sha_victim
    assert verdicts["absent.txt"]["verdict"] == "missing"
    assert verdicts["absent.txt"]["computed_sha256"] is None

    rules = [obs["rule"] for obs in payload["observations"]]
    assert rules == ["triage.manifest.hash_mismatch", "triage.manifest.entry_missing"]
    severities = [obs["severity"] for obs in payload["observations"]]
    assert severities == ["high", "medium"]
    # verbatim recomputed hashes are recorded; the model added nothing
    assert payload["format_profile"]["manifest_entries"] == 3
    assert phase2_fake_ai.triage_explain_calls  # explanation still ran, over recorded facts


async def test_triage_unsupported_prose_fails_with_typed_error(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, PROSE, name="prose.txt")
    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    assert jobs[-1].status == "failed"
    assert CODE_TRIAGE_UNSUPPORTED_CONTENT in (jobs[-1].error or "")
    artifacts = await _artifacts(http_client, _owned_case, "triage_observation")
    assert artifacts == []  # never an empty success
    assert phase2_fake_ai.triage_explain_calls == []  # no model call before the refusal


async def test_triage_refuses_while_a_run_is_active(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="triage",
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

    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_TRIAGE_ACTIVE


async def test_triage_typed_errors_for_missing_and_deleted_evidence(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    unknown = await _submit_triage(http_client, _owned_case, uuid.uuid4())
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_EVIDENCE_NOT_FOUND

    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)
    deleted = await http_client.delete(f"{PREFIX}/cases/{_owned_case}/evidence/{evidence_id}")
    assert deleted.status_code == 204

    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_EVIDENCE_UNAVAILABLE


async def test_triage_model_outage_is_reported_as_partial(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.error = RuntimeError("model overloaded")
    fake.fail_after = 0  # the single explanation call raises
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)

    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "partial"  # an outage is never a clean success
    assert "1 unit(s) failed" in (job.error or "")
    summary = dict(job.result_summary or {})
    assert summary["units_failed"] == 1
    assert summary["explanation_failed"] == 1
    assert summary["artifacts_created"] == 1  # deterministic observations kept

    artifacts = await _artifacts(http_client, _owned_case, "triage_observation")
    assert len(artifacts) == 1
    payload = artifacts[0]["payload"]
    assert [obs["rule"] for obs in payload["observations"]] == EXPECTED_RULES
    assert payload["explanation"] is None
    assert payload["explanation_failed"] is True
    assert "model call failed" in payload["explanation_error"]
    assert artifacts[0]["validation_status"] == "flagged"
    assert any(
        issue.get("code") == "model_call_failed" for issue in artifacts[0]["validation_errors"]
    )


async def test_triage_retry_dedupes_identical_artifact_and_reports_reuse(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)

    first = await _submit_triage(http_client, _owned_case, evidence_id)
    assert first.status_code == 202, first.text
    second = await _submit_triage(http_client, _owned_case, evidence_id)
    assert second.status_code == 202, second.text

    jobs = await _job_rows(database, _owned_case)
    assert len(jobs) == 2  # a new attempt runs, the artifact does not duplicate
    assert all(job.status == "succeeded" for job in jobs)
    retry_summary = dict(jobs[-1].result_summary or {})
    assert retry_summary["artifacts_reused"] == 1
    assert retry_summary["artifacts_created"] == 0

    artifacts = await _artifacts(http_client, _owned_case, "triage_observation")
    assert len(artifacts) == 1
    # honest: the explanation re-ran (stochastic model), the artifact deduped
    assert len(phase2_fake_ai.triage_explain_calls) == 2


async def test_triage_cancel_before_run_creates_no_artifacts(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app
    from app.services.forensic_triage import run_triage_job

    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)
    job_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                id=job_id,
                case_id=str(_owned_case),
                feature="triage",
                status="pending",
                idempotency_key=f"seed-cancel-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=600,
                cancel_requested=True,
                evidence_file_id=str(evidence_id),
                actor_id=str(api_user.id),
            )
        )
        await session.commit()

    await run_triage_job(shared_app, job_id)

    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        artifacts = (
            (
                await session.execute(
                    select(DerivedArtifact).where(DerivedArtifact.case_id == str(_owned_case))
                )
            )
            .scalars()
            .all()
        )
    assert job is not None
    assert job.status == "canceled"
    assert artifacts == []
    assert phase2_fake_ai.triage_explain_calls == []


async def test_triage_requires_ingestion_run_permission(
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app

    viewer = await user_factory(role="VIEWER")
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
        response = await _submit_triage(client, _owned_case, uuid.uuid4())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == viewer.id))
        await session.commit()


async def test_triage_non_member_is_refused(
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
        response = await _submit_triage(client, _owned_case, uuid.uuid4())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_CASE_ACCESS_DENIED


async def test_triage_anonymous_is_refused(
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app

    transport = httpx.ASGITransport(app=shared_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await _submit_triage(client, _owned_case, uuid.uuid4())
    assert response.status_code == 401


async def test_triage_blocked_when_ai_feature_disabled(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    monkeypatch,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)
    monkeypatch.setattr(get_settings(), "AI_FEATURE_TRIAGE", False)
    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_AI_DISABLED


async def test_triage_blocked_on_read_only_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    evidence_id = await _upload_txt(http_client, _owned_case, TRIAGE_URLS_TXT)
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, _owned_case)
        assert case is not None
        case.status = "closed"
        await session.commit()

    response = await _submit_triage(http_client, _owned_case, evidence_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_CASE_READ_ONLY

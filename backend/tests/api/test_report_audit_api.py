"""API tests: AI report auditor endpoints (feature 10, phase 6).

Covers the accepted-job contract (202 + background run), the deterministic
finding matrix (invalid citations, arithmetic, chronology, currency,
spans - recomputed from the stored payload), verbatim quote validation of
model assessments, honest failed/partial states on model outage, the typed
rejection matrix (source XOR, empty/oversized draft, message-mode refusals,
active duplicate, disabled, permission, non-member, read-only case), the
message-reference staleness contract, draft immutability, cancellation,
retry dedupe and the case-scoped list/detail surface. The model is the
shared deterministic fake - no live llama.cpp dependency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_CASE_ACCESS_DENIED,
    CODE_CASE_READ_ONLY,
    CODE_DRAFT_SOURCE_INVALID,
    CODE_DRAFT_TOO_LARGE,
    CODE_DRAFT_UNAVAILABLE,
    CODE_MESSAGE_NOT_REPORT_MODE,
    CODE_REPORT_AUDIT_ACTIVE,
    CODE_REPORT_AUDIT_FAILED,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import (
    AIConversation,
    AIMessage,
    AnalysisJob,
    AuditLog,
    Case,
    CaseMember,
    DerivedArtifact,
    EvidenceFile,
)
from app.models.analysis_job import ANALYSIS_JOB_FEATURES
from sqlalchemy import delete, select

from tests.api.phase2_fakes import FakeAI, claims_reply, support_reply

PREFIX = get_settings().API_V1_PREFIX

# Synthetic draft with planted, hand-derivable issues (order matters: the
# timeline-category claims are intentionally out of chronological order).
DRAFT = (
    "The seller was contacted on 2026-01-20. "
    "The account of Priya Sharma received ₹5,000 on 2026-01-10. "
    "The total of INR 12,000 and INR 8,000 is INR 18,000. "
    "The account balance is $5,000. "
    "The first transfer happened on 2026-01-05. "
    "The complaint was filed with the cyber cell."
)
EVIDENCE_TXT = (
    "bank feed entry: on 2026-01-10 ₹5,000 was credited to account "
    "99887766 of Priya Sharma per statement"
)

VALID_QUOTE = "₹5,000 was credited"


def _span(text: str) -> tuple[int, int]:
    start = DRAFT.index(text)
    return start, start + len(text)


def _matrix_claims(evidence_id: uuid.UUID) -> list[dict]:
    """Six claims: two deterministic-timeline, three numeric, one broken."""
    late = "The seller was contacted on 2026-01-20."
    received = "The account of Priya Sharma received ₹5,000 on 2026-01-10."
    total = "The total of INR 12,000 and INR 8,000 is INR 18,000."
    balance = "The account balance is $5,000."
    early = "The first transfer happened on 2026-01-05."
    late_start, late_end = _span(late)
    received_start, received_end = _span(received)
    total_start, total_end = _span(total)
    balance_start, balance_end = _span(balance)
    early_start, early_end = _span(early)
    return [
        {
            "claim_id": "c_late",
            "text": late,
            "char_start": late_start,
            "char_end": late_end,
            "category": "timeline",
            "cited_ids": [],
        },
        {
            "claim_id": "c_received",
            "text": received,
            "char_start": received_start,
            "char_end": received_end,
            "category": "factual_statement",
            "cited_ids": [f"evidence:{evidence_id}"],
        },
        {
            "claim_id": "c_total",
            "text": total,
            "char_start": total_start,
            "char_end": total_end,
            "category": "quantity",
            "cited_ids": [],
        },
        {
            "claim_id": "c_balance",
            "text": balance,
            "char_start": balance_start,
            "char_end": balance_end,
            "category": "quantity",
            "cited_ids": [],
        },
        {
            "claim_id": "c_early",
            "text": early,
            "char_start": early_start,
            "char_end": early_end,
            "category": "timeline",
            "cited_ids": [],
        },
        {
            # span does not reproduce the draft + cites an unknown id
            "claim_id": "c_broken",
            "text": "The seller vanished after the payment.",
            "char_start": 0,
            "char_end": 38,
            "category": "factual_statement",
            "cited_ids": [f"evidence:{uuid.uuid4()}"],
        },
    ]


async def _upload_ingest_txt(client: httpx.AsyncClient, case_id: uuid.UUID, text: str) -> uuid.UUID:
    response = await client.post(
        f"{PREFIX}/cases/{case_id}/evidence",
        files={"file": ("statement.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    evidence_id = uuid.UUID(response.json()["id"])
    ingest = await client.post(
        f"{PREFIX}/cases/{case_id}/ingest",
        json={"evidence_file_id": str(evidence_id)},
    )
    assert ingest.status_code in (200, 201, 202), ingest.text
    return evidence_id


async def _submit(client: httpx.AsyncClient, case_id: uuid.UUID, body: dict):
    return await client.post(f"{PREFIX}/cases/{case_id}/report-audits", json=body)


async def _job_rows(database: Database, case_id: uuid.UUID) -> list[AnalysisJob]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.case_id == str(case_id))
            .order_by(AnalysisJob.created_at)
        )
        return list(rows.scalars())


async def _artifact_rows(database: Database, case_id: uuid.UUID) -> list[DerivedArtifact]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(DerivedArtifact).where(DerivedArtifact.case_id == str(case_id))
        )
        return list(rows.scalars())


async def _audit_rows(database: Database, resource_id: uuid.UUID) -> list[AuditLog]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AuditLog).where(AuditLog.resource_id == str(resource_id))
        )
        return list(rows.scalars())


def _findings_by_claim(payload: dict) -> dict[str, list[str]]:
    return {
        str(claim["claim_id"] or claim["claim_index"]): [item["code"] for item in claim["findings"]]
        for claim in payload["claims"]
    }


# -- happy path + deterministic finding matrix --------------------------------


async def test_report_audit_records_claim_review_with_deterministic_matrix(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    evidence_id = await _upload_ingest_txt(http_client, _owned_case, EVIDENCE_TXT)
    fake.claim_replies = [claims_reply(*_matrix_claims(evidence_id))]
    fake.support_replies = [
        support_reply(
            "supported",
            "the bank feed records the credit verbatim",
            [VALID_QUOTE],
        )
    ]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "report_audit"

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["claims_extracted"] == 6
    assert summary["claims_invalid"] == 1  # c_broken span
    assert summary["citations_checked"] == 2
    assert summary["citations_invalid"] == 1  # unknown evidence id
    assert summary["assessments_attempted"] == 1
    assert summary["assessments_valid"] == 1
    assert summary["assessments_invalid"] == 0
    assert summary["records_searched"] == 1  # the ingested statement record
    assert summary["counter_matches"] == 2  # c_received + c_balance hit "5,000"
    assert summary["findings_high"] == 5
    assert summary["findings_info"] == 2
    assert summary["findings_medium"] == 0
    assert summary["artifacts_created"] == 1
    assert summary["units_failed"] == 0
    assert summary["draft_chars"] == len(DRAFT)

    # The raw draft is never persisted on the job row - only its hash.
    assert DRAFT not in str(summary)

    artifacts = await _artifact_rows(database, _owned_case)
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.kind == "report_claim_review"
    assert artifact.origin == "llm"
    assert artifact.status == "pending_review"
    assert artifact.validation_status == "flagged"  # model-derived: always reviewed
    assert artifact.model_profile == "report_audit"
    payload = artifact.payload
    assert payload["draft_hash"] == summary["draft_hash"]
    assert payload["model"]["claims_extracted"] == 6
    assert payload["rules_version"] == "1.0.0"
    assert payload["counter_evidence"]["records_searched"] == 1

    findings = _findings_by_claim(payload)
    assert findings["c_total"] == ["numeric_mismatch"]
    assert findings["c_balance"] == ["currency_mismatch", "counter_evidence_candidate"]
    assert findings["c_early"] == ["timeline_discrepancy"]
    assert findings["c_received"] == ["counter_evidence_candidate"]
    assert sorted(findings["c_broken"]) == ["claim_extraction_invalid", "invalid_citation"]
    assert findings["c_late"] == []

    severities = {claim["claim_id"]: claim["severity"] for claim in payload["claims"]}
    assert severities["c_total"] == "high"
    assert severities["c_balance"] == "high"
    assert severities["c_early"] == "high"
    assert severities["c_received"] == "info"
    assert severities["c_late"] == "none"

    # The model assessment was quote-validated against the real record text.
    assessed = next(c for c in payload["claims"] if c["claim_id"] == "c_received")
    assert assessed["assessment"]["assessment"] == "supported"
    assert assessed["assessment"]["quotes_verified"] is True
    assert assessed["citations"][0]["ok"] is True
    assert VALID_QUOTE in assessed["counter_evidence"]["matches"][0]["excerpt"] or (
        assessed["counter_evidence"]["matches"][0]["token"] == "5,000"
    )

    # Audit trail: submitted + completed with counts/ids only.
    actions = {row.action for row in await _audit_rows(database, job.id)}
    assert {"report_audit.submitted", "report_audit.completed"} <= actions
    for row in await _audit_rows(database, job.id):
        assert DRAFT not in str(row.metadata_)


async def test_report_audit_supported_claim_produces_no_support_finding(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    evidence_id = await _upload_ingest_txt(http_client, _owned_case, EVIDENCE_TXT)
    text = "The account of Priya Sharma received ₹5,000 on 2026-01-10."
    start = DRAFT.index(text)
    fake.claim_replies = [
        claims_reply(
            {
                "claim_id": "c1",
                "text": text,
                "char_start": start,
                "char_end": start + len(text),
                "category": "factual_statement",
                "cited_ids": [f"evidence:{evidence_id}"],
            }
        )
    ]
    fake.support_replies = [support_reply("supported", "quoted ledger", [VALID_QUOTE])]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    summary = dict(jobs[-1].result_summary or {})
    assert summary["findings_high"] == 0
    assert summary["findings_medium"] == 0
    # only the info-level counter-evidence candidate remains
    assert summary["findings_info"] == 1
    assert jobs[-1].status == "succeeded"


# -- source XOR + typed refusals ----------------------------------------------


async def test_report_audit_requires_exactly_one_source(
    http_client: httpx.AsyncClient, _owned_case: uuid.UUID, phase2_fake_ai: FakeAI
) -> None:
    neither = await _submit(http_client, _owned_case, {})
    assert neither.status_code == 422
    assert neither.json()["error"]["code"] == CODE_DRAFT_SOURCE_INVALID

    half = await _submit(http_client, _owned_case, {"conversation_id": str(uuid.uuid4())})
    assert half.status_code == 422
    assert half.json()["error"]["code"] == CODE_DRAFT_SOURCE_INVALID

    both = await _submit(
        http_client,
        _owned_case,
        {
            "conversation_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()),
            "draft_text": DRAFT,
        },
    )
    assert both.status_code == 422
    assert both.json()["error"]["code"] == CODE_DRAFT_SOURCE_INVALID


async def test_report_audit_rejects_empty_and_oversized_drafts(
    http_client: httpx.AsyncClient, _owned_case: uuid.UUID, phase2_fake_ai: FakeAI
) -> None:
    empty = await _submit(http_client, _owned_case, {"draft_text": "   "})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == CODE_DRAFT_SOURCE_INVALID

    settings = get_settings()
    oversized = await _submit(
        http_client,
        _owned_case,
        {"draft_text": "x" * (settings.REPORT_AUDIT_MAX_DRAFT_CHARS + 1)},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == CODE_DRAFT_TOO_LARGE


async def _seed_message(
    database: Database,
    *,
    case_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    mode: str = "report",
    role: str = "assistant",
) -> tuple[uuid.UUID, uuid.UUID]:
    factory = database.session_factory()
    async with factory() as session:
        conversation = AIConversation(
            user_id=user_id,
            case_id=str(case_id),
            mode=mode,
            title="report draft",
        )
        session.add(conversation)
        await session.flush()
        message = AIMessage(
            conversation_id=conversation.id,
            case_id=str(case_id),
            role=role,
            content=content,
            generated_at=datetime.now(UTC),
        )
        session.add(message)
        await session.commit()
        return conversation.id, message.id


async def test_report_audit_message_source_records_ids_and_preserves_content(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    conv_id, message_id = await _seed_message(
        database, case_id=_owned_case, user_id=api_user.id, content=DRAFT
    )
    fake.claim_replies = [claims_reply()]

    response = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(conv_id), "message_id": str(message_id)},
    )
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["draft_source_type"] == "message"
    assert summary["message_id"] == str(message_id)

    artifacts = await _artifact_rows(database, _owned_case)
    draft_source = artifacts[0].payload["draft_source"]
    assert draft_source["type"] == "message"
    assert draft_source["message_id"] == str(message_id)
    assert draft_source["conversation_id"] == str(conv_id)

    # The referenced message is never modified by the audit.
    factory = database.session_factory()
    async with factory() as session:
        message = await session.get(AIMessage, message_id)
    assert message is not None
    assert message.content == DRAFT

    # Not stale while the message matches the audited hash.
    detail = await http_client.get(f"{PREFIX}/cases/{_owned_case}/report-audits/{job.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["stale"] is False

    # Editing the message afterwards marks the audit stale (read-time check).
    async with factory() as session:
        message = await session.get(AIMessage, message_id)
        assert message is not None
        message.content = DRAFT + " (edited after the audit)"
        await session.commit()
    detail = await http_client.get(f"{PREFIX}/cases/{_owned_case}/report-audits/{job.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["stale"] is True


async def test_report_audit_message_source_typed_refusals(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    factory = database.session_factory()

    # missing conversation / message
    missing = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4())},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == CODE_DRAFT_UNAVAILABLE

    # conversation that is not report-mode
    conv_id, message_id = await _seed_message(
        database, case_id=_owned_case, user_id=api_user.id, content=DRAFT, mode="case"
    )
    wrong_mode = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(conv_id), "message_id": str(message_id)},
    )
    assert wrong_mode.status_code == 422
    assert wrong_mode.json()["error"]["code"] == CODE_MESSAGE_NOT_REPORT_MODE

    # report-mode conversation, but the message is a user turn
    conv_id, user_message = await _seed_message(
        database,
        case_id=_owned_case,
        user_id=api_user.id,
        content=DRAFT,
        role="user",
    )
    user_turn = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(conv_id), "message_id": str(user_message)},
    )
    assert user_turn.status_code == 422
    assert user_turn.json()["error"]["code"] == CODE_DRAFT_SOURCE_INVALID

    # message id from a different conversation of the same case
    conv_a, _ = await _seed_message(
        database, case_id=_owned_case, user_id=api_user.id, content=DRAFT
    )
    conv_b, message_b = await _seed_message(
        database, case_id=_owned_case, user_id=api_user.id, content=DRAFT
    )
    mixed = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(conv_a), "message_id": str(message_b)},
    )
    assert mixed.status_code == 404
    assert mixed.json()["error"]["code"] == CODE_DRAFT_UNAVAILABLE

    # a conversation that belongs to another case is indistinguishable
    # from a missing one (no existence oracle)
    other_case = Case(
        id=uuid.uuid4(),
        case_number=f"RAOTHER-{uuid.uuid4().hex[:8]}",
        title="other case",
        status="open",
        owner_id=api_user.id,
    )
    async with factory() as session:
        session.add(other_case)
        await session.commit()
        other_case_id = other_case.id
    other_conv, other_message = await _seed_message(
        database, case_id=other_case_id, user_id=api_user.id, content=DRAFT
    )
    cross_case = await _submit(
        http_client,
        _owned_case,
        {"conversation_id": str(other_conv), "message_id": str(other_message)},
    )
    assert cross_case.status_code == 404
    assert cross_case.json()["error"]["code"] == CODE_DRAFT_UNAVAILABLE
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == other_case_id))
        await session.commit()


# -- duplicate / disabled / permission / cancel -------------------------------


async def test_report_audit_refuses_while_an_audit_of_the_same_draft_is_active(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.services.report_audit import draft_sha256

    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="report_audit",
                status="pending",
                idempotency_key=f"seed-active-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=300,
                cancel_requested=False,
                result_summary={"draft_hash": draft_sha256(DRAFT)},
                actor_id=str(api_user.id),
            )
        )
        await session.commit()

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == CODE_REPORT_AUDIT_ACTIVE

    # a different draft is not blocked by the active run
    other = await _submit(http_client, _owned_case, {"draft_text": "A different draft."})
    assert other.status_code == 202, other.text


async def test_report_audit_disabled_feature_is_refused(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
    monkeypatch,
    phase2_fake_ai: FakeAI,
) -> None:
    monkeypatch.setattr(get_settings(), "AI_FEATURE_REPORT_AUDIT", False)
    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == CODE_AI_DISABLED


async def test_report_audit_open_to_case_members_and_refused_for_strangers(
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app

    # a case member with case.read (VIEWER) may submit - same permission as
    # report drafting (documented scope decision)
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
        allowed = await _submit(client, _owned_case, {"draft_text": DRAFT})
    assert allowed.status_code == 202, allowed.text

    # a non-member is refused without an existence oracle
    stranger = await user_factory(role="INVESTIGATOR")
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {stranger.token}"},
    ) as client:
        refused = await _submit(client, _owned_case, {"draft_text": DRAFT})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == CODE_CASE_ACCESS_DENIED

    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == viewer.id))
        await session.commit()


async def test_report_audit_refused_for_read_only_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, _owned_case)
        assert case is not None
        case.status = "closed"
        await session.commit()
    try:
        response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == CODE_CASE_READ_ONLY
    finally:
        async with factory() as session:
            case = await session.get(Case, _owned_case)
            assert case is not None
            case.status = "open"
            await session.commit()


async def test_report_audit_cancel_before_run_creates_no_artifacts(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
    phase2_fake_ai: FakeAI,
) -> None:
    from app.main import app as shared_app
    from app.services.report_audit import run_report_audit_job

    job_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                id=job_id,
                case_id=str(_owned_case),
                feature="report_audit",
                status="pending",
                idempotency_key=f"seed-cancel-{uuid.uuid4().hex[:10]}",
                attempts=1,
                timeout_seconds=300,
                cancel_requested=True,
                actor_id=str(api_user.id),
            )
        )
        await session.commit()

    await run_report_audit_job(shared_app, job_id, {"draft": DRAFT, "source_type": "text"})

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
    assert phase2_fake_ai.claim_calls == []


# -- model failure honesty ----------------------------------------------------


async def test_report_audit_extraction_outage_fails_without_artifact(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.error = RuntimeError("model overloaded")
    fake.fail_after = 0  # the claim-extraction call raises

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "failed"  # nothing to review -> honest failure
    assert CODE_REPORT_AUDIT_FAILED in (job.error or "")
    assert await _artifact_rows(database, _owned_case) == []
    actions = {row.action for row in await _audit_rows(database, job.id)}
    assert "report_audit.failed" in actions


async def test_report_audit_support_outage_is_partial_with_findings_kept(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    evidence_id = await _upload_ingest_txt(http_client, _owned_case, EVIDENCE_TXT)
    fake.claim_replies = [claims_reply(*_matrix_claims(evidence_id))]

    # Fail only the support surface (the shared error knob would also fail
    # extraction, which is the honest-failure test above).
    async def _boom(*, claim: str, sources: str):
        raise RuntimeError("model overloaded")

    fake.assess_claim_support = _boom  # type: ignore[method-assign]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "partial"
    summary = dict(job.result_summary or {})
    assert summary["units_failed"] == 1
    assert summary["assessments_attempted"] == 1
    assert summary["artifacts_created"] == 1  # deterministic findings kept

    artifacts = await _artifact_rows(database, _owned_case)
    payload = artifacts[0].payload
    findings = _findings_by_claim(payload)
    assert findings["c_total"] == ["numeric_mismatch"]  # deterministic work stands
    assessed = next(c for c in payload["claims"] if c["claim_id"] == "c_received")
    assert assessed["assessment"] is None
    assert assessed["assessment_skipped"] == "model_call_failed"


async def test_report_audit_unparseable_extraction_flags_the_artifact(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.claim_replies = ["this is not the json contract"]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    job = jobs[-1]
    assert job.status == "partial"
    summary = dict(job.result_summary or {})
    assert summary["units_failed"] == 1
    assert summary["claims_extracted"] == 0

    artifacts = await _artifact_rows(database, _owned_case)
    assert len(artifacts) == 1
    codes = {err["code"] for err in (artifacts[0].validation_errors or [])}
    assert "unparseable_model_output" in codes
    assert "model_claims_unreviewed" in codes  # standing: never auto-trusted


async def test_report_audit_forged_quote_invalidates_the_assessment(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    evidence_id = await _upload_ingest_txt(http_client, _owned_case, EVIDENCE_TXT)
    text = "The account of Priya Sharma received ₹5,000 on 2026-01-10."
    start = DRAFT.index(text)
    fake.claim_replies = [
        claims_reply(
            {
                "claim_id": "c1",
                "text": text,
                "char_start": start,
                "char_end": start + len(text),
                "category": "factual_statement",
                "cited_ids": [f"evidence:{evidence_id}"],
            }
        )
    ]
    fake.support_replies = [
        support_reply("supported", "clearly true", ["the account was drained completely"])
    ]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    summary = dict(jobs[-1].result_summary or {})
    assert summary["assessments_invalid"] == 1
    assert summary["assessments_valid"] == 0

    artifacts = await _artifact_rows(database, _owned_case)
    claim = artifacts[0].payload["claims"][0]
    assert claim["assessment"]["quotes_verified"] is False
    assert claim["assessment"]["unverified_quotes"] == ["the account was drained completely"]
    # the amount also matches the ingested record -> info-level counter note
    assert sorted(item["code"] for item in claim["findings"]) == [
        "assessment_unverified",
        "counter_evidence_candidate",
    ]
    assert claim["severity"] == "medium"  # unverified assessment dominates the info note
    codes = {err["code"] for err in (artifacts[0].validation_errors or [])}
    assert "assessment_unverified" in codes


async def test_report_audit_cross_case_citation_is_a_finding_not_a_retrieval(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    # evidence in a *different* case the same user owns: citing it must
    # surface a wrong-case finding without borrowing any content
    other_case = Case(
        id=uuid.uuid4(),
        case_number=f"RACROSS-{uuid.uuid4().hex[:8]}",
        title="cross case",
        status="open",
        owner_id=(await _actor_id(database, _owned_case)),
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other_case)
        await session.commit()
        other_case_id = other_case.id
    other_evidence = EvidenceFile(
        id=uuid.uuid4(),
        case_id=str(other_case_id),
        original_filename="foreign.txt",
        stored_key=f"evidence/{other_case_id}/foreign.txt",
        content_type="text/plain",
        file_size=10,
        sha256="a" * 64,
        format="txt",
    )
    async with factory() as session:
        session.add(other_evidence)
        await session.commit()
        foreign_id = other_evidence.id

    text = "The account of Priya Sharma received ₹5,000 on 2026-01-10."
    start = DRAFT.index(text)
    fake.claim_replies = [
        claims_reply(
            {
                "claim_id": "c1",
                "text": text,
                "char_start": start,
                "char_end": start + len(text),
                "category": "factual_statement",
                "cited_ids": [f"evidence:{foreign_id}"],
            }
        )
    ]

    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    summary = dict(jobs[-1].result_summary or {})
    assert summary["citations_invalid"] == 1

    artifacts = await _artifact_rows(database, _owned_case)
    claim = artifacts[0].payload["claims"][0]
    assert claim["citations"][0]["codes"] == ["citation_wrong_case"]
    assert [item["code"] for item in claim["findings"]] == ["invalid_citation"]
    assert claim["assessment_skipped"] == "no_valid_citation"  # no foreign content

    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == other_case_id))
        await session.commit()


async def _actor_id(database: Database, case_id: uuid.UUID) -> uuid.UUID:
    factory = database.session_factory()
    async with factory() as session:
        row = (
            await session.execute(select(Case.owner_id).where(Case.id == str(case_id)))
        ).scalar_one()
        return uuid.UUID(str(row))


# -- list/detail surface + dedupe ---------------------------------------------


async def test_report_audit_list_and_detail_are_case_scoped(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.claim_replies = [claims_reply()]
    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["job"]["id"])

    listing = await http_client.get(f"{PREFIX}/cases/{_owned_case}/report-audits")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert uuid.UUID(item["id"]) == job_id
    assert item["status"] == "succeeded"
    assert item["draft_source_type"] == "text"
    assert item["draft_chars"] == len(DRAFT)
    assert item["claims"] == 0
    assert item["stale"] is None  # text drafts have nothing to go stale against

    detail = await http_client.get(f"{PREFIX}/cases/{_owned_case}/report-audits/{job_id}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["artifact"]["kind"] == "report_claim_review"
    assert detail_body["artifact"]["payload"]["report_audit"] is True

    unknown = await http_client.get(f"{PREFIX}/cases/{_owned_case}/report-audits/{uuid.uuid4()}")
    assert unknown.status_code == 404


async def test_report_audit_retry_after_completion_reuses_identical_artifact(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    fake.claim_replies = [claims_reply(), claims_reply()]

    first = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert first.status_code == 202, first.text
    second = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert second.status_code == 202, second.text

    jobs = await _job_rows(database, _owned_case)
    assert len(jobs) == 2
    summary = dict(jobs[-1].result_summary or {})
    assert summary["artifacts_reused"] == 1
    assert summary["artifacts_created"] == 0
    # identical payload -> exactly one artifact row (content-hash dedupe)
    assert len(await _artifact_rows(database, _owned_case)) == 1


async def test_report_audit_counter_evidence_note_distinguishes_no_records(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    fake = phase2_fake_ai
    text = "The account of Priya Sharma received ₹5,000 on 2026-01-10."
    start = DRAFT.index(text)
    fake.claim_replies = [
        claims_reply(
            {
                "claim_id": "c1",
                "text": text,
                "char_start": start,
                "char_end": start + len(text),
                "category": "factual_statement",
                "cited_ids": [],
            }
        )
    ]
    # no evidence exists in this case at all
    response = await _submit(http_client, _owned_case, {"draft_text": DRAFT})
    assert response.status_code == 202, response.text

    jobs = await _job_rows(database, _owned_case)
    summary = dict(jobs[-1].result_summary or {})
    assert summary["records_searched"] == 0
    assert summary["counter_matches"] == 0

    artifacts = await _artifact_rows(database, _owned_case)
    claim = artifacts[0].payload["claims"][0]
    assert claim["counter_evidence"]["note"] == "no source records exist for this case"
    assert claim["counter_evidence"]["matches"] == []


async def test_report_audit_all_db_features_have_a_cancel_contract(
    _owned_case: uuid.UUID,
) -> None:
    from app.api.routes.evidence_intelligence import _CANCELABLE_FEATURES

    assert set(ANALYSIS_JOB_FEATURES) <= set(_CANCELABLE_FEATURES)

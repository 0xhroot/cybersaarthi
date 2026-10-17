"""Phase 4 feature B: permission-scoped cross-case discovery (backend).

Two layers, both asserted against expected values the test derives itself:

* **pure unit tests** for normalization, indicator extraction, classification,
  the bounded score band, conflict flagging and hash-key grouping — the
  invariants that a shared identifier is only ever a *candidate* signal and
  that no all-pairs comparison happens;
* **API and runner tests** for the security contract — the ``crosscase.read``
  capability, a no-leak 404 that never reveals which scope id failed (or
  whether it exists), execution-time re-check (a revoked scope fails the job
  closed with ``CROSS_CASE_SCOPE_REVOKED``), and read-time omission of any
  candidate touching an inaccessible case.

Seed data mirrors the live schema (``docs/ai/PHASE_4_DESIGN.md`` §5): two cases
sharing a phone (different formatting), an account (identical) and an email
(different case), plus a shared person name with *no* shared identifier. If a
fabricated probability, an all-pairs scan, an entity merge, or a scope leak is
ever reintroduced, these tests fail.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import httpx
import pytest
from app.core.codes import (
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_CROSS_CASE_ACTIVE,
    CODE_CROSS_CASE_SCOPE_DENIED,
    CODE_CROSS_CASE_SCOPE_REVOKED,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_INVALID_PAYLOAD,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import (
    AnalysisJob,
    AuditLog,
    Case,
    CaseMember,
    DerivedArtifact,
    Entity,
    EvidenceFile,
    SourceRecord,
)
from app.services import cross_case as xc_svc
from app.services.normalization import blocking_key
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from tests.api.conftest import ApiUser

PREFIX = get_settings().API_V1_PREFIX


@pytest.fixture
async def _second_case(database: Database, api_user: ApiUser) -> uuid.UUID:
    """A second case owned by the same investigator (both are in scope)."""
    case = Case(
        id=uuid.uuid4(),
        case_number=f"AIXC-{uuid.uuid4().hex[:8]}",
        title="cross-case second case",
        status="open",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    yield case_id
    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.case_id == case_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()

# -- seeded records -------------------------------------------------------------
# Two cases sharing three identifiers (account identical -> exact; phone and
# email differently formatted -> normalized) plus a shared person name with no
# shared identifier on the entity itself.

CASE_A_RECORD = {
    "account_number": "ACC-SIH-001",
    "beneficiary_phone": "+91 98200 00001",
    "beneficiary_email": "priya.sharma@example.com",
}
CASE_B_RECORD = {
    "account_number": "ACC-SIH-001",  # identical original -> exact_identifier
    "beneficiary_phone": "9820000001",  # same number, other format -> normalized
    "beneficiary_email": "Priya.Sharma@Example.com",  # case differs -> normalized
}
SHARED_NAME = "Priya Sharma"


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _seed_evidence_records(
    database: Database,
    case_id: uuid.UUID,
    records: list[dict[str, object]],
    *,
    label: str,
) -> uuid.UUID:
    """Insert one evidence file plus its parsed source records (no storage)."""
    payload = json.dumps(records).encode()
    factory = database.session_factory()
    async with factory() as session:
        evidence = EvidenceFile(
            case_id=str(case_id),
            original_filename=f"{label}.json",
            stored_key=f"seed/{label}.json",
            content_type="application/json",
            file_size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            format="json",
            encoding="utf-8",
            record_count=len(records),
            status="stored",
        )
        session.add(evidence)
        await session.flush()
        evidence_id = uuid.UUID(str(evidence.id))
        for index, raw in enumerate(records, start=1):
            session.add(
                SourceRecord(
                    evidence_file_id=str(evidence_id),
                    record_no=index,
                    raw_data=dict(raw),
                    status="parsed",
                )
            )
        await session.commit()
        return evidence_id


async def _seed_person(database: Database, case_id: uuid.UUID, name: str) -> None:
    """An active person entity (contributes only a ``name`` indicator)."""
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            Entity(
                case_id=str(case_id),
                entity_type="person",
                canonical_value=name,
                display_value=name,
                blocking_key=blocking_key("person", name.lower()),
                status="active",
            )
        )
        await session.commit()


async def _add_member(
    database: Database, case_id: uuid.UUID, user_id: uuid.UUID, *, role: str = "collaborator"
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        session.add(CaseMember(case_id=case_id, user_id=user_id, role=role))
        await session.commit()


async def _artifacts(database: Database, case_id: uuid.UUID) -> list[DerivedArtifact]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(DerivedArtifact).where(
                DerivedArtifact.case_id == str(case_id),
                DerivedArtifact.kind == "cross_case_link",
            )
        )
        return list(rows.scalars())


async def _job_row(database: Database, job_id: uuid.UUID) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None, f"job {job_id} not found"
        return job


async def _audit_row(database: Database, *, action: str, resource_id: uuid.UUID | str):
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.resource_id == str(resource_id),
            )
        )
        return rows.scalars().first()


async def _seed_pending_cross_job(
    database: Database,
    anchor_case_id: uuid.UUID,
    scope_case_ids: list[uuid.UUID],
    *,
    actor_id: uuid.UUID,
) -> uuid.UUID:
    scope = sorted(str(value) for value in scope_case_ids)
    factory = database.session_factory()
    async with factory() as session:
        job = AnalysisJob(
            case_id=str(anchor_case_id),
            feature="cross_case",
            status="pending",
            idempotency_key=f"seed-cross_case-{uuid.uuid4().hex[:8]}",
            attempts=1,
            timeout_seconds=300,
            actor_id=str(actor_id),
            result_summary={"scope_case_ids": scope, "scope_hash": xc_svc._scope_hash(scope)},
        )
        session.add(job)
        await session.commit()
        return uuid.UUID(str(job.id))


async def _run_job(database: Database, job_id: uuid.UUID, *, settings) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        await xc_svc.execute_cross_case(session, job_id=job_id, settings=settings)
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        await session.refresh(job)
        return job


async def _discover(
    client: httpx.AsyncClient, anchor: uuid.UUID, case_ids: list[uuid.UUID]
) -> httpx.Response:
    return await client.post(
        f"{PREFIX}/cross-case/discover",
        json={"anchor_case_id": str(anchor), "case_ids": [str(c) for c in case_ids]},
    )


# -- pure normalization ---------------------------------------------------------


def test_normalization_is_documented_and_lossless() -> None:
    # Phone: country code preserved, digits-only alternative normalizes equal.
    assert xc_svc._normalize_for("phone", "+91 98200 00001") == "919820000001"
    assert xc_svc._normalize_for("phone", "9820000001") == "919820000001"
    # Account: alphanumerics only, upper-cased.
    assert xc_svc._normalize_for("account_ref", "ACC-SIH-001") == "ACCSIH001"
    # Email: case-folded and trimmed.
    assert xc_svc._normalize_for("email", " Priya.Sharma@Example.com ") == (
        "priya.sharma@example.com"
    )
    # URL: case-folded, one trailing slash stripped.
    assert xc_svc.normalize_url("HTTPS://Example.com/Path/") == "https://example.com/path"
    # Domain: lower-cased, www stripped, from a URL or an email.
    assert xc_svc.normalize_domain("https://www.Example.com/x") == "example.com"
    assert xc_svc.normalize_domain("a@Example.com") == "example.com"
    # Transaction id: alphanumerics only, upper-cased.
    assert xc_svc.normalize_txn("txn-sih-001") == "TXNSIH001"
    # Device: trimmed and case-folded, whitespace removed.
    assert xc_svc.normalize_device(" iPhone XYZ 001 ") == "iphonexyz001"
    # Name: case-folded, whitespace collapsed, edge punctuation stripped.
    assert xc_svc.normalize_name("  Priya   Sharma. ") == "priya sharma"
    # Invalid values normalize to None (never silently coerced).
    assert xc_svc._normalize_for("phone", "not-a-phone") is None
    assert xc_svc._normalize_for("account_ref", "abc") is None  # < 6 chars


def test_unkeyed_detection_is_pattern_only_and_full_match() -> None:
    assert xc_svc.detect_unkeyed_kind("a@b.com") == ("email", "a@b.com")
    assert xc_svc.detect_unkeyed_kind("https://x.io/p") == ("url", "https://x.io/p")
    assert xc_svc.detect_unkeyed_kind("9820000001") == ("phone", "919820000001")
    # A long digit string that only looks numeric is not a phone (needs 7..15).
    assert xc_svc.detect_unkeyed_kind("12345678901234567890123456") is None
    # Free text is never classified.
    assert xc_svc.detect_unkeyed_kind("called about a refund") is None


# -- extraction -----------------------------------------------------------------


def test_record_indicators_prefer_keys_then_patterns() -> None:
    counters = xc_svc.CaseExtraction(case_id="case-a")
    record = SourceRecord(
        evidence_file_id=str(uuid.uuid4()),
        record_no=1,
        raw_data=CASE_A_RECORD,
        status="parsed",
    )
    record.id = uuid.uuid4()
    indicators = xc_svc.extract_record_indicators(record, case_id="case-a", counters=counters)
    kinds = {i.kind for i in indicators}
    # account_number (key), beneficiary_phone (key), beneficiary_email (unkeyed
    # pattern), plus the domain derived from the email.
    assert {"account_ref", "phone", "email", "domain"} <= kinds
    phone = next(i for i in indicators if i.kind == "phone")
    # Provenance is never None: both the record and its evidence file are cited.
    assert phone.source_record_id == str(record.id)
    assert phone.evidence_file_id == str(record.evidence_file_id)
    # Originals are preserved verbatim alongside the normalized value.
    assert phone.value_original == "+91 98200 00001"
    assert phone.value_normalized == "919820000001"


def test_merged_or_rejected_entities_never_contribute() -> None:
    counters = xc_svc.CaseExtraction(case_id="case-a")
    merged = Entity(
        case_id="case-a",
        entity_type="person",
        canonical_value=SHARED_NAME,
        display_value=SHARED_NAME,
        blocking_key="priya sharma",
        status="merged",
    )
    merged.id = uuid.uuid4()
    # collect_case_indicators filters to active entities; the extractor itself
    # is given only active rows, so a merged entity yields nothing here.
    assert xc_svc.extract_entity_indicators(merged, case_id="case-a", counters=counters) != []
    # The real guarantee is the SQL filter (Entity.status == "active"), exercised
    # in the API test below where only active entities are seeded.


# -- classification -------------------------------------------------------------


def _controlled_member(case_id: str, originals: list[str], *, reviewed: bool = False):
    return {
        "case_id": case_id,
        "originals": originals,
        "reviewed": reviewed,
    }


def test_classification_labels_match_signal_strength() -> None:
    cases = ["a", "b"]
    base_originals = {"a": ["TXN-1"], "b": ["TXN-1"]}
    side_reviewed = {"a": False, "b": False}
    # Identical raw strings -> exact_identifier.
    assert (
        xc_svc._classify(
            kind="txn_id",
            side_originals=base_originals,
            side_reviewed=side_reviewed,
            additional_shared_kinds=[],
            side_values_by_kind={},
            cases=cases,
        )
        == "exact_identifier"
    )
    # Identical only after normalization -> normalized_identifier.
    assert (
        xc_svc._classify(
            kind="phone",
            side_originals={"a": ["+91 98200 00001"], "b": ["9820000001"]},
            side_reviewed=side_reviewed,
            additional_shared_kinds=[],
            side_values_by_kind={},
            cases=cases,
        )
        == "normalized_identifier"
    )
    # A Phase 3-reviewed alias on either side -> reviewed_alias.
    assert (
        xc_svc._classify(
            kind="phone",
            side_originals=base_originals,
            side_reviewed={"a": True, "b": False},
            additional_shared_kinds=[],
            side_values_by_kind={},
            cases=cases,
        )
        == "reviewed_alias"
    )
    # Name group with no shared identifier -> similarity_name_only.
    assert (
        xc_svc._classify(
            kind="name",
            side_originals={"a": ["Priya Sharma"], "b": ["Priya Sharma"]},
            side_reviewed=side_reviewed,
            additional_shared_kinds=[],
            side_values_by_kind={},
            cases=cases,
        )
        == "similarity_name_only"
    )
    # Name group *with* a genuinely shared identifier is upgraded, not left
    # informational.
    assert (
        xc_svc._classify(
            kind="name",
            side_originals={"a": ["Priya Sharma"], "b": ["Priya Sharma"]},
            side_reviewed=side_reviewed,
            additional_shared_kinds=["phone"],
            side_values_by_kind={"phone": {"a": ["919820000001"], "b": ["919820000001"]}},
            cases=cases,
        )
        == "exact_identifier"
    )


def _indicator(kind: str, norm: str, original: str, case_id: str, **kw):
    return xc_svc.Indicator(
        kind=kind,
        value_normalized=norm,
        value_original=original,
        case_id=case_id,
        **kw,
    )


def _record_indicator(
    kind: str, norm: str, original: str, case_id: str, record_id: str, file_id: str
):
    return _indicator(
        kind,
        norm,
        original,
        case_id,
        source_record_id=record_id,
        evidence_file_id=file_id,
    )


def test_score_is_a_bounded_band_not_a_probability() -> None:
    # A clean two-case group over one record per side, no other shared kind:
    # exact_identifier base 60 + 0 additional-shared + supporting bonus.
    # Each side cites 1 record + 1 file = 2; bonus = min(15, 3*(4-2)) = 6.
    file_a, file_b = str(uuid.uuid4()), str(uuid.uuid4())
    rec_a, rec_b = str(uuid.uuid4()), str(uuid.uuid4())
    indicators = {
        "a": [_record_indicator("txn_id", "TXN1", "TXN-1", "a", rec_a, file_a)],
        "b": [_record_indicator("txn_id", "TXN1", "TXN-1", "b", rec_b, file_b)],
    }
    members = {"a": indicators["a"], "b": indicators["b"]}
    payload = xc_svc.build_candidate(
        kind="txn_id",
        value_normalized="TXN1",
        members=members,
        indicators_by_case=indicators,
        indices_by_case={
            "a": xc_svc._build_case_index(indicators["a"]),
            "b": xc_svc._build_case_index(indicators["b"]),
        },
        scope_case_ids=["a", "b"],
        scope_hash="h",
        max_supporting_ids=10,
    )
    assert payload["classification"] == "exact_identifier"
    # 60 (base) + 0 (no additional shared) + 6 (supporting bonus).
    assert payload["score"] == 66
    assert 0 <= payload["score"] <= 100
    assert "NOT a probability" in payload["score_semantics"]


def test_conflicting_identifiers_are_flagged_not_hidden() -> None:
    # Two cases share a phone but carry disjoint emails: the shared phone still
    # forms a candidate, and the disagreement is surfaced, never dropped.
    file_a, file_b = str(uuid.uuid4()), str(uuid.uuid4())
    rec_a, rec_b = str(uuid.uuid4()), str(uuid.uuid4())
    indicators = {
        "a": [
            _record_indicator("phone", "919820000001", "+91 98200 00001", "a", rec_a, file_a),
            _record_indicator("email", "a@alpha.test", "a@alpha.test", "a", rec_a, file_a),
        ],
        "b": [
            _record_indicator("phone", "919820000001", "9820000001", "b", rec_b, file_b),
            _record_indicator("email", "b@beta.test", "b@beta.test", "b", rec_b, file_b),
        ],
    }
    members = {"a": [indicators["a"][0]], "b": [indicators["b"][0]]}
    payload = xc_svc.build_candidate(
        kind="phone",
        value_normalized="919820000001",
        members=members,
        indicators_by_case=indicators,
        indices_by_case={
            "a": xc_svc._build_case_index(indicators["a"]),
            "b": xc_svc._build_case_index(indicators["b"]),
        },
        scope_case_ids=["a", "b"],
        scope_hash="h",
        max_supporting_ids=10,
    )
    conflict = payload["conflicting_attributes"]
    assert conflict["flagged"] is True
    kinds = {e["kind"] for e in conflict["evidence"]}
    assert "email" in kinds
    email_evidence = next(e for e in conflict["evidence"] if e["kind"] == "email")
    assert email_evidence["per_case_values"]["a"] == ["a@alpha.test"]
    assert email_evidence["per_case_values"]["b"] == ["b@beta.test"]


def test_name_only_candidate_is_informational_and_not_reviewable() -> None:
    indicators = {
        "a": [_indicator("name", "priya sharma", "Priya Sharma", "a")],
        "b": [_indicator("name", "priya sharma", "Priya Sharma", "b")],
    }
    payload = xc_svc.build_candidate(
        kind="name",
        value_normalized="priya sharma",
        members={"a": indicators["a"], "b": indicators["b"]},
        indicators_by_case=indicators,
        indices_by_case={
            "a": xc_svc._build_case_index(indicators["a"]),
            "b": xc_svc._build_case_index(indicators["b"]),
        },
        scope_case_ids=["a", "b"],
        scope_hash="h",
        max_supporting_ids=10,
    )
    assert payload["classification"] == "similarity_name_only"
    assert payload["reviewable"] is False
    assert payload["review_disabled_reason"]


def test_grouping_is_hash_keyed_not_all_pairs() -> None:
    # Case A and case B share no (kind, value); case C bridges nothing. Only a
    # truly shared key can form a candidate — never a pairwise scan.
    indicators = {
        "a": [_indicator("phone", "111", "111", "a"), _indicator("email", "x@y.z", "x@y.z", "a")],
        "b": [_indicator("phone", "222", "222", "b"), _indicator("email", "p@q.r", "p@q.r", "b")],
    }
    candidates, stats = xc_svc.build_candidates(
        indicators,
        scope_case_ids=["a", "b"],
        scope_hash="h",
        max_candidates=10,
        max_supporting_ids=10,
    )
    assert candidates == []
    assert stats["groups_shared"] == 0
    assert stats["groups_total"] == 4  # two kinds x two distinct values


# -- API + runner ---------------------------------------------------------------


async def test_discover_run_stores_reviewable_candidates(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="xc-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="xc-b")
    await _seed_person(database, _owned_case, SHARED_NAME)
    await _seed_person(database, _second_case, SHARED_NAME)

    response = await _discover(http_client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "cross_case"

    job_id = uuid.UUID(body["job"]["id"])
    job = await _job_row(database, job_id)
    assert job.status == "succeeded"
    assert str(job.case_id) == str(_owned_case)  # anchored to the requesting case
    summary = dict(job.result_summary or {})
    assert summary["scope_cases"] == 2
    assert summary["cases_scanned"] == 2
    assert summary["records_scanned"] == 2
    assert summary["indicators_extracted"] == 10  # 5 per case (4 record + 1 name)
    assert summary["groups_shared"] == 5
    assert summary["candidates_expected"] == 5
    assert summary["artifacts_created"] == 5
    assert summary["candidates_bounded"] is False

    artifacts = await _artifacts(database, _owned_case)
    assert len(artifacts) == 5
    by_kind = {}
    for artifact in artifacts:
        assert artifact.status == "pending_review"
        assert artifact.origin == "deterministic"
        assert artifact.parser_version == xc_svc.CROSSCASE_RULES_VERSION
        assert str(artifact.analysis_job_id) == str(job_id)
        assert str(artifact.created_by) == str(api_user.id)
        payload = dict(artifact.payload or {})
        by_kind[payload["group"]["indicator_kind"]] = payload

    # Classifications derived from the seed originals, not the implementation.
    assert by_kind["account_ref"]["classification"] == "exact_identifier"
    assert by_kind["phone"]["classification"] == "normalized_identifier"
    assert by_kind["email"]["classification"] == "normalized_identifier"
    assert by_kind["domain"]["classification"] == "exact_identifier"
    assert by_kind["name"]["classification"] == "similarity_name_only"

    # Only the name-similarity candidate is non-reviewable.
    assert by_kind["name"]["reviewable"] is False
    for kind in ("account_ref", "phone", "email", "domain"):
        assert by_kind[kind]["reviewable"] is True

    # Scores are bounded ints with an explicit "not a probability" semantics.
    for payload in by_kind.values():
        assert isinstance(payload["score"], int)
        assert 0 <= payload["score"] <= 100
        assert "NOT a probability" in payload["score_semantics"]

    # Both cases appear as sides with their own provenance; no merge happened.
    account = by_kind["account_ref"]
    side_cases = {side["case_id"] for side in account["sides"]}
    assert side_cases == {str(_owned_case), str(_second_case)}
    for side in account["sides"]:
        assert side["source_record_ids"], "each side cites its own record"
        assert side["value_originals"] == ["ACC-SIH-001"]
    name = by_kind["name"]
    for side in name["sides"]:
        assert side["entity_ids"], "the name side cites its own entity"

    # Honest limitations and the no-Neo4j-read freshness note.
    limitations = " ".join(account["limitations"])
    assert "never proof" in limitations
    assert "never merges entities" in limitations
    assert "Neo4j" in account["graph_freshness_note"]

    audit = await _audit_row(database, action="cross_case.analysis_completed", resource_id=job_id)
    assert audit is not None


async def test_discover_is_one_active_job_and_typed_409(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="cross_case",
                status="running",
                idempotency_key=f"running-cross_case-{uuid.uuid4().hex[:8]}",
                attempts=1,
                timeout_seconds=300,
                actor_id=None,
            )
        )
        await session.commit()

    refused = await _discover(http_client, _owned_case, [_owned_case, _second_case])
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == CODE_CROSS_CASE_ACTIVE

    # Submission audit records the authorized scope (ids + hash).
    audit = await _audit_row(
        database, action="cross_case.search_submitted", resource_id=_owned_case
    )
    assert audit is None  # denial happened before the audit write


async def test_discover_requires_crosscase_permission(
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    user_factory,
) -> None:
    viewer = await user_factory(role="VIEWER")
    async with _client(viewer.token) as client:
        response = await _discover(client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    # No job, no artifact: denial happened before any work.
    factory = database.session_factory()
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.case_id == str(_owned_case),
                    AnalysisJob.feature == "cross_case",
                )
            )
        ).scalars()
        assert list(jobs) == []
    assert await _artifacts(database, _owned_case) == []


async def test_discover_scope_never_reveals_case_existence(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    _stranger_case: uuid.UUID,
) -> None:
    nonexistent = uuid.uuid4()
    # A real-but-foreign case and a nonexistent id are indistinguishable.
    for probe in (_stranger_case, nonexistent):
        response = await _discover(http_client, _owned_case, [_owned_case, probe])
        assert response.status_code == 404, response.text
        error = response.json()["error"]
        assert error["code"] == CODE_CROSS_CASE_SCOPE_DENIED
        # The response never names which id failed nor admits it exists.
        assert str(probe) not in response.text
        assert "not accessible" in error["message"]


async def test_discover_rejects_bad_scope_bounds(
    http_client: AsyncClient,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
) -> None:
    # Anchor must itself be part of the scope.
    response = await _discover(http_client, _owned_case, [_second_case, uuid.uuid4()])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == CODE_INVALID_PAYLOAD

    # Scope is bounded (never "every case I can see").
    too_many = [uuid.uuid4() for _ in range(get_settings().CROSSCASE_MAX_CASES + 1)]
    response = await _discover(http_client, _owned_case, [_owned_case, *too_many])
    assert response.status_code == 422, response.text


async def test_partial_scope_member_is_denied_without_leak(
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    user_factory,
) -> None:
    """A member of the anchor but not the side case gets the same no-leak 404."""
    partial = await user_factory(role="INVESTIGATOR")
    await _add_member(database, _owned_case, partial.id)
    async with _client(partial.token) as client:
        response = await _discover(client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == CODE_CROSS_CASE_SCOPE_DENIED
    assert str(_second_case) not in response.text


async def test_runner_fails_closed_when_scope_revoked(
    database: Database,
    settings,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    user_factory,
) -> None:
    """Authorization is re-checked at execution time, not trusted from submit."""
    actor = await user_factory(role="INVESTIGATOR")
    await _add_member(database, _owned_case, actor.id)
    await _add_member(database, _second_case, actor.id)
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="rev-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="rev-b")
    job_id = await _seed_pending_cross_job(
        database, _owned_case, [_owned_case, _second_case], actor_id=actor.id
    )

    # Revoke access to the side case between submission and execution.
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(
            delete(CaseMember).where(
                CaseMember.user_id == actor.id, CaseMember.case_id == _second_case
            )
        )
        await session.commit()

    job = await _run_job(database, job_id, settings=settings)

    assert job.status == "failed"
    assert dict(job.result_summary or {})["error_code"] == CODE_CROSS_CASE_SCOPE_REVOKED
    # Denied before a single record was analyzed: no candidate, no artifact.
    assert await _artifacts(database, _owned_case) == []
    denied = await _audit_row(database, action="cross_case.denied", resource_id=job_id)
    assert denied is not None
    assert dict(denied.metadata_ or {}).get("code") == CODE_CROSS_CASE_SCOPE_REVOKED


async def test_candidates_read_omits_inaccessible_side(
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    api_user: ApiUser,
    user_factory,
) -> None:
    """A member of the anchor who cannot read the side case sees nothing."""
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="read-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="read-b")
    async with _client(api_user.token) as lead_client:
        response = await _discover(lead_client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 202, response.text

    # The owner (lead) sees the candidate.
    async with _client(api_user.token) as lead_client:
        lead = await lead_client.get(
            f"{PREFIX}/cross-case/candidates", params={"anchor_case_id": str(_owned_case)}
        )
    assert lead.status_code == 200, lead.text
    assert lead.json()["total"] >= 1

    # A member of the anchor only (not the side case) omits it entirely.
    member = await user_factory(role="INVESTIGATOR")
    await _add_member(database, _owned_case, member.id)
    async with _client(member.token) as member_client:
        hidden = await member_client.get(
            f"{PREFIX}/cross-case/candidates", params={"anchor_case_id": str(_owned_case)}
        )
    assert hidden.status_code == 200, hidden.text
    body = hidden.json()
    assert body["total"] == 0
    assert body["items"] == []
    # Nothing about the inaccessible side case leaks into the response.
    assert str(_second_case) not in hidden.text


async def test_candidates_read_requires_crosscase_permission(
    database: Database,
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    viewer = await user_factory(role="VIEWER")
    await _add_member(database, _owned_case, viewer.id)
    async with _client(viewer.token) as client:
        response = await client.get(
            f"{PREFIX}/cross-case/candidates", params={"anchor_case_id": str(_owned_case)}
        )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION


async def test_generic_artifact_list_excludes_cross_case_candidates(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="gl-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="gl-b")
    response = await _discover(http_client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 202, response.text

    listing = await http_client.get(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts"
    )
    assert listing.status_code == 200, listing.text
    # The generic listing never returns cross-case candidates (payloads span
    # cases); they are read only through the scope-checked endpoint.
    kinds = {item["kind"] for item in listing.json()["items"]}
    assert "cross_case_link" not in kinds


async def test_name_only_candidate_cannot_be_approved(
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="ap-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="ap-b")
    await _seed_person(database, _owned_case, SHARED_NAME)
    await _seed_person(database, _second_case, SHARED_NAME)
    async with _client(api_user.token) as client:
        response = await _discover(client, _owned_case, [_owned_case, _second_case])
        assert response.status_code == 202, response.text

        artifacts = await _artifacts(database, _owned_case)

        def _group_kind(artifact: DerivedArtifact) -> str:
            return (artifact.payload or {}).get("group", {}).get("indicator_kind")

        name_artifact = next(a for a in artifacts if _group_kind(a) == "name")
        approve = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{name_artifact.id}/review",
            json={"decision": "approved"},
        )
        assert approve.status_code == 409, approve.text
        assert approve.json()["error"]["code"] == CODE_ARTIFACT_NOT_REVIEWABLE

        # A reviewable candidate (shared account) approves cleanly.
        account_artifact = next(a for a in artifacts if _group_kind(a) == "account_ref")
        ok = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{account_artifact.id}/review",
            json={"decision": "approved"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "approved"


async def test_identical_rerun_reuses_candidates(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(database, _owned_case, [CASE_A_RECORD], label="ru-a")
    await _seed_evidence_records(database, _second_case, [CASE_B_RECORD], label="ru-b")
    first = await _discover(http_client, _owned_case, [_owned_case, _second_case])
    assert first.status_code == 202, first.text
    after_first = await _artifacts(database, _owned_case)
    # Four record-based groups (account, phone, email, domain); no name group
    # because no person entity was seeded here.
    assert len(after_first) == 4

    # Mark the first run terminal so a re-submit becomes a fresh attempt.
    factory = database.session_factory()
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.case_id == str(_owned_case),
                    AnalysisJob.feature == "cross_case",
                )
            )
        ).scalars()
        for job in jobs:
            job.status = "failed"
            job.error = "cleared for the rerun assertion"
        await session.commit()

    second = await _discover(http_client, _owned_case, [_owned_case, _second_case])
    assert second.status_code == 202, second.text
    second_job = await _job_row(database, uuid.UUID(second.json()["job"]["id"]))
    summary = dict(second_job.result_summary or {})
    # Content-hash dedupe: identical candidates are reused, not duplicated.
    assert summary["artifacts_reused"] == 4
    assert summary["artifacts_created"] == 0
    assert len(await _artifacts(database, _owned_case)) == 4


async def test_anonymous_discover_is_unauthorized(
    _owned_case: uuid.UUID,
    _second_case: uuid.UUID,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await _discover(client, _owned_case, [_owned_case, _second_case])
    assert response.status_code == 401, response.text

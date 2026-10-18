"""API contract tests for the phase-3 case-intelligence features.

Feature A (entity-pair resolution), Feature B (timeline reconstruction) and
Feature C (contradiction detection):

- submit -> 202 + one active job per feature (typed 409 while one runs) and
  honest stale clearing with attempt-numbered retry keys;
- reviewable derived artifacts with full provenance (never auto-applied);
- approval of an entity candidate adds audited, additive aliases and never
  merges (false-merge rate zero by construction);
- committing an approved timeline proposal is idempotent and refuses
  proposals without an established timestamp;
- contradiction resolution states are appended child artifacts, never a
  rewrite of the candidate or the evidence;
- cancellation of a queued run leaves it terminal with zero artifacts;
- every path enforces authentication, membership and role permissions.

Background tasks run to completion before the ASGI call returns, so each
test asserts the terminal job/artifact state right after the POST resolves.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from app.core.codes import (
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_ARTIFACT_NOT_FOUND,
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_CANDIDATE_ENTITY_UNAVAILABLE,
    CODE_CASE_READ_ONLY,
    CODE_CONTRADICTION_ACTIVE,
    CODE_CONTRADICTION_STATE_INVALID,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_JOB_TERMINAL,
    CODE_PROPOSAL_NOT_APPROVED,
    CODE_RECONSTRUCTION_ACTIVE,
    CODE_RESOLUTION_ACTIVE,
    CODE_REVIEW_NOTE_REQUIRED,
    CODE_TIMELINE_TIMESTAMP_MISSING,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app as shared_app
from app.models import (
    AnalysisJob,
    AuditLog,
    Case,
    CaseMember,
    DerivedArtifact,
    Entity,
    EntityAlias,
    EvidenceFile,
    SourceRecord,
    TimelineEvent,
)
from app.services import (
    contradiction_detection as contradiction_svc,
)
from app.services import (
    entity_matching as resolution_svc,
)
from app.services import (
    timeline_reconstruction as reconstruction_svc,
)
from app.services.normalization import blocking_key, normalize_value
from sqlalchemy import delete, select

from tests.api.conftest import ApiUser
from tests.api.phase2_fakes import FakeAI

PREFIX = get_settings().API_V1_PREFIX

# Two person pairs, deliberately in different similarity bands:
# - Priya Sharma / Priya Sharmaa: 96.0 -> strong band (deterministic only);
# - Amit Mehta / Anil Mehta: 80.0 -> ambiguous band (LLM-eligible advisory).
# - Suresh Patel / Suresh Patil: 91.67 -> ambiguous band (LLM-eligible).
STRONG_A = "Priya Sharma"
STRONG_B = "Priya Sharmaa"
AMBIGUOUS_A = "Amit Mehta"
AMBIGUOUS_B = "Anil Mehta"
AMBIGUOUS_C = "Suresh Patel"
AMBIGUOUS_D = "Suresh Patil"

NOTE_A = (
    "The account holder stated that the transfer was initiated from the "
    "branch counter on Monday afternoon"
)
NOTE_B = (
    "The account holder stated that no transfer was ever initiated by "
    "them from any branch at any time"
)
NOTE_C = (
    "The account holder confirmed the transfer was requested by phone and "
    "later cancelled before any money left the account"
)

# -- helpers ----------------------------------------------------------------------


def _wire_app() -> None:
    """Attach infrastructure clients for requests built outside http_client."""
    settings = get_settings()
    shared_app.state.database = Database(settings)
    shared_app.state.settings = settings


def _review_body(note: str, decision: str = "approved") -> dict[str, str]:
    return {"decision": decision, "note": note}


def _codes(artifact: DerivedArtifact) -> set[str]:
    return {str(err.get("code")) for err in (artifact.validation_errors or [])}


async def _seed_person(database: Database, case_id: uuid.UUID, name: str) -> uuid.UUID:
    normalized = normalize_value("person", name)
    assert normalized.is_valid, name
    factory = database.session_factory()
    async with factory() as session:
        entity = Entity(
            case_id=str(case_id),
            entity_type="person",
            canonical_value=normalized.canonical,
            blocking_key=blocking_key("person", normalized.canonical),
            display_value=normalized.display,
            status="active",
        )
        session.add(entity)
        await session.commit()
        return uuid.UUID(str(entity.id))


async def _seed_evidence_records(
    database: Database,
    case_id: uuid.UUID,
    records: list[dict[str, object]],
    *,
    label: str,
) -> uuid.UUID:
    """Insert one evidence file plus its parsed source records (no storage).

    Timeline reconstruction and contradiction detection read ``raw_data``
    straight from the database, so no object-store round trip is needed.
    """
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


async def _seed_job(
    database: Database,
    case_id: uuid.UUID,
    *,
    feature: str,
    status: str = "running",
    actor_id: uuid.UUID,
    created_at: datetime | None = None,
    cancel_requested: bool = False,
) -> uuid.UUID:
    factory = database.session_factory()
    async with factory() as session:
        job = AnalysisJob(
            case_id=str(case_id),
            feature=feature,
            status=status,
            idempotency_key=f"seed-{feature}-{uuid.uuid4().hex[:8]}",
            attempts=1,
            timeout_seconds=300,
            cancel_requested=cancel_requested,
            actor_id=str(actor_id),
        )
        if created_at is not None:
            job.created_at = created_at
        session.add(job)
        await session.commit()
        return job.id


async def _artifacts(database: Database, case_id: uuid.UUID, *, kind: str) -> list[DerivedArtifact]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(DerivedArtifact).where(
                DerivedArtifact.case_id == str(case_id),
                DerivedArtifact.kind == kind,
            )
        )
        return list(rows.scalars())


async def _candidates(database: Database, case_id: uuid.UUID) -> list[DerivedArtifact]:
    """Contradiction candidates only (excludes appended resolution children)."""
    return [
        a
        for a in await _artifacts(database, case_id, kind="contradiction")
        if (a.payload or {}).get("type") == "contradiction"
    ]


async def _job_row(database: Database, job_id: uuid.UUID) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None, f"job {job_id} not found"
        return job


async def _audit_row(
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


async def _submit(client: httpx.AsyncClient, case_id: uuid.UUID, path: str) -> httpx.Response:
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/{path}",
        json={},
    )


# -- feature A: entity-pair resolution --------------------------------------------


async def test_entity_resolution_proposes_reviewable_candidate_with_provenance(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)

    response = await _submit(http_client, _owned_case, "entity-resolution")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "entity_resolution"

    job_id = uuid.UUID(body["job"]["id"])
    job = await _job_row(database, job_id)
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["pairs_proposed"] == 1
    # A strong name match needs no model; the deterministic path owns it.
    assert summary["pairs_llm"] == 0

    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.status == "pending_review"
    assert artifact.origin == "deterministic"
    # A name-only match is visibly unverified, never presented as safe.
    assert artifact.validation_status == "flagged"
    assert _codes(artifact) == {"no_identifier_evidence"}

    payload = dict(artifact.payload or {})
    assert payload["type"] == "entity_candidate"
    assert payload["method"] == "name_similarity"
    assert payload["score_band"] == "strong"
    assert "not a probability" in str(payload["score_semantics"])
    assert payload["name_similarity"] == 96.0

    # Full provenance: job, content hash, parser and both source entities.
    assert str(artifact.analysis_job_id) == str(job_id)
    assert artifact.content_hash
    assert artifact.parser_version.startswith("entity_match:")
    locator = dict(artifact.source_locator or {})
    assert set(locator) == {"entity_a", "entity_b"}
    assert {locator["entity_a"], locator["entity_b"]} == {
        str(entity_a),
        str(entity_b),
    }
    assert str(artifact.created_by) == str(api_user.id)


async def test_entity_resolution_approval_adds_additive_aliases_never_merges(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)

    submit = await _submit(http_client, _owned_case, "entity-resolution")
    assert submit.status_code == 202, submit.text
    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("cross-check confirmed by phone records"),
    )
    assert approve.status_code == 200, approve.text

    factory = database.session_factory()
    async with factory() as session:
        aliases = list(
            (
                await session.execute(
                    select(EntityAlias).where(
                        EntityAlias.entity_id.in_([str(entity_a), str(entity_b)])
                    )
                )
            ).scalars()
        )
        by_entity: dict[str, set[tuple[str, str]]] = {}
        for alias in aliases:
            by_entity.setdefault(str(alias.entity_id), set()).add(
                (alias.alias_value, alias.alias_type)
            )
        # Each entity gains the other's canonical value as a reviewed alias.
        assert ("priya sharmaa", "resolution") in by_entity[str(entity_a)]
        assert ("priya sharma", "resolution") in by_entity[str(entity_b)]

        # Approval is additive: entities are never merged or rewritten.
        entities = list(
            (
                await session.execute(
                    select(Entity).where(Entity.id.in_([str(entity_a), str(entity_b)]))
                )
            ).scalars()
        )
        assert {e.canonical_value for e in entities} == {"priya sharma", "priya sharmaa"}
        assert all(e.status == "active" for e in entities)
        assert all(e.merged_into_id is None for e in entities)

    audit = await _audit_row(database, action="derived_artifact.approved", resource_id=artifact.id)
    assert audit is not None
    metadata = dict(audit.metadata_ or {})
    assert metadata.get("aliases_added") == 2
    assert {metadata.get("entity_a_id"), metadata.get("entity_b_id")} == {
        str(entity_a),
        str(entity_b),
    }


async def test_entity_resolution_rejection_adds_no_aliases_and_is_one_shot(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    entity_b = await _seed_person(database, _owned_case, STRONG_B)
    await _submit(http_client, _owned_case, "entity-resolution")
    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    artifact = artifacts[0]

    reject = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("distinct people, different branches", decision="rejected"),
    )
    assert reject.status_code == 200, reject.text

    factory = database.session_factory()
    async with factory() as session:
        aliases = list(
            (
                await session.execute(
                    select(EntityAlias).where(
                        EntityAlias.entity_id.in_([str(entity_a), str(entity_b)])
                    )
                )
            ).scalars()
        )
        assert aliases == []

    # Review decisions are one-shot: no flip-flopping without a new derivation.
    repeat = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("changed my mind"),
    )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == CODE_ARTIFACT_NOT_REVIEWABLE


async def test_entity_resolution_stale_candidate_approval_is_refused(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    entity_a = await _seed_person(database, _owned_case, STRONG_A)
    await _seed_person(database, _owned_case, STRONG_B)
    await _submit(http_client, _owned_case, "entity-resolution")
    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1

    factory = database.session_factory()
    async with factory() as session:
        stale = await session.get(Entity, str(entity_a))
        assert stale is not None
        await session.delete(stale)
        await session.commit()

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifacts[0].id}/review",
        json=_review_body("approving after evidence deletion"),
    )
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == CODE_CANDIDATE_ENTITY_UNAVAILABLE


async def test_entity_resolution_llm_verdict_is_advisory_only(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    entity_a = await _seed_person(database, _owned_case, AMBIGUOUS_A)
    entity_b = await _seed_person(database, _owned_case, AMBIGUOUS_B)
    phase2_fake_ai.pair_replies = [
        json.dumps({"verdict": "same", "reason": "same surname, same branch records"}),
    ]

    submit = await _submit(http_client, _owned_case, "entity-resolution")
    assert submit.status_code == 202, submit.text
    job = await _job_row(database, uuid.UUID(submit.json()["job"]["id"]))
    summary = dict(job.result_summary or {})
    assert summary["pairs_llm"] == 1
    assert summary["pairs_llm_invalid"] == 0

    # The model only ever sees facts; entity ids are never handed over.
    assert len(phase2_fake_ai.pair_calls) == 1
    dumped_call = json.dumps(phase2_fake_ai.pair_calls[0])
    assert str(entity_a) not in dumped_call
    assert str(entity_b) not in dumped_call

    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]
    payload = dict(artifact.payload or {})
    assert payload["llm"]["verdict"] == "same"
    # Advisory only: still a flagged, human-reviewable proposal.
    assert artifact.status == "pending_review"
    assert artifact.origin == "llm"
    assert artifact.validation_status == "flagged"
    assert "ai_unverified" in _codes(artifact)


async def test_entity_resolution_llm_reply_with_echoed_ids_is_discarded(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    await _seed_person(database, _owned_case, AMBIGUOUS_C)
    await _seed_person(database, _owned_case, AMBIGUOUS_D)
    # Extra key (an echoed id) breaks the strict schema -> reply discarded.
    phase2_fake_ai.pair_replies = [
        json.dumps({"verdict": "same", "reason": "ok", "entity_a": str(uuid.uuid4())}),
    ]

    submit = await _submit(http_client, _owned_case, "entity-resolution")
    assert submit.status_code == 202, submit.text
    job = await _job_row(database, uuid.UUID(submit.json()["job"]["id"]))
    summary = dict(job.result_summary or {})
    assert summary["pairs_llm"] == 0
    assert summary["pairs_llm_invalid"] == 1

    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1
    artifact = artifacts[0]
    payload = dict(artifact.payload or {})
    # The unusable reply leaves the deterministic proposal intact.
    assert "llm" not in payload
    assert artifact.origin == "deterministic"
    assert "ai_unverified" not in _codes(artifact)


async def test_entity_resolution_refuses_while_active_and_clears_stale_jobs(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    await _seed_person(database, _owned_case, STRONG_A)
    await _seed_person(database, _owned_case, STRONG_B)

    active = await _seed_job(
        database,
        _owned_case,
        feature="entity_resolution",
        status="running",
        actor_id=api_user.id,
    )
    refused = await _submit(http_client, _owned_case, "entity-resolution")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == CODE_RESOLUTION_ACTIVE

    # Stale pending jobs (past 2x timeout) are honestly cleared, not ignored.
    factory = database.session_factory()
    async with factory() as session:
        stale = await session.get(AnalysisJob, str(active))
        assert stale is not None
        stale.status = "pending"
        stale.created_at = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()

    retry = await _submit(http_client, _owned_case, "entity-resolution")
    assert retry.status_code == 202, retry.text
    assert retry.json()["job"]["idempotency_key"].endswith(":a2")

    cleared = await _job_row(database, active)
    assert cleared.status == "canceled"


async def test_entity_resolution_retry_does_not_duplicate_artifacts(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_person(database, _owned_case, STRONG_A)
    await _seed_person(database, _owned_case, STRONG_B)

    first = await _submit(http_client, _owned_case, "entity-resolution")
    assert first.status_code == 202, first.text
    first_job = await _job_row(database, uuid.UUID(first.json()["job"]["id"]))
    assert first_job.status == "succeeded"

    second = await _submit(http_client, _owned_case, "entity-resolution")
    assert second.status_code == 202, second.text
    assert second.json()["job"]["idempotency_key"].endswith(":a2")
    second_job = await _job_row(database, uuid.UUID(second.json()["job"]["id"]))
    second_summary = dict(second_job.result_summary or {})
    # Content-hash dedupe: the retry reuses instead of re-creating.
    assert second_summary["artifacts_reused"] >= 1
    assert second_summary["artifacts_created"] == 0

    artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(artifacts) == 1


# -- feature B: timeline reconstruction -------------------------------------------


async def test_timeline_reconstruction_preserves_originals_and_flags_gaps(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_date": "2026-03-15", "txn_id": "TXN-1"},  # date-only granularity
            {"incident_at": "15/03/2026 14:30"},  # naive -> tz assumed
            {"payment_date": "TBD"},  # strong field, unparseable -> missing
        ],
        label="timeline-seed",
    )

    submit = await _submit(http_client, _owned_case, "timeline-reconstruction")
    assert submit.status_code == 202, submit.text
    job = await _job_row(database, uuid.UUID(submit.json()["job"]["id"]))
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["proposals_recorded"] == 3
    assert summary["missing_timestamps"] == 1
    assert summary["ambiguous_timezones"] == 1

    artifacts = await _artifacts(database, _owned_case, kind="timeline_proposal")
    assert len(artifacts) == 3
    by_original: dict[str, DerivedArtifact] = {}
    for artifact in artifacts:
        payload = dict(artifact.payload or {})
        assert payload["type"] == "timeline_proposal"
        assert artifact.source_locator is not None
        assert payload["proposal_key"]
        by_original[str(payload["original_timestamp"])] = artifact

    date_only = dict(by_original["2026-03-15"].payload or {})
    assert date_only["occurred_at"] == "2026-03-15T00:00:00+00:00"
    assert date_only["time_granularity"] == "date"
    assert date_only["tz_assumed"] is False
    assert date_only["time_semantics"] == "record_occurs_on"
    assert _codes(by_original["2026-03-15"]) == set()

    naive = dict(by_original["15/03/2026 14:30"].payload or {})
    assert naive["tz_assumed"] is True
    assert naive["tz"] is None  # no explicit zone: unknown, not invented
    assert naive["occurred_at"].startswith("2026-03-15T14:30")
    assert _codes(by_original["15/03/2026 14:30"]) == {"ambiguous_timezone"}
    assert by_original["15/03/2026 14:30"].validation_status == "flagged"

    missing = dict(by_original["TBD"].payload or {})
    assert missing["missing_timestamp"] is True
    assert missing["occurred_at"] is None
    assert missing["time_granularity"] is None
    assert _codes(by_original["TBD"]) == {"missing_timestamp"}


async def test_timeline_commit_is_idempotent_and_refuses_unapproved(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [{"txn_date": "2026-03-15", "txn_id": "TXN-1"}],
        label="commit-seed",
    )
    submit = await _submit(http_client, _owned_case, "timeline-reconstruction")
    assert submit.status_code == 202, submit.text
    artifacts = await _artifacts(database, _owned_case, kind="timeline_proposal")
    assert len(artifacts) == 1
    artifact = artifacts[0]

    # Committing an unapproved proposal is refused.
    early = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{artifact.id}/commit",
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == CODE_PROPOSAL_NOT_APPROVED

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact.id}/review",
        json=_review_body("matches the bank statement"),
    )
    assert approve.status_code == 200, approve.text

    commit = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{artifact.id}/commit",
    )
    assert commit.status_code == 200, commit.text
    commit_body = commit.json()
    assert commit_body["duplicate"] is False
    event_id = commit_body["event"]["id"]
    assert commit_body["event"]["kind"] == "case_event"
    event_payload = dict(commit_body["event"]["payload"] or {})
    assert event_payload["origin"] == "timeline_reconstruction"
    assert event_payload["proposal_artifact_id"] == str(artifact.id)
    assert event_payload["proposal_key"] == (artifact.payload or {}).get("proposal_key")
    assert event_payload["original_timestamp"] == "2026-03-15"

    # A retry returns the already-committed event instead of a second row.
    repeat = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{artifact.id}/commit",
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["duplicate"] is True
    assert repeat.json()["event"]["id"] == event_id

    factory = database.session_factory()
    async with factory() as session:
        events = list(
            (
                await session.execute(
                    select(TimelineEvent).where(TimelineEvent.case_id == str(_owned_case))
                )
            ).scalars()
        )
        assert len(events) == 1
        assert events[0].id == uuid.UUID(event_id)

    # The rerun marks the committed proposal as skipped and records nothing new.
    rerun = await _submit(http_client, _owned_case, "timeline-reconstruction")
    assert rerun.status_code == 202, rerun.text
    rerun_job = await _job_row(database, uuid.UUID(rerun.json()["job"]["id"]))
    rerun_summary = dict(rerun_job.result_summary or {})
    assert rerun_summary["proposals_committed_skipped"] == 1
    assert rerun_summary["proposals_recorded"] == 0

    async with factory() as session:
        events_after = list(
            (
                await session.execute(
                    select(TimelineEvent).where(TimelineEvent.case_id == str(_owned_case))
                )
            ).scalars()
        )
        assert len(events_after) == 1


async def test_timeline_commit_typed_refusals(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"payment_date": "TBD", "txn_id": "TXN-9"},
            {"txn_id": "TXN-9", "txn_amount": "1500", "currency": "INR"},
            {"txn_id": "TXN-9", "txn_amount": "2500", "currency": "INR"},
        ],
        label="refusals-seed",
    )
    await _submit(http_client, _owned_case, "timeline-reconstruction")
    proposals = await _artifacts(database, _owned_case, kind="timeline_proposal")
    assert len(proposals) == 1
    proposal = proposals[0]

    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{proposal.id}/review",
        json=_review_body("approve for completeness"),
    )
    assert approve.status_code == 200, approve.text

    # No established timestamp -> typed 422, never an invented instant.
    commit = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{proposal.id}/commit",
    )
    assert commit.status_code == 422
    assert commit.json()["error"]["code"] == CODE_TIMELINE_TIMESTAMP_MISSING

    # An unknown artifact simply does not resolve (case-scoped lookup).
    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{uuid.uuid4()}/commit",
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_ARTIFACT_NOT_FOUND

    # A contradiction candidate is not a timeline proposal.
    await _submit(http_client, _owned_case, "contradiction-detection")
    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    wrong_kind = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"timeline-proposals/{candidates[0].id}/commit",
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["error"]["code"] == CODE_ARTIFACT_KIND_UNSUPPORTED


# -- feature C: contradiction detection -------------------------------------------


async def test_contradiction_detection_proposes_anchored_candidate_with_alternatives(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-9001", "txn_amount": "1500", "currency": "INR"},
            {"txn_id": "TXN-9001", "txn_amount": "2500", "currency": "INR"},
            # Same shape, different anchor: unrelated records are never compared.
            {"txn_id": "TXN-9002", "txn_amount": "9999", "currency": "INR"},
        ],
        label="conflict-seed",
    )

    submit = await _submit(http_client, _owned_case, "contradiction-detection")
    assert submit.status_code == 202, submit.text
    job = await _job_row(database, uuid.UUID(submit.json()["job"]["id"]))
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["conflicts"] == 1

    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    artifact = candidates[0]
    assert artifact.status == "pending_review"
    assert artifact.origin == "deterministic"
    assert artifact.validation_status == "valid"

    payload = dict(artifact.payload or {})
    assert payload["category"] == "amount"
    assert payload["priority"] == "high"
    assert payload["rule"].startswith("contradiction.")
    assert payload["rule_version"]
    assert payload["anchor"]["value"] == "txn9001"
    assert payload["anchor"]["scope"] == "transaction"
    assert len(payload["alternatives"]) >= 2
    assert payload["explanation"]

    values = payload["conflicting_values"]
    assert isinstance(values, list) and len(values) == 1
    # Pair ordering is not guaranteed, so compare the value set.
    assert {values[0]["first"], values[0]["second"]} == {"1500", "2500"}
    assert {values[0]["first_original"], values[0]["second_original"]} == {
        "1500",
        "2500",
    }


async def test_contradiction_resolution_states_are_appended_child_artifacts(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-9001", "txn_amount": "1500", "currency": "INR"},
            {"txn_id": "TXN-9001", "txn_amount": "2500", "currency": "INR"},
        ],
        label="resolve-seed",
    )
    submit = await _submit(http_client, _owned_case, "contradiction-detection")
    assert submit.status_code == 202, submit.text
    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    candidate = candidates[0]
    original_hash = candidate.content_hash
    original_payload = json.dumps(candidate.payload, sort_keys=True)

    for state in ("explained", "requires_evidence", "deferred"):
        response = await http_client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
            f"contradictions/{candidate.id}/resolve",
            json={"state": state, "note": f"reviewer recorded {state}"},
        )
        assert response.status_code == 200, response.text
        child = response.json()
        assert child["status"] == "recorded"
        assert child["kind"] == "contradiction"
        assert child["parent_artifact_id"] == str(candidate.id)
        child_payload = dict(child["payload"] or {})
        assert child_payload["type"] == "contradiction_review"
        assert child_payload["state"] == state
        assert child_payload["note"] == f"reviewer recorded {state}"
        assert child_payload["for_artifact_id"] == str(candidate.id)

    # The candidate itself is never rewritten by a resolution state.
    factory = database.session_factory()
    async with factory() as session:
        current = await session.get(DerivedArtifact, str(candidate.id))
        assert current is not None
        assert current.status == "pending_review"
        assert current.content_hash == original_hash
        assert json.dumps(current.payload, sort_keys=True) == original_payload
        assert (current.payload or {}).get("type") == "contradiction"

    invalid = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{candidate.id}/resolve",
        json={"state": "rejected", "note": "not a valid state"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == CODE_CONTRADICTION_STATE_INVALID

    empty_note = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{candidate.id}/resolve",
        json={"state": "deferred", "note": "   "},
    )
    assert empty_note.status_code == 422
    assert empty_note.json()["error"]["code"] == CODE_REVIEW_NOTE_REQUIRED

    # Confirmed / false positive stay the one-shot review on the shared router.
    approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{candidate.id}/review",
        json=_review_body("both statements verified against the ledger"),
    )
    assert approve.status_code == 200, approve.text
    after_approve = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{candidate.id}/resolve",
        json={"state": "deferred", "note": "too late"},
    )
    assert after_approve.status_code == 409
    assert after_approve.json()["error"]["code"] == CODE_ARTIFACT_NOT_REVIEWABLE

    repeat_review = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{candidate.id}/review",
        json=_review_body("flip"),
    )
    assert repeat_review.status_code == 409
    assert repeat_review.json()["error"]["code"] == CODE_ARTIFACT_NOT_REVIEWABLE


async def test_contradiction_resolve_typed_errors_and_kind_guard(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-1", "txn_amount": "10", "currency": "INR"},
            {"txn_id": "TXN-1", "txn_amount": "20", "currency": "INR"},
        ],
        label="kinds-seed",
    )
    await _seed_person(database, _owned_case, STRONG_A)
    await _seed_person(database, _owned_case, STRONG_B)
    await _submit(http_client, _owned_case, "contradiction-detection")
    await _submit(http_client, _owned_case, "entity-resolution")
    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    candidate_id = candidates[0].id

    unknown = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{uuid.uuid4()}/resolve",
        json={"state": "deferred", "note": "ghost"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CODE_ARTIFACT_NOT_FOUND

    # An entity candidate is not a contradiction.
    entity_artifacts = await _artifacts(database, _owned_case, kind="entity_resolution")
    assert len(entity_artifacts) == 1
    wrong_kind = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
        f"contradictions/{entity_artifacts[0].id}/resolve",
        json={"state": "deferred", "note": "wrong kind"},
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["error"]["code"] == CODE_ARTIFACT_KIND_UNSUPPORTED

    # A resolution child is lineage, not a fresh candidate.
    first = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{candidate_id}/resolve",
        json={"state": "deferred", "note": "pending lab report"},
    )
    assert first.status_code == 200, first.text
    child_id = first.json()["id"]
    child_again = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/contradictions/{child_id}/resolve",
        json={"state": "deferred", "note": "again"},
    )
    assert child_again.status_code == 422
    assert child_again.json()["error"]["code"] == CODE_ARTIFACT_KIND_UNSUPPORTED


async def test_contradiction_semantic_llm_candidate_is_flagged_never_confirmed(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    phase2_fake_ai: FakeAI,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-777", "notes": NOTE_A},
            {"txn_id": "TXN-777", "notes": NOTE_B},
        ],
        label="semantic-seed",
    )
    agree_reply = json.dumps({"contradicts": False, "explanation": "no conflict"})
    phase2_fake_ai.statement_replies = [
        json.dumps({"contradicts": True, "explanation": "the two statements differ"}),
        agree_reply,
    ]

    submit = await _submit(http_client, _owned_case, "contradiction-detection")
    assert submit.status_code == 202, submit.text
    job = await _job_row(database, uuid.UUID(submit.json()["job"]["id"]))
    summary = dict(job.result_summary or {})
    assert summary["semantic_llm"] == 1

    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    candidate = candidates[0]
    payload = dict(candidate.payload or {})
    assert payload["category"] == "semantic"
    assert payload["priority"] == "low"
    assert payload["llm"]["contradicts"] is True
    assert payload["llm"]["explanation"]
    # Never a confirmation: flagged, unverified and awaiting a human.
    assert candidate.origin == "llm"
    assert candidate.validation_status == "flagged"
    assert candidate.status == "pending_review"
    assert "ai_unverified" in _codes(candidate)
    # The model only saw the statement text and the anchor value.
    assert phase2_fake_ai.statement_calls[0]["anchor"] == "txn777"

    # A "does not contradict" verdict yields no candidate at all.
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-778", "notes": NOTE_A},
            {"txn_id": "TXN-778", "notes": NOTE_C},
        ],
        label="semantic-agree",
    )
    agree = await _submit(http_client, _owned_case, "contradiction-detection")
    assert agree.status_code == 202, agree.text
    agree_job = await _job_row(database, uuid.UUID(agree.json()["job"]["id"]))
    agree_summary = dict(agree_job.result_summary or {})
    assert agree_summary["semantic_skipped"] >= 1
    # Still exactly one candidate: the agreeing pair never became one.
    assert len(await _candidates(database, _owned_case)) == 1


# -- submission lifecycle: active refusal, stale clearing, cancellation ----------


async def test_submissions_refuse_while_active_and_clear_stale_jobs(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    cases = (
        ("entity-resolution", "entity_resolution", CODE_RESOLUTION_ACTIVE),
        ("timeline-reconstruction", "timeline", CODE_RECONSTRUCTION_ACTIVE),
        ("contradiction-detection", "contradiction", CODE_CONTRADICTION_ACTIVE),
    )
    for path, feature, code in cases:
        active = await _seed_job(
            database,
            _owned_case,
            feature=feature,
            status="running",
            actor_id=api_user.id,
        )
        refused = await _submit(http_client, _owned_case, path)
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == code

        # Stale pending jobs (past 2x timeout) are honestly cleared, not ignored.
        factory = database.session_factory()
        async with factory() as session:
            stale = await session.get(AnalysisJob, str(active))
            assert stale is not None
            stale.status = "pending"
            stale.created_at = datetime.now(UTC) - timedelta(hours=2)
            await session.commit()

        cleared = await _submit(http_client, _owned_case, path)
        assert cleared.status_code == 202, cleared.text
        # Attempts are counted per (case, feature): the cleared seed is the
        # first attempt, so the retry is attempt 2 for this feature.
        assert cleared.json()["job"]["idempotency_key"].endswith(":a2"), (
            f"attempt key for {feature}"
        )
        row = await _job_row(database, active)
        assert row.status == "canceled"


async def test_canceled_jobs_never_succeed_and_write_no_artifacts(
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    """A cancel-requested run stops before writing anything."""
    settings = get_settings()
    # Data that a non-canceled run *would* turn into proposals.
    await _seed_person(database, _owned_case, STRONG_A)
    await _seed_person(database, _owned_case, STRONG_B)
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_date": "2026-03-15", "txn_id": "TXN-1"},
            {"txn_id": "TXN-1", "txn_amount": "1500", "currency": "INR"},
            {"txn_id": "TXN-1", "txn_amount": "2500", "currency": "INR"},
        ],
        label="cancel-seed",
    )

    runners = {
        "entity_resolution": (
            "resolution",
            lambda session, job_id: resolution_svc.execute_entity_resolution(
                session, job_id=job_id, settings=settings
            ),
        ),
        "timeline": (
            "reconstruction",
            lambda session, job_id: reconstruction_svc.execute_timeline_reconstruction(
                session, job_id=job_id, settings=settings
            ),
        ),
        "contradiction": (
            "contradiction",
            lambda session, job_id: contradiction_svc.execute_contradiction_detection(
                session, job_id=job_id, settings=settings
            ),
        ),
    }
    for feature, (prefix, runner) in runners.items():
        job_id = await _seed_job(
            database,
            _owned_case,
            feature=feature,
            status="pending",
            actor_id=api_user.id,
            cancel_requested=True,
        )
        factory = database.session_factory()
        async with factory() as session:
            await runner(session, job_id)
            await session.commit()

        job = await _job_row(database, job_id)
        assert job.status == "canceled", feature
        audit = await _audit_row(database, action=f"{prefix}.canceled", resource_id=job_id)
        assert audit is not None, feature

    # No proposals of any kind were left behind by the canceled runs.
    for kind in ("entity_resolution", "timeline_proposal"):
        assert await _artifacts(database, _owned_case, kind=kind) == []
    assert await _candidates(database, _owned_case) == []

    # Cancelling a terminal job is refused with a typed code.
    done = await _seed_job(
        database,
        _owned_case,
        feature="custody",
        status="succeeded",
        actor_id=api_user.id,
    )
    _wire_app()
    transport = httpx.ASGITransport(app=shared_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {api_user.token}"},
    ) as client:
        repeat = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{done}/cancel"
        )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == CODE_JOB_TERMINAL


async def test_cancel_route_requests_cancellation_for_each_phase3_feature(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    for feature, prefix in (
        ("entity_resolution", "resolution"),
        ("timeline", "reconstruction"),
        ("contradiction", "contradiction"),
    ):
        job_id = await _seed_job(
            database,
            _owned_case,
            feature=feature,
            status="pending",
            actor_id=api_user.id,
        )
        response = await http_client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/jobs/{job_id}/cancel"
        )
        assert response.status_code == 200, response.text
        assert response.json()["cancel_requested"] is True
        audit = await _audit_row(database, action=f"{prefix}.cancel_requested", resource_id=job_id)
        assert audit is not None


# -- authorization, read-only and disabled-AI contracts ---------------------------


async def test_phase3_submissions_are_authentication_and_membership_scoped(
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    _wire_app()
    transport = httpx.ASGITransport(app=shared_app)
    paths = (
        "entity-resolution",
        "timeline-reconstruction",
        "contradiction-detection",
    )

    # Anonymous callers are refused outright.
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as anon:
        for path in paths:
            response = await _submit(anon, _owned_case, path)
            assert response.status_code == 401, response.text

    # Authenticated but not a member: the case does not resolve.
    stranger = await user_factory(role="INVESTIGATOR")
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {stranger.token}"},
    ) as client:
        for path in paths:
            response = await _submit(client, _owned_case, path)
            assert response.status_code == 403, response.text


async def test_phase3_writes_require_role_permissions(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-9001", "txn_amount": "1500", "currency": "INR"},
            {"txn_id": "TXN-9001", "txn_amount": "2500", "currency": "INR"},
        ],
        label="perm-seed",
    )
    await _seed_evidence_records(
        database,
        _owned_case,
        [{"txn_date": "2026-03-15", "txn_id": "TXN-2"}],
        label="perm-timeline",
    )
    submit = await _submit(http_client, _owned_case, "contradiction-detection")
    assert submit.status_code == 202, submit.text
    await _submit(http_client, _owned_case, "timeline-reconstruction")
    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    proposals = await _artifacts(database, _owned_case, kind="timeline_proposal")
    assert len(proposals) == 1

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
        # Submits need ingestion.run.
        refused_submit = await _submit(client, _owned_case, "entity-resolution")
        assert refused_submit.status_code == 403
        assert refused_submit.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

        # Commit needs case.update.
        refused_commit = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
            f"timeline-proposals/{proposals[0].id}/commit",
        )
        assert refused_commit.status_code == 403
        assert refused_commit.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

        # Resolve needs findings.review.
        refused_resolve = await client.post(
            f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/"
            f"contradictions/{candidates[0].id}/resolve",
            json={"state": "deferred", "note": "not allowed"},
        )
        assert refused_resolve.status_code == 403
        assert refused_resolve.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == viewer.id))
        await session.commit()


async def test_submissions_are_refused_on_read_only_cases(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, str(_owned_case))
        assert case is not None
        case.status = "closed"
        await session.commit()

    for path in (
        "entity-resolution",
        "timeline-reconstruction",
        "contradiction-detection",
    ):
        response = await _submit(http_client, _owned_case, path)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == CODE_CASE_READ_ONLY


async def test_submissions_run_deterministically_when_ai_disabled(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    monkeypatch,
    phase2_fake_ai: FakeAI,
) -> None:
    """Feature flags gate the LLM only; the deterministic run still proceeds."""
    await _seed_person(database, _owned_case, AMBIGUOUS_A)
    await _seed_person(database, _owned_case, AMBIGUOUS_B)
    await _seed_evidence_records(
        database,
        _owned_case,
        [
            {"txn_id": "TXN-9001", "txn_amount": "1500", "currency": "INR", "notes": NOTE_A},
            {"txn_id": "TXN-9001", "txn_amount": "2500", "currency": "INR", "notes": NOTE_B},
        ],
        label="flag-seed",
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_FEATURE_RESOLUTION", False)
    monkeypatch.setattr(settings, "AI_FEATURE_CONTRADICTION", False)

    entity_submit = await _submit(http_client, _owned_case, "entity-resolution")
    assert entity_submit.status_code == 202, entity_submit.text
    entity_job = await _job_row(database, uuid.UUID(entity_submit.json()["job"]["id"]))
    assert entity_job.status == "succeeded"
    entity_summary = dict(entity_job.result_summary or {})
    assert entity_summary["pairs_llm"] == 0
    assert entity_summary["pairs_llm_skipped"] >= 1
    assert phase2_fake_ai.pair_calls == []

    contradiction_submit = await _submit(http_client, _owned_case, "contradiction-detection")
    assert contradiction_submit.status_code == 202, contradiction_submit.text
    contradiction_job = await _job_row(
        database, uuid.UUID(contradiction_submit.json()["job"]["id"])
    )
    assert contradiction_job.status == "succeeded"
    contradiction_summary = dict(contradiction_job.result_summary or {})
    assert contradiction_summary["semantic_pairs"] == 0
    assert phase2_fake_ai.statement_calls == []

    # The deterministic candidate is still proposed for human review.
    candidates = await _candidates(database, _owned_case)
    assert len(candidates) == 1
    assert candidates[0].origin == "deterministic"

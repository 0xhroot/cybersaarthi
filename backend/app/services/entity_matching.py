"""Phase 3 feature A: entity-pair resolution proposals (deduplication).

The phase-1 ``resolution.py`` pipeline resolves *mentions* into entities
during ingestion. This module does the complementary job: it compares the
already-resolved entities of one case with each other and proposes pairs that
may refer to the same real-world entity - stored as reviewable derived
artifacts, never merged automatically.

Design contract (``docs/ai/PHASE_3_DESIGN.md`` section 3):

- Candidate generation is deterministic and indexed (no all-pairs scan): the
  blocking buckets of ``normalization.blocking_key`` plus exact alias to
  canonical lookups. Because ``entities`` is unique on (case, type, canonical),
  two rows can never share a canonical value - exact matches surface only
  through aliases, and no identifier is ever fabricated to create a pair.
- Only same-type pairs are generated (merging refuses type mismatches anyway).
- Features are transparent per-field signals (name similarity, alias
  equality, shared/conflicting identifier signals, shared source records).
  The stored ``score`` is a 0-100 similarity band label (ADR-006 thresholds),
  never a probability.
- The local LLM is consulted only for ambiguous pairs without exact evidence;
  its verdict is advisory (``ai_unverified``) and lands in a flagged artifact.
  Two people are never identified as the same solely because their names or
  locations match, and pairs whose identifier signals are disjoint are not
  proposed at all.
- Approval never merges entities: ``merge_entities`` has no rollback, so an
  approved match records only the reviewer's acceptance plus additive,
  append-only aliases (searchable both ways). Canonical merging remains its
  own explicit ``entity.merge`` action with its current semantics.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import RESOLUTION_PROMPT_VERSION
from app.core import rbac
from app.core.codes import (
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_CANDIDATE_ENTITY_UNAVAILABLE,
    CODE_CASE_ACCESS_DENIED,
    CODE_INVALID_PAYLOAD,
    CODE_TYPE_MISMATCH,
)
from app.core.config import Settings
from app.models import AnalysisJob, DerivedArtifact, Entity, EntityAlias, EntityCandidate
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services.authorization import still_authorized_for_case
from app.services.normalization import normalize_value
from app.services.structured_extraction import parse_structured

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

RESOLUTION_FEATURE = "entity_resolution"
ENTITY_MATCHER_VERSION = "entity_match:1.0.0"
MODEL_PROFILE = "resolution"

# Entity types whose canonical values act as identity evidence.
IDENTIFIER_TYPES = ("phone", "account", "vehicle", "document")

MAX_PAYLOAD_SOURCE_RECORDS = 20

VALIDATION_MESSAGES: dict[str, str] = {
    "no_identifier_evidence": (
        "no shared identifier or alias; name or context similarity alone "
        "never proves identity"
    ),
    "conflicting_identifiers": (
        "the two entities carry disjoint identifier signals alongside the "
        "matching evidence"
    ),
    "ai_unverified": (
        "an LLM verdict is included; it is unverified and cannot certify identity"
    ),
}


class ResolutionRejected(ValueError):
    """Approval refused; ``code`` carries the typed API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PairResolver(Protocol):
    """The bounded model-call surface the runner needs (AIService implements it)."""

    async def compare_entity_pair(
        self, *, entity_a: dict[str, Any], entity_b: dict[str, Any], features: dict[str, Any]
    ) -> Any: ...


# -- snapshot types (what the pure matching sees) ------------------------------


@dataclass(frozen=True, slots=True)
class EntityFacts:
    """Row-level facts for one entity (no ORM objects in pure rules)."""

    id: str
    entity_type: str
    canonical_value: str
    display_value: str
    blocking_key: str
    status: str
    signals: tuple[str, ...]
    source_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidatePair:
    """One proposed pair with its transparent feature-level evidence."""

    entity_a: EntityFacts
    entity_b: EntityFacts
    method: str
    score: float
    score_band: str
    name_similarity: float
    alias_exact: bool
    matching_fields: tuple[dict[str, object], ...]
    conflicting_fields: tuple[dict[str, object], ...]
    shared_identifiers: tuple[str, ...]
    shared_source_record_ids: tuple[str, ...]
    union_source_record_ids: tuple[str, ...]
    validation_codes: tuple[str, ...]
    llm_eligible: bool

    def as_llm_facts(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Model-facing facts: display values and features only - never ids."""
        entity_a = {
            "entity_type": self.entity_a.entity_type,
            "canonical_value": self.entity_a.canonical_value,
            "display_value": self.entity_a.display_value,
        }
        entity_b = {
            "entity_type": self.entity_b.entity_type,
            "canonical_value": self.entity_b.canonical_value,
            "display_value": self.entity_b.display_value,
        }
        features = {
            "method": self.method,
            "score_band": self.score_band,
            "name_similarity": self.name_similarity,
            "alias_exact": self.alias_exact,
            "shared_identifiers": list(self.shared_identifiers),
            "conflicting_fields": [dict(field) for field in self.conflicting_fields],
        }
        return entity_a, entity_b, features


def _context_signals(context: Mapping[str, object] | None) -> tuple[str, ...]:
    raw = context.get("signals") if context else None
    signals = raw if isinstance(raw, list) else []
    return tuple(s for s in signals if isinstance(s, str))


def build_entity_facts(entity: Entity, source_record_ids: Sequence[str] = ()) -> EntityFacts:
    """ORM row -> immutable matching input (original values never rewritten)."""
    return EntityFacts(
        id=str(entity.id),
        entity_type=entity.entity_type,
        canonical_value=entity.canonical_value,
        display_value=entity.display_value,
        blocking_key=entity.blocking_key,
        status=entity.status,
        signals=_context_signals(entity.context),
        source_record_ids=tuple(sorted({str(r) for r in source_record_ids})),
    )


def _identifier_signals(
    entity: EntityFacts, identifier_map: Mapping[str, str]
) -> tuple[str, ...]:
    """Context signals that resolve (by deterministic normalization) to an
    identifier entity of this case: co-mentions of phones/accounts/vehicles/
    documents, never values invented here."""
    out: list[str] = []
    for signal in entity.signals:
        for id_type in IDENTIFIER_TYPES:
            normalized = normalize_value(id_type, signal)
            if normalized.is_valid and normalized.canonical in identifier_map:
                out.append(normalized.canonical)
                break
    return tuple(sorted(set(out)))


# -- pure candidate generation -------------------------------------------------


def build_candidate_pairs(
    entities: Sequence[EntityFacts],
    alias_values: Mapping[str, Sequence[str]],
    *,
    auto_threshold: float,
    review_threshold: float,
    max_per_bucket: int,
    max_pairs: int,
) -> tuple[list[CandidatePair], dict[str, int]]:
    """Generate and score candidate pairs between resolved entities.

    Deterministic and bounded: exact-value index (alias to canonical) and
    blocking buckets, deduplicated, then scored with transparent features.
    Returns the proposed pairs (sorted) and honest counters for everything
    generated, rejected or capped.
    """
    counts: dict[str, int] = {
        "pairs_from_exact": 0,
        "pairs_from_blocking": 0,
        "pairs_generated": 0,
        "pairs_proposed": 0,
        "pairs_rejected_conflicting_identifiers": 0,
        "pairs_rejected_weak_similarity": 0,
        "pairs_capped": 0,
    }
    by_id = {e.id: e for e in entities}
    identifier_map = {
        e.canonical_value: e.entity_type for e in entities if e.entity_type in IDENTIFIER_TYPES
    }

    # Probe 1: exact alias/canonical equality (per type, normalized).
    exact_index: dict[tuple[str, str], set[str]] = {}
    for entity in entities:
        values = [entity.canonical_value, *alias_values.get(entity.id, ())]
        for raw in values:
            normalized = normalize_value(entity.entity_type, raw)
            if not normalized.is_valid:
                continue
            exact_index.setdefault((entity.entity_type, normalized.canonical), set()).add(
                entity.id
            )

    # Probe 2: blocking buckets.
    buckets: dict[tuple[str, str], list[str]] = {}
    for entity in entities:
        buckets.setdefault((entity.entity_type, entity.blocking_key), []).append(entity.id)

    seen: set[frozenset[str]] = set()
    # (id_a, id_b, matched_value, from_exact) with id_a < id_b for stability.
    raw_pairs: list[tuple[str, str, str | None, bool]] = []
    for key in sorted(exact_index):
        ids = sorted(exact_index[key])
        for index, id_a in enumerate(ids):
            for id_b in ids[index + 1 :]:
                pair = frozenset((id_a, id_b))
                if pair in seen:
                    continue
                seen.add(pair)
                raw_pairs.append((id_a, id_b, key[1], True))
                counts["pairs_from_exact"] += 1
    for key in sorted(buckets):
        ids = sorted(buckets[key])
        generated = 0
        stop = False
        for index, id_a in enumerate(ids):
            for id_b in ids[index + 1 :]:
                if generated >= max_per_bucket:
                    stop = True
                    break
                pair = frozenset((id_a, id_b))
                if pair in seen:
                    continue
                seen.add(pair)
                raw_pairs.append((id_a, id_b, None, False))
                counts["pairs_from_blocking"] += 1
                generated += 1
            if stop:
                break
    counts["pairs_generated"] = len(raw_pairs)

    proposed: list[CandidatePair] = []
    evaluated = 0
    for id_a, id_b, matched_value, from_exact in raw_pairs:
        if len(proposed) >= max_pairs:
            break
        evaluated += 1
        entity_a, entity_b = by_id[id_a], by_id[id_b]
        name_similarity = round(
            float(fuzz.ratio(entity_a.canonical_value, entity_b.canonical_value)), 2
        )
        id_a_signals = set(_identifier_signals(entity_a, identifier_map))
        id_b_signals = set(_identifier_signals(entity_b, identifier_map))
        shared_identifiers = tuple(sorted(id_a_signals & id_b_signals))
        a_only = sorted(id_a_signals - id_b_signals)
        b_only = sorted(id_b_signals - id_a_signals)
        disjoint_conflict = bool(a_only and b_only and not shared_identifiers)

        # Decision (documented): propose only with exact alias evidence, or
        # name similarity at/above the review threshold without disjoint
        # identifier conflicts. Shared identifier co-mentions upgrade the
        # method but never carry a pair on their own (co-mention is
        # association, not identity).
        if from_exact:
            method = "exact_alias"
        elif shared_identifiers and name_similarity >= review_threshold:
            method = "exact_identifier"
        elif name_similarity >= review_threshold and not disjoint_conflict:
            method = "name_similarity"
        else:
            if disjoint_conflict:
                counts["pairs_rejected_conflicting_identifiers"] += 1
            else:
                counts["pairs_rejected_weak_similarity"] += 1
            continue

        score = 100.0 if from_exact else name_similarity
        score_band = "strong" if score >= auto_threshold else "ambiguous"

        matching: list[dict[str, object]] = []
        if from_exact and matched_value is not None:
            matching.append(
                {
                    "field": "alias",
                    "detail": (
                        f"normalized value {matched_value!r} of one entity is a "
                        "registered alias of the other"
                    ),
                }
            )
        if shared_identifiers:
            matching.append(
                {"field": "shared_identifier", "detail": list(shared_identifiers)}
            )
        if name_similarity >= review_threshold:
            matching.append(
                {"field": "name_variant", "detail": {"similarity": name_similarity}}
            )
        shared_records = sorted(
            set(entity_a.source_record_ids) & set(entity_b.source_record_ids)
        )
        if shared_records:
            matching.append({"field": "shared_source_record", "detail": len(shared_records)})

        conflicting: list[dict[str, object]] = []
        if a_only and b_only:
            conflicting.append(
                {
                    "field": "identifier_signals",
                    "detail": {"a_only": a_only, "b_only": b_only},
                }
            )

        codes: list[str] = []
        if not from_exact and not shared_identifiers:
            codes.append("no_identifier_evidence")
        if conflicting and from_exact:
            codes.append("conflicting_identifiers")

        union = sorted(
            set(entity_a.source_record_ids) | set(entity_b.source_record_ids)
        )[:MAX_PAYLOAD_SOURCE_RECORDS]
        proposed.append(
            CandidatePair(
                entity_a=entity_a,
                entity_b=entity_b,
                method=method,
                score=score,
                score_band=score_band,
                name_similarity=name_similarity,
                alias_exact=from_exact,
                matching_fields=tuple(matching),
                conflicting_fields=tuple(conflicting),
                shared_identifiers=shared_identifiers,
                shared_source_record_ids=tuple(shared_records),
                union_source_record_ids=tuple(union),
                validation_codes=tuple(codes),
                llm_eligible=(
                    not from_exact
                    and not shared_identifiers
                    and score_band == "ambiguous"
                ),
            )
        )
    counts["pairs_proposed"] = len(proposed)
    counts["pairs_capped"] = max(0, len(raw_pairs) - evaluated)
    return proposed, counts


def pair_payload(pair: CandidatePair, llm: dict[str, str] | None) -> dict[str, Any]:
    """Artifact payload for one pair: deterministic facts, optional LLM verdict."""
    payload: dict[str, Any] = {
        "type": "entity_candidate",
        "entity_a": {
            "id": pair.entity_a.id,
            "entity_type": pair.entity_a.entity_type,
            "canonical_value": pair.entity_a.canonical_value,
            "display_value": pair.entity_a.display_value,
        },
        "entity_b": {
            "id": pair.entity_b.id,
            "entity_type": pair.entity_b.entity_type,
            "canonical_value": pair.entity_b.canonical_value,
            "display_value": pair.entity_b.display_value,
        },
        "method": pair.method,
        "score": pair.score,
        "score_band": pair.score_band,
        "score_semantics": "0-100 similarity band (not a probability)",
        "name_similarity": pair.name_similarity,
        "matching_fields": [dict(field) for field in pair.matching_fields],
        "conflicting_fields": [dict(field) for field in pair.conflicting_fields],
        "shared_identifiers": list(pair.shared_identifiers),
        "shared_source_record_ids": list(pair.shared_source_record_ids),
        "source_record_ids": list(pair.union_source_record_ids),
    }
    if llm is not None:
        payload["llm"] = dict(llm)
    return payload


class _PairVerdictSchema(BaseModel):
    """Strict reply schema: extra keys (e.g. echoed ids) reject the reply."""

    verdict: str = Field(pattern="^(same|different|unclear)$")
    reason: str = Field(min_length=1, max_length=600)


def parse_pair_verdict(text: str) -> dict[str, str] | None:
    """Validate one model reply; None means the reply is unusable."""
    result = parse_structured(text, _PairVerdictSchema)
    if result.data is None:
        return None
    return {
        "verdict": str(result.data["verdict"]),
        "reason": str(result.data["reason"]).strip()[:300],
    }


# -- approval (reviewed relationship, never a merge) ----------------------------


async def _scoped_entity(
    session: AsyncSession, case_id: uuid.UUID, entity_id: uuid.UUID
) -> Entity | None:
    result = await session.execute(
        select(Entity).where(Entity.id == str(entity_id), Entity.case_id == str(case_id))
    )
    return result.scalar_one_or_none()


async def apply_approved_match(
    session: AsyncSession, *, case_id: uuid.UUID, artifact: DerivedArtifact
) -> dict[str, object]:
    """Reviewer-approved candidate: additive aliases only, never a merge.

    Validates both entities still exist in this case and are unmerged, then
    cross-registers each entity's canonical value as an alias of the other
    (append-only, idempotent). Entity rows, statuses and ``merged_into_id``
    are untouched, so the measured false-merge rate is zero by construction
    and the reviewer's decision remains reversible through the audit trail.
    """
    payload = artifact.payload or {}
    if payload.get("type") != "entity_candidate":
        raise ResolutionRejected(
            CODE_ARTIFACT_KIND_UNSUPPORTED, "artifact is not an entity candidate"
        )
    try:
        block_a = payload["entity_a"]
        block_b = payload["entity_b"]
        if not isinstance(block_a, dict) or not isinstance(block_b, dict):
            raise TypeError("candidate blocks are not objects")
        entity_a_id = uuid.UUID(str(block_a["id"]))
        entity_b_id = uuid.UUID(str(block_b["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResolutionRejected(
            CODE_INVALID_PAYLOAD, "candidate payload lacks valid entity ids"
        ) from exc
    if entity_a_id == entity_b_id:
        raise ResolutionRejected(CODE_INVALID_PAYLOAD, "candidate references one entity twice")

    entity_a = await _scoped_entity(session, case_id, entity_a_id)
    entity_b = await _scoped_entity(session, case_id, entity_b_id)
    for entity in (entity_a, entity_b):
        if entity is None:
            raise ResolutionRejected(
                CODE_CANDIDATE_ENTITY_UNAVAILABLE,
                "one of the candidate entities no longer exists in this case; "
                "the proposal cannot be applied",
            )
        if entity.status == "merged":
            raise ResolutionRejected(
                CODE_CANDIDATE_ENTITY_UNAVAILABLE,
                "one of the candidate entities was already merged; the proposal is stale",
            )
    assert entity_a is not None and entity_b is not None
    if entity_a.entity_type != entity_b.entity_type:
        raise ResolutionRejected(CODE_TYPE_MISMATCH, "candidate entities are of different types")

    aliases_added = 0
    for target, value in (
        (entity_a, entity_b.canonical_value),
        (entity_b, entity_a.canonical_value),
    ):
        if value == target.canonical_value:
            continue
        existing = await session.execute(
            select(func.count())
            .select_from(EntityAlias)
            .where(
                EntityAlias.entity_id == str(target.id),
                EntityAlias.alias_value == value,
            )
        )
        if int(existing.scalar_one()) > 0:
            continue
        session.add(
            EntityAlias(
                entity_id=str(target.id),
                alias_value=value,
                alias_type="resolution",
            )
        )
        aliases_added += 1
    await session.flush()
    return {
        "aliases_added": aliases_added,
        "entity_a_id": str(entity_a_id),
        "entity_b_id": str(entity_b_id),
    }


# -- execution (bounded job runner) ----------------------------------------------


async def _load_entity_facts(
    session: AsyncSession, case_id: uuid.UUID, cap: int
) -> tuple[list[EntityFacts], dict[str, tuple[str, ...]], bool]:
    """Active/review entities of the case (bounded, chronological), plus their
    alias values keyed by entity id."""
    rows = await session.execute(
        select(Entity)
        .where(
            Entity.case_id == str(case_id),
            Entity.status.in_(("active", "review")),
        )
        .order_by(Entity.created_at, Entity.id)
        .limit(cap + 1)
    )
    entities = list(rows.scalars())
    bounded = len(entities) > cap
    entities = entities[:cap]
    if not entities:
        return [], {}, bounded
    entity_ids = [str(e.id) for e in entities]

    alias_rows = await session.execute(
        select(EntityAlias.entity_id, EntityAlias.alias_value).where(
            EntityAlias.entity_id.in_(entity_ids)
        )
    )
    alias_map: dict[str, list[str]] = {}
    for entity_id, alias_value in alias_rows.all():
        alias_map.setdefault(str(entity_id), []).append(str(alias_value))

    link_rows = await session.execute(
        select(EntityCandidate.entity_id, EntityCandidate.source_record_id).where(
            EntityCandidate.entity_id.in_(entity_ids),
            EntityCandidate.source_record_id.is_not(None),
        )
    )
    link_map: dict[str, list[str]] = {}
    for entity_id, record_id in link_rows.all():
        link_map.setdefault(str(entity_id), []).append(str(record_id))

    facts = [
        build_entity_facts(entity, link_map.get(str(entity.id), ())) for entity in entities
    ]
    aliases = {entity_id: tuple(sorted(set(values))) for entity_id, values in alias_map.items()}
    return facts, aliases, bounded


async def execute_entity_resolution(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    resolver: PairResolver | None = None,
) -> None:
    """Run one pending entity-resolution job to a terminal state.

    Proposals are never a job failure: ``succeeded`` reports how many pairs
    were proposed. Only authorization loss or unexpected crashes fail the
    job - always with a typed code. Cancellation and timeout are cooperative
    between pair evaluations and a canceled job can never succeed.
    """
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    if actor_id is None:
        await _fail_job(
            session, job, code="RESOLUTION_FAILED", error="job has no actor reference"
        )
        return
    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CASE_ACCESS_DENIED,
            error="access to this case was revoked before entity resolution ran",
            denial=True,
        )
        return
    if job.cancel_requested:
        await _stop_job(
            session, job, stop="cancel", summary={}, case_id=case_id, actor_id=actor_id
        )
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "entities_scanned": 0,
        "entities_bounded": False,
        "pairs_generated": 0,
        "pairs_proposed": 0,
        "pairs_llm": 0,
        "pairs_llm_invalid": 0,
        "pairs_llm_failed": 0,
        "pairs_llm_skipped": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
    }
    stage = "load"
    try:
        stage = "load-entities"
        entities, alias_values, bounded = await _load_entity_facts(
            session, case_id, settings.RESOLUTION_MAX_ENTITIES
        )
        summary["entities_scanned"] = len(entities)
        summary["entities_bounded"] = bounded

        stage = "match"
        pairs: list[CandidatePair] = []
        if entities:
            pairs, counts = build_candidate_pairs(
                entities,
                alias_values,
                auto_threshold=settings.RESOLUTION_AUTO_THRESHOLD,
                review_threshold=settings.RESOLUTION_REVIEW_THRESHOLD,
                max_per_bucket=settings.RESOLUTION_MAX_PER_BUCKET,
                max_pairs=settings.RESOLUTION_MAX_PAIRS,
            )
            summary.update(counts)
        jobs_svc.advance(job, processed=0, total=len(pairs))
        await session.commit()

        stage = "record"
        llm_budget = settings.RESOLUTION_MAX_LLM_PAIRS
        for index, pair in enumerate(pairs, start=1):
            await session.refresh(job)
            stop = jobs_svc.should_stop(job)
            if stop is not None:
                await _stop_job(
                    session, job, stop=stop, summary=summary,
                    case_id=case_id, actor_id=actor_id,
                )
                return
            if not await still_authorized_for_case(
                session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_READ
            ):
                await _fail_job(
                    session,
                    job,
                    code=CODE_CASE_ACCESS_DENIED,
                    error="access to this case was revoked mid-run; resolution stopped",
                    denial=True,
                    summary=summary,
                )
                return

            llm: dict[str, str] | None = None
            if pair.llm_eligible:
                if resolver is not None and settings.AI_FEATURE_RESOLUTION and llm_budget > 0:
                    llm_budget -= 1
                    llm = await _compare_with_model(resolver, pair, summary)
                else:
                    summary["pairs_llm_skipped"] += 1

            codes = list(pair.validation_codes)
            if llm is not None:
                codes.append("ai_unverified")
            validation_errors: list[dict[str, object]] = [
                {"field": "pair", "code": code, "message": VALIDATION_MESSAGES[code]}
                for code in codes
            ]
            _, created = await artifacts_svc.record_artifact(
                session,
                case_id=case_id,
                kind="entity_resolution",
                origin="llm" if llm is not None else "deterministic",
                payload=pair_payload(pair, llm),
                source_record_id=(
                    uuid.UUID(pair.shared_source_record_ids[0])
                    if pair.shared_source_record_ids
                    else None
                ),
                source_locator={"entity_a": pair.entity_a.id, "entity_b": pair.entity_b.id},
                validation_status="flagged" if codes else "valid",
                validation_errors=validation_errors or None,
                parser_version=ENTITY_MATCHER_VERSION,
                prompt_version=RESOLUTION_PROMPT_VERSION if llm is not None else None,
                model_profile=MODEL_PROFILE if llm is not None else None,
                analysis_job_id=job.id,
                created_by=actor_id,
                status="pending_review",
            )
            summary["artifacts_created" if created else "artifacts_reused"] += 1
            jobs_svc.advance(job, processed=index, total=len(pairs))
            await session.commit()

        job.result_summary = summary
        jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="resolution.analysis_completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata={
                "entities_scanned": summary["entities_scanned"],
                "pairs_proposed": summary["pairs_proposed"],
                "pairs_llm": summary["pairs_llm"],
            },
        )
        await session.commit()
    except Exception:
        logger.exception("entity resolution job crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code="RESOLUTION_FAILED",
            error=f"unexpected error during stage {stage}",
            summary=summary,
        )


async def _compare_with_model(
    resolver: PairResolver, pair: CandidatePair, summary: dict[str, Any]
) -> dict[str, str] | None:
    """One bounded, advisory comparison; failures degrade to deterministic."""
    entity_a, entity_b, features = pair.as_llm_facts()
    try:
        completion = await resolver.compare_entity_pair(
            entity_a=entity_a, entity_b=entity_b, features=features
        )
    except Exception:
        logger.warning("entity-pair comparison failed; keeping deterministic proposal")
        summary["pairs_llm_failed"] += 1
        return None
    verdict = parse_pair_verdict(getattr(completion, "text", "") or "")
    if verdict is None:
        summary["pairs_llm_invalid"] += 1
        return None
    summary["pairs_llm"] += 1
    return verdict


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """Cooperative stop: cancel wins over timeout; never reports success."""
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "resolution.canceled"
    else:
        job.error = f"entity resolution timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "resolution.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"pairs_proposed": summary.get("pairs_proposed", 0)} if summary else {},
    )
    await session.commit()


async def _fail_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    code: str,
    error: str,
    summary: dict[str, Any] | None = None,
    denial: bool = False,
    stage: str = "authorize",
) -> None:
    """Terminal failure with typed code + audit; safe from pending or running."""
    if jobs_svc.is_terminal(job.status):
        return
    payload: dict[str, Any] = dict(summary) if summary else {}
    payload["error_code"] = code
    job.result_summary = payload
    job.error = error[:500]
    jobs_svc.transition(job, "failed")
    await session.flush()
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action="resolution.denied" if denial else "resolution.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


# -- background entry ------------------------------------------------------------


async def run_entity_resolution_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    resolver: PairResolver | None = getattr(app.state, "ai_service", None)
    try:
        async with factory() as session:
            await execute_entity_resolution(
                session, job_id=job_id, settings=settings, resolver=resolver
            )
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background entity resolution failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code="RESOLUTION_FAILED",
                    error="background entity resolution task crashed",
                )

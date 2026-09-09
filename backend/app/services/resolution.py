"""Entity resolution: decide whether a candidate mention is a known entity.

Strategy (deterministic, per-case isolation):

1. **Blocking** - only entities sharing the mention's blocking key are compared;
2. **Signals** - exact canonical match, RapidFuzz similarity, and shared-context
   overlap (co-mentioned values from the same source records);
3. **Decision** - ``AUTO_MATCH`` at/above the auto threshold (link + alias),
   ``REVIEW`` between review and auto thresholds (recorded for later review),
   ``NO_MATCH`` below the review threshold (new entity created).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.core.config import Settings
from app.models import Entity
from app.repositories.entity_repository import EntityRepository

# Weight profile for the combined score (0-100).
FUZZY_WEIGHT = 0.85
CONTEXT_WEIGHT = 0.15


@dataclass(frozen=True)
class ResolutionOutcome:
    decision: str
    score: float
    signals: dict[str, object]
    entity: Entity | None
    created_new: bool
    target_signals: list[dict[str, object]] | None = None


def build_record_context(mention_signals: list[str]) -> dict[str, object]:
    return {"signals": sorted(set(signal for signal in mention_signals if signal))}


def merge_signals(existing: list[str], incoming: list[str]) -> list[str]:
    return sorted(set(existing) | set(incoming))


def _context_signals(context: dict[str, object] | None) -> list[str]:
    raw = context.get("signals") if context else None
    signals = raw if isinstance(raw, list) else []
    return [s for s in signals if isinstance(s, str)]


def _context_overlap(candidate_signals: list[str], entity_signals: list[str]) -> float:
    if not candidate_signals or not entity_signals:
        return 0.0
    cs, es = set(candidate_signals), set(entity_signals)
    if not es:
        return 0.0
    return round(len(cs & es) / len(cs | es) * 100, 2)


async def resolve_candidate(
    *,
    candidate_id: uuid.UUID,
    case_id: uuid.UUID,
    entity_type: str,
    canonical: str,
    blocking_key: str,
    display: str,
    candidate_signals: list[str],
    confidence: float | None,
    settings: Settings,
    repository: EntityRepository,
) -> ResolutionOutcome:
    targets = await repository.find_by_blocking_key(
        case_id=case_id,
        entity_type=entity_type,
        blocking_key=blocking_key,
        limit=settings.MAX_CANDIDATE_TARGETS_PER_KEY,
    )

    if not targets:
        entity = await repository.create_entity(
            case_id=case_id,
            entity_type=entity_type,
            canonical_value=canonical,
            blocking_key=blocking_key,
            display_value=display,
            confidence=confidence,
            status="active",
        )
        await repository.add_alias(
            entity_id=entity.id,
            alias_value=canonical,
            alias_type="value",
        )
        await repository.update_entity_context(entity.id, build_record_context(candidate_signals))
        await repository.link_candidate(
            candidate_id,
            entity_id=entity.id,
            resolution_status="no_match",
            confidence=confidence,
        )
        return ResolutionOutcome(
            decision="no_match",
            score=0.0,
            signals={"reason": "no candidate targets in blocking bucket"},
            entity=entity,
            created_new=True,
        )

    evaluations: list[dict[str, object]] = []
    best_target: Entity | None = None
    best_score = -1.0
    best_signals: dict[str, object] = {}

    for target in targets:
        entity_signals = _context_signals(target.context)
        fuzzy_score = float(fuzz.ratio(canonical, target.canonical_value))
        context_score = _context_overlap(candidate_signals, entity_signals)
        exact = canonical == target.canonical_value
        score = (
            100.0
            if exact
            else round(FUZZY_WEIGHT * fuzzy_score + CONTEXT_WEIGHT * context_score, 2)
        )
        signals = {
            "exact": exact,
            "fuzzy_ratio": fuzzy_score,
            "context_overlap": context_score,
            "target_entity_id": str(target.id),
            "target_value": target.display_value,
        }
        evaluations.append(signals)
        if score > best_score:
            best_score = score
            best_target = target
            best_signals = signals

    assert best_target is not None, "blocking bucket was non-empty"

    auto = settings.RESOLUTION_AUTO_THRESHOLD
    review = settings.RESOLUTION_REVIEW_THRESHOLD

    if best_score >= auto:
        await repository.link_candidate(
            candidate_id,
            entity_id=best_target.id,
            resolution_status="auto_match",
            confidence=round(best_score / 100, 3),
        )
        if canonical != best_target.canonical_value:
            await repository.add_alias(
                entity_id=best_target.id,
                alias_value=canonical,
                alias_type="value",
            )
        merged = merge_signals(_context_signals(best_target.context), candidate_signals)
        await repository.update_entity_context(best_target.id, build_record_context(merged))
        await repository.create_match(
            case_id=case_id,
            source_candidate_id=candidate_id,
            target_entity_id=best_target.id,
            decision="auto_match",
            score=best_score,
            signals={**best_signals, "evaluated": len(evaluations)},
            status="active",
        )
        return ResolutionOutcome(
            "auto_match", best_score, best_signals, best_target, False, evaluations
        )

    if best_score >= review:
        await repository.link_candidate(
            candidate_id,
            entity_id=None,
            resolution_status="review",
            confidence=round(best_score / 100, 3),
        )
        await repository.create_match(
            case_id=case_id,
            source_candidate_id=candidate_id,
            target_entity_id=best_target.id,
            decision="review",
            score=best_score,
            signals={**best_signals, "evaluated": len(evaluations)},
            status="review",
        )
        return ResolutionOutcome("review", best_score, best_signals, None, False, evaluations)

    return await _create_new_entity(
        repository=repository,
        case_id=case_id,
        entity_type=entity_type,
        canonical=canonical,
        blocking_key=blocking_key,
        display=display,
        confidence=confidence,
        candidate_id=candidate_id,
        candidate_signals=candidate_signals,
        score=best_score,
        signals=best_signals,
        evaluations=evaluations,
    )


async def _create_new_entity(
    *,
    repository: EntityRepository,
    case_id: uuid.UUID,
    entity_type: str,
    canonical: str,
    blocking_key: str,
    display: str,
    confidence: float | None,
    candidate_id: uuid.UUID,
    candidate_signals: list[str],
    score: float,
    signals: dict[str, object],
    evaluations: list[dict[str, object]],
) -> ResolutionOutcome:
    entity = await repository.create_entity(
        case_id=case_id,
        entity_type=entity_type,
        canonical_value=canonical,
        blocking_key=blocking_key,
        display_value=display,
        confidence=confidence,
        status="active",
    )
    await repository.add_alias(entity_id=entity.id, alias_value=canonical, alias_type="value")
    await repository.update_entity_context(entity.id, build_record_context(candidate_signals))
    await repository.link_candidate(
        candidate_id,
        entity_id=entity.id,
        resolution_status="no_match",
        confidence=confidence,
    )
    return ResolutionOutcome("no_match", score, signals, entity, True, evaluations)

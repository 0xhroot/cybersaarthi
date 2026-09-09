"""Unit tests for entity resolution decisions (blocking + fuzzy + context)."""

from __future__ import annotations

import uuid

from app.core.config import Settings
from app.models import Entity, EntityMatch
from app.services.resolution import resolve_candidate


class FakeEntityRepository:
    """In-memory stand-in implementing only what ``resolve_candidate`` touches."""

    def __init__(self) -> None:
        self.bucket: dict[tuple[str, str], list[Entity]] = {}
        self.entities: list[Entity] = []
        self.aliases: list[tuple[object, str, str]] = []
        self.contexts: list[tuple[object, str]] = []
        self.links: list[tuple[uuid.UUID, object, str, float | None]] = []
        self.matches: list[dict[str, object]] = []

    def _seed(self, *, canonical: str, signals: list[str] | None = None) -> Entity:
        entity = Entity(
            id=uuid.uuid4(),
            case_id="00000000-0000-0000-0000-000000000000",
            entity_type="person",
            canonical_value=canonical,
            blocking_key=canonical[:4],
            display_value=canonical.title(),
            confidence=1.0,
            status="active",
            context={"signals": signals or []},
        )
        self.bucket.setdefault(("person", canonical[:4]), []).append(entity)
        return entity

    async def find_by_blocking_key(
        self, *, case_id: uuid.UUID, entity_type: str, blocking_key: str, limit: int
    ) -> list[Entity]:
        return self.bucket.get((entity_type, blocking_key), [])[:limit]

    async def create_entity(
        self,
        *,
        case_id: uuid.UUID,
        entity_type: str,
        canonical_value: str,
        blocking_key: str,
        display_value: str,
        confidence: float | None,
        status: str = "active",
    ) -> Entity:
        entity = Entity(
            id=uuid.uuid4(),
            case_id=str(case_id),
            entity_type=entity_type,
            canonical_value=canonical_value,
            blocking_key=blocking_key,
            display_value=display_value,
            confidence=confidence,
            status=status,
        )
        self.entities.append(entity)
        self.bucket.setdefault((entity_type, blocking_key), []).append(entity)
        return entity

    async def add_alias(
        self,
        *,
        entity_id: uuid.UUID,
        alias_value: str,
        alias_type: str = "value",
        source_record_id: uuid.UUID | None = None,
    ) -> None:
        self.aliases.append((entity_id, alias_value, alias_type))

    async def update_entity_context(self, entity_id: uuid.UUID, context: dict[str, object]) -> None:
        self.contexts.append((entity_id, " ".join(context.get("signals", []))))

    async def link_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        entity_id: uuid.UUID | None,
        resolution_status: str,
        confidence: float | None,
    ) -> None:
        self.links.append((candidate_id, entity_id, resolution_status, confidence))

    async def create_match(
        self,
        *,
        case_id: uuid.UUID,
        source_candidate_id: uuid.UUID,
        target_entity_id: uuid.UUID | None,
        decision: str,
        score: float,
        signals: dict[str, object] | None,
        status: str = "review",
    ) -> EntityMatch:
        self.matches.append(
            {
                "case_id": case_id,
                "source_candidate_id": source_candidate_id,
                "target_entity_id": target_entity_id,
                "decision": decision,
                "score": score,
                "signals": signals,
                "status": status,
            }
        )
        return EntityMatch(
            case_id=str(case_id),
            source_candidate_id=str(source_candidate_id),
            target_entity_id=str(target_entity_id) if target_entity_id else None,
            decision=decision,
            score=score,
            signals=signals,
            status=status,
        )

    async def get_candidate(self, candidate_id: uuid.UUID) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        RESOLUTION_AUTO_THRESHOLD=92.0,
        RESOLUTION_REVIEW_THRESHOLD=78.0,
        MAX_CANDIDATE_TARGETS_PER_KEY=25,
    )


def _kwargs(canonical: str, signals: list[str]) -> dict[str, object]:
    return {
        "candidate_id": uuid.uuid4(),
        "case_id": uuid.uuid4(),
        "entity_type": "person",
        "canonical": canonical,
        "blocking_key": canonical[:4],
        "display": canonical.title(),
        "candidate_signals": signals,
        "confidence": None,
    }


async def test_empty_bucket_creates_new_entity() -> None:
    repo = FakeEntityRepository()
    outcome = await resolve_candidate(
        repository=repo, settings=_settings(), **_kwargs("rajesh kumar", ["9876543210"])
    )
    assert outcome.decision == "no_match"
    assert outcome.created_new
    assert outcome.entity is not None
    assert outcome.entity.canonical_value == "rajesh kumar"
    assert repo.links[-1][2] == "no_match"


async def test_exact_match_auto_links_without_new_alias() -> None:
    repo = FakeEntityRepository()
    target = repo._seed(canonical="rajesh kumar", signals=["9876543210"])
    outcome = await resolve_candidate(
        repository=repo, settings=_settings(), **_kwargs("rajesh kumar", ["9876543210"])
    )
    assert outcome.decision == "auto_match"
    assert outcome.score == 100.0
    assert not outcome.created_new
    assert outcome.entity is not None and outcome.entity.id == target.id
    assert repo.links[-1][2] == "auto_match"
    assert repo.matches[0]["decision"] == "auto_match"
    assert repo.matches[0]["status"] == "active"
    assert repo.aliases == []


async def test_close_fuzzy_with_shared_context_auto_matches() -> None:
    repo = FakeEntityRepository()
    target = repo._seed(canonical="arjun mehra", signals=["9876543210", "9876500001"])
    outcome = await resolve_candidate(
        repository=repo,
        settings=_settings(),
        **_kwargs("arjun mehta", ["9876543210", "9876500001"]),
    )
    assert outcome.decision == "auto_match"
    assert outcome.score >= 92.0
    assert outcome.entity is not None and outcome.entity.id == target.id
    # The variant spelling is recorded as an alias for future lookups.
    assert repo.aliases == [(target.id, "arjun mehta", "value")]


async def test_fuzzy_with_partial_context_lands_in_review() -> None:
    repo = FakeEntityRepository()
    repo._seed(canonical="arjun mehra", signals=["9876543210", "9876500001", "abc1234"])
    outcome = await resolve_candidate(
        repository=repo,
        settings=_settings(),
        **_kwargs("arjun mehta", ["9876543210", "9876500001"]),
    )
    assert outcome.decision == "review"
    assert 78.0 <= outcome.score < 92.0
    assert outcome.entity is None
    assert repo.links[-1][2] == "review"
    assert repo.matches[-1]["decision"] == "review"
    assert repo.matches[-1]["status"] == "review"


async def test_fuzzy_without_context_creates_new_entity() -> None:
    repo = FakeEntityRepository()
    repo._seed(canonical="arjun mehra", signals=["0000000000"])
    outcome = await resolve_candidate(
        repository=repo, settings=_settings(), **_kwargs("arjun mehta", [])
    )
    assert outcome.decision == "no_match"
    assert outcome.created_new
    assert outcome.entity is not None
    assert outcome.entity.canonical_value == "arjun mehta"


async def test_signals_report_target_and_ratio() -> None:
    repo = FakeEntityRepository()
    repo._seed(canonical="arjun mehra", signals=["9876543210"])
    outcome = await resolve_candidate(
        repository=repo, settings=_settings(), **_kwargs("arjun mehta", ["9876543210"])
    )
    fuzzy = float(outcome.signals["fuzzy_ratio"])
    assert abs(fuzzy - 90.909) < 0.01
    assert outcome.signals["exact"] is False
    assert "target_entity_id" in outcome.signals

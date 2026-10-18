"""Phase 3 feature A: entity-pair matcher - pure rules, anti-vacuous fixtures.

Pins the deterministic candidate generation (indexed probes only, never an
all-pairs scan), the transparent feature/band semantics (score is a 0-100 band
label, never a probability), and the safety properties: name-only pairs with
disjoint identifier signals are rejected, the LLM is consulted only for
ambiguous name-only pairs, and model replies with any extra key (e.g. echoed
ids) are discarded. The golden fixture runner asserts exact decisions for
positive, ambiguous and negative pairs; the guard asserts the set actually
exercises every decision class.

An approved match never merges entities (that is the API/route contract, see
tests/api/test_phase3_intelligence_api.py): the pure matcher here must simply
never *propose* a pair without evidence strong enough for human review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.entity_matching import (
    CandidatePair,
    EntityFacts,
    build_candidate_pairs,
    pair_payload,
    parse_pair_verdict,
)
from app.services.normalization import blocking_key

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "entity_resolution_checks.json"
)

AUTO, REVIEW = 92.0, 78.0


def _facts(entity: dict[str, Any]) -> EntityFacts:
    canonical = entity["canonical_value"]
    entity_type = entity["entity_type"]
    return EntityFacts(
        id=entity["id"],
        entity_type=entity_type,
        canonical_value=canonical,
        display_value=entity.get("display_value", canonical),
        blocking_key=blocking_key(entity_type, canonical),
        status="active",
        signals=tuple(entity.get("signals", ())),
        source_record_ids=tuple(entity.get("source_record_ids", ())),
    )


def _run(
    entities: list[EntityFacts],
    aliases: dict[str, tuple[str, ...]],
    **overrides: float,
) -> tuple[list[CandidatePair], dict[str, int]]:
    return build_candidate_pairs(
        entities,
        aliases,
        auto_threshold=overrides.get("auto_threshold", AUTO),
        review_threshold=overrides.get("review_threshold", REVIEW),
        max_per_bucket=overrides.get("max_per_bucket", 25),
        max_pairs=overrides.get("max_pairs", 150),
    )


def _load() -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["cases"], "fixture file must not be empty"
    return data


# -- golden fixture runner ------------------------------------------------------


def test_fixture_set_exercises_every_decision_class() -> None:
    """Anti-vacuous guard: proposals, every reject reason and LLM eligibility."""
    cases = _load()["cases"]
    assert {case["category"] for case in cases} == {"positive", "ambiguous", "negative"}
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"

    proposed = [c for c in cases if c["expect"]["proposed"]]
    rejected = [c for c in cases if not c["expect"]["proposed"]]
    assert proposed and rejected, "set must contain both proposals and rejections"
    assert {c["expect"].get("reject_reason") for c in rejected} == {
        "conflicting_identifiers",
        "weak_similarity",
        "not_generated",
    }
    assert {c["expect"].get("method") for c in proposed} == {
        "exact_alias",
        "exact_identifier",
        "name_similarity",
    }
    assert any(c["expect"].get("llm_eligible") for c in proposed)
    assert any(not c["expect"].get("llm_eligible") for c in proposed)
    assert any(
        "no_identifier_evidence" in c["expect"].get("validation_codes", []) for c in proposed
    )
    assert any(c["expect"].get("validation_codes") == [] for c in proposed)


def test_every_fixture_case_produces_expected_decision() -> None:
    for case in _load()["cases"]:
        entities = [_facts(entity) for entity in case["entities"]]
        aliases = {key: tuple(values) for key, values in case.get("aliases", {}).items()}
        pairs, _counts = _run(entities, aliases)
        pair_key = frozenset(case["pair"])
        match = next(
            (pair for pair in pairs if frozenset((pair.entity_a.id, pair.entity_b.id)) == pair_key),
            None,
        )
        expect = case["expect"]
        if not expect["proposed"]:
            assert match is None, case["id"]
            if expect.get("reject_reason") == "not_generated":
                _, counts = _run(entities, aliases)
                assert counts["pairs_generated"] == 0, case["id"]
            continue
        assert match is not None, case["id"]
        if "method" in expect:
            assert match.method == expect["method"], case["id"]
        if "score" in expect:
            assert match.score == expect["score"], case["id"]
        if "score_band" in expect:
            assert match.score_band == expect["score_band"], case["id"]
        assert sorted(match.validation_codes) == sorted(expect.get("validation_codes", [])), case[
            "id"
        ]
        assert match.llm_eligible == expect.get("llm_eligible", False), case["id"]


# -- direct rule tests ----------------------------------------------------------


def test_exact_alias_with_disjoint_identifier_signals_is_flagged() -> None:
    """Strong positive evidence wins over co-mention conflicts, but is flagged."""
    entities = [
        _facts(
            {
                "id": "e1",
                "entity_type": "person",
                "canonical_value": "arjun mehta",
                "signals": ["9876543210"],
            }
        ),
        _facts(
            {
                "id": "e2",
                "entity_type": "person",
                "canonical_value": "a. mehta",
                "signals": ["9988776655"],
            }
        ),
        _facts({"id": "p1", "entity_type": "phone", "canonical_value": "9876543210"}),
        _facts({"id": "p2", "entity_type": "phone", "canonical_value": "9988776655"}),
    ]
    pairs, _ = _run(entities, {"e2": ("Arjun Mehta",)})
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.method == "exact_alias"
    assert "conflicting_identifiers" in pair.validation_codes
    assert pair.conflicting_fields, "conflicts must be recorded next to matches"


def test_generation_is_indexed_not_all_pairs() -> None:
    """Different blocking keys without aliases generate no pairs at all."""
    entities = [
        _facts({"id": "a", "entity_type": "person", "canonical_value": "arjun mehta"}),
        _facts({"id": "b", "entity_type": "person", "canonical_value": "sunita iyer"}),
        _facts({"id": "c", "entity_type": "vehicle", "canonical_value": "mh12ab1234"}),
        _facts({"id": "d", "entity_type": "vehicle", "canonical_value": "dl09cq9999"}),
    ]
    pairs, counts = _run(entities, {})
    assert pairs == []
    assert counts["pairs_generated"] == 0


def test_blocking_bucket_cap_bounds_generation() -> None:
    entities = [
        _facts(
            {
                "id": f"e{i:02d}",
                "entity_type": "person",
                "canonical_value": f"rajesh kumar{i}",
            }
        )
        for i in range(10)
    ]
    _pairs, counts = _run(entities, {}, max_per_bucket=3)
    assert counts["pairs_from_blocking"] <= 3


def test_max_pairs_cap_is_reported_honestly() -> None:
    entities = [
        _facts({"id": f"e{i:02d}", "entity_type": "person", "canonical_value": "rajesh kumar"})
        for i in range(5)
    ]
    pairs, counts = _run(entities, {}, max_pairs=1)
    assert len(pairs) == 1
    assert counts["pairs_generated"] > 1
    assert counts["pairs_capped"] == counts["pairs_generated"] - 1


def test_shared_identifier_requires_name_support_to_upgrade() -> None:
    """Co-mention of one phone with dissimilar names never carries a pair."""
    entities = [
        _facts(
            {
                "id": "e1",
                "entity_type": "person",
                "canonical_value": "arjun mehta",
                "signals": ["9876543210"],
            }
        ),
        _facts(
            {
                "id": "e2",
                "entity_type": "person",
                "canonical_value": "ajay mehta",
                "signals": ["9876543210"],
            }
        ),
        _facts({"id": "p1", "entity_type": "phone", "canonical_value": "9876543210"}),
    ]
    pairs, counts = _run(entities, {})
    assert pairs == []
    assert counts["pairs_rejected_weak_similarity"] == 1


def test_llm_eligibility_is_ambiguous_band_only() -> None:
    entities = [
        _facts({"id": "e1", "entity_type": "person", "canonical_value": "amit mehta"}),
        _facts({"id": "e2", "entity_type": "person", "canonical_value": "anil mehta"}),
    ]
    pairs, _ = _run(entities, {})
    assert len(pairs) == 1
    assert pairs[0].llm_eligible is True, "ambiguous name-only pairs are LLM-eligible"


def test_llm_facts_never_contain_ids() -> None:
    entities = [
        _facts({"id": "e1", "entity_type": "person", "canonical_value": "amit mehta"}),
        _facts({"id": "e2", "entity_type": "person", "canonical_value": "anil mehta"}),
    ]
    pairs, _ = _run(entities, {})
    entity_a, entity_b, features = pairs[0].as_llm_facts()
    for block in (entity_a, entity_b, features):
        assert "id" not in block and "entity_id" not in block
    assert "entity_a" not in features


# -- model reply validation -------------------------------------------------------


def test_parse_verdict_accepts_strict_reply() -> None:
    verdict = parse_pair_verdict('{"verdict": "unclear", "reason": "no shared identifier"}')
    assert verdict == {"verdict": "unclear", "reason": "no shared identifier"}


def test_parse_verdict_rejects_echoed_identifiers() -> None:
    """Model-returned ids are unknown fields; the reply is discarded entirely."""
    reply = '{"verdict": "same", "reason": "names match", "entity_id": "123e4567"}'
    assert parse_pair_verdict(reply) is None


def test_parse_verdict_rejects_missing_or_invalid_fields() -> None:
    assert parse_pair_verdict('{"verdict": "same"}') is None
    assert parse_pair_verdict('{"verdict": "maybe", "reason": "x"}') is None
    assert parse_pair_verdict("not json at all") is None
    assert parse_pair_verdict("") is None


def test_payload_declares_score_semantics_and_keeps_both_sides() -> None:
    entities = [
        _facts({"id": "e1", "entity_type": "person", "canonical_value": "amit mehta"}),
        _facts({"id": "e2", "entity_type": "person", "canonical_value": "anil mehta"}),
    ]
    pairs, _ = _run(entities, {})
    payload = pair_payload(pairs[0], None)
    assert payload["type"] == "entity_candidate"
    assert "probability" in payload["score_semantics"]
    assert payload["entity_a"]["id"] == "e1" and payload["entity_b"]["id"] == "e2"
    assert "llm" not in payload
    payload_llm = pair_payload(pairs[0], {"verdict": "unclear", "reason": "x"})
    assert payload_llm["llm"]["verdict"] == "unclear"

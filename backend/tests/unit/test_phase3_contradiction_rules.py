"""Phase 3 feature C: contradiction rules - anchored matrix, fixtures.

Pins the deterministic field classifier and the anchored comparison matrix,
including the anti-false-positive core: an entity anchor (shared account or
phone) never carries amount/date/transaction-status comparisons, so two
different transactions of one account never become a "contradiction". Model
replies with any extra key (e.g. echoed ids) are discarded, and only an
anchored pair of statements is ever eligible for the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.contradiction_detection import (
    CONTRADICTION_STATES,
    RecordFacts,
    anchor_scope,
    classify_field,
    collect_statements,
    generate_conflicts,
    identifier_index,
    parse_statement_verdict,
    record_claims,
    semantic_pairs,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "contradiction_checks.json"
)


def _record(record_id: str, raw_data: dict[str, Any], *, record_no: int = 1) -> RecordFacts:
    return RecordFacts(
        id=record_id,
        evidence_file_id="ev-1",
        record_no=record_no,
        raw_data=raw_data,
    )


def _load() -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["classify_cases"] and data["pair_cases"], "fixture file must not be empty"
    return data


# -- golden fixture runner ------------------------------------------------------


def test_fixture_set_exercises_every_outcome() -> None:
    """Anti-vacuous guard: each class and both pair outcomes are covered."""
    data = _load()
    classes = {case["expect"] for case in data["classify_cases"]}
    assert classes == {"amount", "currency", "date", "status", "identifier", None}
    categories = set()
    for case in data["pair_cases"]:
        categories.update(case["expect"]["categories"])
    assert categories == {"amount", "currency", "status", "identifier", "date"}
    assert any(case["expect"]["categories"] == [] for case in data["pair_cases"])
    assert any(case["expect"]["categories"] for case in data["pair_cases"])
    ids = [case["id"] for case in data["pair_cases"]]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"


def test_every_classify_case_produces_expected_class() -> None:
    for case in _load()["classify_cases"]:
        assert classify_field(case["field"], case["value"]) == case["expect"], (
            f"{case['field']}={case['value']!r}"
        )


def test_every_pair_case_produces_expected_conflicts() -> None:
    for case in _load()["pair_cases"]:
        records = [
            _record(r["id"], r["raw_data"], record_no=r["record_no"])
            for r in case["records"]
        ]
        conflicts, counts = generate_conflicts(
            records, max_records_per_anchor=8, max_pair_evals=2000
        )
        expect = case["expect"]
        categories = sorted(conflict.category for conflict, _, _ in conflicts)
        assert categories == sorted(expect["categories"]), case["id"]
        if "conflict_count" in expect:
            assert counts["conflicts"] == expect["conflict_count"], case["id"]
        for conflict, _, _ in conflicts:
            priority_of = expect.get("priority_of", {})
            if conflict.category in priority_of:
                assert conflict.priority == priority_of[conflict.category], case["id"]
            assert conflict.alternatives, f"{case['id']}: every candidate lists alternatives"
            assert conflict.rule.startswith("contradiction."), case["id"]
            assert conflict.as_payload()["rule_version"] == "1.0.0", case["id"]
            assert conflict.first["source_record_id"], case["id"]
            assert conflict.second["source_record_id"], case["id"]
            assert conflict.anchor["value"], case["id"]
        union_alternatives = " ".join(
            alt for conflict, _, _ in conflicts for alt in conflict.alternatives
        )
        if "alternative_any" in expect:
            assert expect["alternative_any"] in union_alternatives, case["id"]
        union_missing = " ".join(
            miss for conflict, _, _ in conflicts for miss in conflict.missing
        )
        if "missing_any" in expect:
            assert expect["missing_any"] in union_missing, case["id"]


# -- direct rule tests -----------------------------------------------------------


def test_amounts_compare_as_exact_decimals() -> None:
    records = [
        _record("r1", {"txn_id": "TXN-1", "txn_amount": "1500.50"}),
        _record("r2", {"txn_id": "TXN-1", "txn_amount": "1500.5"}),
    ]
    conflicts, _ = generate_conflicts(records, max_records_per_anchor=8, max_pair_evals=100)
    assert conflicts == [], "equal decimals in different notations are not a conflict"


def test_identifier_equality_ignores_punctuation_and_case() -> None:
    records = [
        _record("r1", {"txn_id": "UTR-98765", "txn_amount": "100"}),
        _record("r2", {"txn_id": "utr 98765", "txn_amount": "200"}),
    ]
    conflicts, _ = generate_conflicts(records, max_records_per_anchor=8, max_pair_evals=100)
    assert [c.category for c, _, _ in conflicts] == ["amount"]
    assert conflicts[0][0].anchor["value"] == "utr98765"


def test_amount_missing_currency_is_stated_explicitly() -> None:
    records = [
        _record("r1", {"txn_id": "TXN-7", "txn_amount": "100"}),
        _record("r2", {"txn_id": "TXN-7", "txn_amount": "200"}),
    ]
    conflicts, _ = generate_conflicts(records, max_records_per_anchor=8, max_pair_evals=100)
    assert len(conflicts) == 1
    assert "currency code" in conflicts[0][0].missing


def test_multiple_shared_anchors_yield_one_conflict() -> None:
    records = [
        _record("r1", {"txn_id": "TXN-8", "reference_no": "REF-8", "txn_amount": "100"}),
        _record("r2", {"txn_id": "TXN-8", "reference_no": "REF-8", "txn_amount": "200"}),
    ]
    conflicts, counts = generate_conflicts(records, max_records_per_anchor=8, max_pair_evals=100)
    assert counts["conflicts"] == 1
    assert counts["anchor_groups"] >= 2, "both identifiers are anchors"
    assert conflicts[0][0].anchor["scope"] == "transaction"


def test_anchor_scope_prefers_transaction() -> None:
    assert anchor_scope([("r1", "entity"), ("r2", "transaction")]) == "transaction"
    assert anchor_scope([("r1", "entity"), ("r2", "entity")]) == "entity"


def test_pair_evaluation_budget_is_enforced() -> None:
    records = [
        _record("r1", {"txn_id": "TXN-9", "txn_amount": "100"}),
        _record("r2", {"txn_id": "TXN-9", "txn_amount": "200"}),
        _record("r3", {"txn_id": "TXN-9", "txn_amount": "300"}),
    ]
    _conflicts, counts = generate_conflicts(
        records, max_records_per_anchor=8, max_pair_evals=1
    )
    assert counts["pair_evals"] == 1


def test_records_without_claims_never_anchor() -> None:
    records = [
        _record("r1", {"name": "Rajesh Kumar", "city": "Mumbai"}),
        _record("r2", {"name": "Rajesh Kumar", "city": "Pune"}),
    ]
    claims = {record.id: record_claims(record) for record in records}
    index = identifier_index(claims)
    assert index == {}
    conflicts, counts = generate_conflicts(records, max_records_per_anchor=8, max_pair_evals=10)
    assert conflicts == [] and counts["records_with_claims"] == 0


# -- semantic (LLM-eligible) pairs ------------------------------------------------


def test_semantic_pairs_require_anchor_same_field_and_different_text() -> None:
    records = [
        _record(
            "r1",
            {
                "txn_id": "TXN-S",
                "statement": (
                    "Vendor reported the goods were delivered to the wrong "
                    "warehouse on 2026-03-10."
                ),
            },
        ),
        _record(
            "r2",
            {
                "txn_id": "TXN-S",
                "statement": (
                    "Vendor reported the goods were never dispatched from "
                    "the origin warehouse."
                ),
            },
        ),
        _record(
            "r3",
            {
                "txn_id": "TXN-OTHER",
                "statement": (
                    "Unrelated statement about a completely different "
                    "transaction reference."
                ),
            },
        ),
    ]
    pairs = semantic_pairs(
        records, collect_statements(records, []), max_records_per_anchor=8, limit=10
    )
    assert len(pairs) == 1
    anchor, first, second = pairs[0]
    assert anchor == "txns"
    assert {first.record_id, second.record_id} == {"r1", "r2"}


def test_semantic_pairs_never_compare_different_fields_or_identical_text() -> None:
    records = [
        _record(
            "r1",
            {
                "txn_id": "TXN-S2",
                "statement": (
                    "The goods were delivered late due to a port strike "
                    "in March."
                ),
            },
        ),
        _record(
            "r2",
            {"txn_id": "TXN-S2", "notes": "Buyer insists the goods were never delivered at all."},
        ),
        _record(
            "r3",
            {
                "txn_id": "TXN-S2",
                "statement": (
                    "The goods were delivered late due to a port strike "
                    "in March."
                ),
            },
        ),
    ]
    pairs = semantic_pairs(
        records, collect_statements(records, []), max_records_per_anchor=8, limit=10
    )
    assert pairs == [], "different field names and identical text are not eligible"


def test_semantic_pair_limit_is_enforced() -> None:
    records = [
        _record(
            "r1",
            {
                "txn_id": "TXN-L1",
                "statement": (
                    "Statement number one claiming delivery happened on "
                    "the fifteenth of March."
                ),
            },
        ),
        _record(
            "r2",
            {
                "txn_id": "TXN-L1",
                "statement": (
                    "Statement number two claiming nothing was ever "
                    "delivered to anyone."
                ),
            },
        ),
        _record(
            "r3",
            {
                "txn_id": "TXN-L2",
                "statement": (
                    "Statement number three claiming a refund was issued "
                    "in cash."
                ),
            },
        ),
        _record(
            "r4",
            {
                "txn_id": "TXN-L2",
                "statement": (
                    "Statement number four claiming no refund was ever "
                    "issued."
                ),
            },
        ),
    ]
    pairs = semantic_pairs(
        records, collect_statements(records, []), max_records_per_anchor=8, limit=1
    )
    assert len(pairs) == 1


def test_parse_statement_verdict_accepts_and_rejects_appropriately() -> None:
    verdict = parse_statement_verdict(
        '{"contradicts": true, "explanation": "opposite delivery claims"}'
    )
    assert verdict == {"contradicts": True, "explanation": "opposite delivery claims"}
    # Extra keys (echoed ids) reject the whole reply.
    assert parse_statement_verdict(
        '{"contradicts": true, "explanation": "x", "record_id": "abc"}'
    ) is None
    assert parse_statement_verdict('{"contradicts": "definitely", "explanation": "x"}') is None
    assert parse_statement_verdict("not json") is None


def test_review_states_are_the_documented_three() -> None:
    assert set(CONTRADICTION_STATES) == {"explained", "requires_evidence", "deferred"}

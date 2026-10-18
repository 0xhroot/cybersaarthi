"""Deterministic evaluation of the custody fixture set (feature 9).

Every snapshot in ``custody_checks.json`` runs through the pure rule engine
exactly as the audit assembles it (recorded events, recorded hash, recomputed
object hash, audit-entry count). Assertions pin the §E metrics: hash
verification correctness (match/mismatch/missing each map to their rule or to
silence), custody false-positive rate (positive fixtures must yield ZERO
findings), per-defect detection with severity semantics and event scoping.
Anti-vacuous guards fix minimum rule/severity coverage.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.services.custody import (
    CUSTODY_POLICY_VERSION,
    CUSTODY_RULE_SET_VERSION,
    CustodyEventFacts,
    CustodySnapshot,
    evaluate_custody,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "custody_checks.json"
)


def _load() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["cases"], "fixture file must not be empty"
    return data


def _snapshot(case: dict) -> CustodySnapshot:
    values = dict(case["snapshot"])
    values["case_id"] = "eval-case"
    values["evidence_id"] = "ev1"
    values["checked_at"] = datetime.fromisoformat(values["checked_at"])
    values.setdefault(
        "evidence_created_at", datetime(2026, 1, 1, tzinfo=values["checked_at"].tzinfo)
    )
    values["events"] = tuple(
        CustodyEventFacts(
            id=event["id"],
            event_type=event["event_type"],
            occurred_at=datetime.fromisoformat(event["occurred_at"]),
            recorded_at=datetime.fromisoformat(event["recorded_at"]),
            collector=event["collector"],
            transferor=event["transferor"],
            recipient=event["recipient"],
            evidence_file_id=event["evidence_file_id"],
            recorded_sha256=event["recorded_sha256"],
        )
        for event in values["events"]
    )
    return CustodySnapshot(**values)


def test_fixture_set_covers_rules_and_severities() -> None:
    """Anti-vacuous guard: rule, severity and category coverage."""
    cases = _load()["cases"]
    rules = {rule for case in cases for rule in case["expect"]["rules"]}
    assert {
        "custody.hash_mismatch",
        "custody.hash_missing",
        "custody.source_missing",
        "custody.recorded_hash_mismatch",
        "custody.missing_required_field",
        "custody.unacknowledged_transfer",
        "custody.duplicate_event",
    } <= rules
    severities = {
        severity for case in cases for severity in case["expect"].get("severities", {}).values()
    }
    assert severities == {"critical", "warning", "info"}
    positives = [case for case in cases if case["category"] == "positive"]
    negatives = [case for case in cases if case["category"] == "negative"]
    assert len(positives) >= 3 and len(negatives) >= 8
    for case in positives:
        assert case["expect"]["rules"] == [], case["id"]
    for case in negatives:
        assert case["expect"]["rules"], case["id"]  # defects must expect findings
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"


def test_every_fixture_case_produces_expected_rules() -> None:
    for case in _load()["cases"]:
        issues = evaluate_custody(_snapshot(case))
        expect = case["expect"]
        assert sorted(i.rule for i in issues) == sorted(expect["rules"]), case["id"]
        by_rule = {i.rule: i for i in issues}
        for rule, severity in expect.get("severities", {}).items():
            assert by_rule[rule].severity == severity, f"{case['id']}:{rule}"
        for rule, ids in expect.get("event_ids_by_rule", {}).items():
            assert list(by_rule[rule].event_ids) == ids, f"{case['id']}:{rule}"
        # Payloads stay wall-clock-free: same facts must dedupe across runs.
        for issue in issues:
            payload = issue.as_payload()
            assert "checked_at" not in payload
            assert payload["rule_set_version"] == CUSTODY_RULE_SET_VERSION
            assert payload["policy_version"] == CUSTODY_POLICY_VERSION


def test_false_positive_rate_is_zero_on_positive_cases() -> None:
    positives = [case for case in _load()["cases"] if case["category"] == "positive"]
    assert len(positives) >= 3
    for case in positives:
        assert evaluate_custody(_snapshot(case)) == (), case["id"]


def test_hash_verification_correctness_is_exact() -> None:
    cases = {case["id"]: case for case in _load()["cases"]}
    mismatch = evaluate_custody(_snapshot(cases["recomputed-hash-mismatch-critical"]))
    assert len(mismatch) == 1
    observed = mismatch[0].observed
    snap = cases["recomputed-hash-mismatch-critical"]["snapshot"]
    assert observed["expected_sha256"] == snap["evidence_sha256"]
    assert observed["calculated_sha256"] == snap["object_hash"]

    for clean_id in ("clean-full-lifecycle", "documented-no-events-clean"):
        rules = [i.rule for i in evaluate_custody(_snapshot(cases[clean_id]))]
        assert not any("hash" in rule for rule in rules), clean_id

    # Missing info never masquerades as tampering.
    missing = evaluate_custody(_snapshot(cases["recorded-hash-missing-info-only"]))
    assert [i.severity for i in missing] == ["info"]
    no_source = evaluate_custody(_snapshot(cases["source-bytes-missing-warning-not-tampering"]))
    assert [i.severity for i in no_source] == ["warning"]
    assert "not proof of tampering" in no_source[0].message


def test_evaluation_is_deterministic_for_identical_snapshots() -> None:
    for case in _load()["cases"]:
        first = [i.as_payload() for i in evaluate_custody(_snapshot(case))]
        second = [i.as_payload() for i in evaluate_custody(_snapshot(case))]
        assert first == second, case["id"]

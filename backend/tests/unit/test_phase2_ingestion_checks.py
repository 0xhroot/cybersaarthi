"""Deterministic evaluation of the ingestion-copilot fixture set (feature 1).

Every case in ``ingestion_checks.json`` runs through the exact stages a model
reply passes: strict schema parse (real ``EvidenceExtractionSchema``) then
field-level validation against the authorized source record. The assertions
pin the §E metrics as exact per-case outcomes - schema acceptance,
field-level verification rate, unsupported-claim detection - so a regression
that silently accepts unsupported claims (or rejects valid ones) fails here.
Anti-vacuous guards fix the minimum fixture coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.evidence_extraction import EvidenceExtractionSchema
from app.services.structured_extraction import check_fields_against_source, parse_structured

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "ingestion_checks.json"
)


def _load() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["cases"], "fixture file must not be empty"
    return data


def _evaluate(case: dict) -> tuple[str, list[str], list[str]]:
    """(status, unverified fields, issue codes) for one fixture case."""
    result = parse_structured(case["raw"], EvidenceExtractionSchema)
    codes = [issue.code for issue in result.issues]
    unverified: list[str] = []
    if result.data is not None:
        issues = check_fields_against_source(result.data, case["source"])
        unverified = sorted({issue.field for issue in issues})
        codes.extend(issue.code for issue in issues)
        status = "flagged" if issues else "valid"
    else:
        status = "invalid"
    return status, unverified, sorted(set(codes))


def test_fixture_set_covers_every_outcome() -> None:
    """Anti-vacuous guard: statuses, categories, planted-defect codes."""
    cases = _load()["cases"]
    statuses = {case["expect"]["status"] for case in cases}
    assert statuses == {"valid", "flagged", "invalid"}
    categories = {case["category"] for case in cases}
    assert categories == {"positive", "negative"}
    codes = {code for case in cases for code in case["expect"]["issue_codes"]}
    assert {"schema_error", "unknown_field", "malformed_json", "value_not_in_source"} <= codes
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"
    assert len(cases) >= 10
    # Expectations themselves must not be vacuous.
    for case in cases:
        if case["expect"]["status"] == "flagged":
            assert case["expect"]["unverified_fields"], case["id"]
        if case["expect"]["status"] == "valid":
            assert case["expect"]["unverified_fields"] == [], case["id"]


def test_every_fixture_case_produces_expected_status_and_codes() -> None:
    for case in _load()["cases"]:
        status, unverified, codes = _evaluate(case)
        expect = case["expect"]
        assert status == expect["status"], case["id"]
        assert unverified == sorted(expect["unverified_fields"]), case["id"]
        assert codes == sorted(set(expect["issue_codes"])), case["id"]


def test_metrics_are_selective_not_blanket() -> None:
    """Aggregate §E metrics over the set: verification is high on clean cases
    and the flagged set is exactly the planted unsupported claims - neither
    blanket acceptance nor blanket rejection passes."""
    evaluated = [(case, *_evaluate(case)) for case in _load()["cases"]]
    schema_valid = [(c, s, u) for c, s, u, _ in evaluated if s != "invalid"]
    invalid = [c for c, s, _, _ in evaluated if s == "invalid"]
    assert len(schema_valid) >= 6
    assert len(invalid) >= 3

    field_total = 12 * len(schema_valid)  # every schema field is reported
    field_unverified = sum(len(u) for _, _, u in schema_valid)
    assert field_total > 0
    assert 0 < field_unverified < field_total  # selective detection

    # Positive cases verify 100% of fields; flagged cases name the exact defect.
    for case, _status, unverified in schema_valid:
        if case["category"] == "positive":
            assert unverified == [], case["id"]
        else:
            assert unverified, case["id"]

"""Runs the shared extraction-validation fixtures through the real validators.

This is the deterministic core of the feature-1 evaluation: every fixture row
asserts the *exact* status and issue codes the pipeline must produce, so a
regression that silently accepts model output (or flags everything) fails here.
Anti-vacuous guards assert the fixture set actually exercises each outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.structured_extraction import check_fields_against_source, parse_structured
from pydantic import BaseModel

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "extraction_checks.json"
)


class FixtureExtraction(BaseModel):
    """Schema described by the fixture's schema_fields (account optional)."""

    person_name: str
    amount: str
    txn_date: str
    account: str | None = None


def _load() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["cases"], "fixture file must not be empty"
    return data


def test_fixture_set_covers_every_outcome() -> None:
    """Anti-vacuous guard: the set must contain valid, flagged and invalid cases."""
    cases = _load()["cases"]
    statuses = {case["expect"]["status"] for case in cases}
    assert statuses == {"valid", "flagged", "invalid"}
    categories = {case["category"] for case in cases}
    assert categories == {"positive", "negative"}
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"


def test_every_fixture_case_produces_expected_status_and_codes() -> None:
    for case in _load()["cases"]:
        result = parse_structured(case["raw"], FixtureExtraction)
        if result.data is not None:
            locators = case.get("locators")
            source_issues = check_fields_against_source(
                result.data,
                case["source"],
                locators=locators,
            )
            result = type(result)(result.data, result.issues + source_issues)

        assert result.status == case["expect"]["status"], case["id"]
        assert sorted(issue.code for issue in result.issues) == sorted(
            case["expect"]["codes"]
        ), case["id"]
        # Every flagged/invalid case must carry at least one machine-readable code.
        if result.status != "valid":
            assert result.issues, case["id"]

"""Unit tests: citation validator shape checks and review-flag rendering.

The database-backed checks (existence, case scope, value equality against
stored rows) are exercised end-to-end in
``tests/integration/test_citations_db.py`` and through the API suite; this
file covers the pure parts that must hold without infrastructure.
"""

from __future__ import annotations

from app.services.citations import (
    CITATION_KINDS,
    CitationCheck,
    CitationRef,
    flags_from_checks,
    preflight,
)


def test_preflight_rejects_malformed_ids() -> None:
    codes = preflight(CitationRef(kind="source_record", id="not-a-uuid"))
    assert "citation_invalid_id" in codes


def test_preflight_rejects_malformed_ids_and_unknown_kinds_together() -> None:
    codes = preflight(CitationRef(kind="telepathy", id="??"))
    assert set(codes) == {"citation_invalid_id", "citation_unknown_kind"}


def test_preflight_accepts_well_formed_reference() -> None:
    good = "12345678-1234-5678-1234-567812345678"
    assert preflight(CitationRef(kind="source_record", id=good)) == ()
    assert preflight(CitationRef(kind="derived_artifact", id=good)) == ()
    assert set(CITATION_KINDS) >= {
        "source_record",
        "evidence_file",
        "entity",
        "relationship",
        "finding",
        "timeline_event",
        "hypothesis",
        "derived_artifact",
    }


def test_check_defaults_to_failure_codes() -> None:
    failed = CitationCheck(ok=False, codes=("citation_record_missing",))
    assert failed.ok is False
    assert failed.codes == ("citation_record_missing",)
    assert CitationCheck(ok=True).codes == ()


def test_flags_from_checks_only_reports_failures() -> None:
    good_id = "12345678-1234-5678-1234-567812345678"
    bad_id = "87654321-4321-8765-4321-876543210987"
    results = {
        "claim-1": CitationCheck(ok=True, resolved_case_id=good_id),
        "claim-2": CitationCheck(
            ok=False, codes=("citation_value_mismatch",), resolved_case_id=bad_id
        ),
    }
    flags = flags_from_checks(results)
    assert len(flags) == 1
    assert flags[0]["claim"] == "claim-2"
    assert flags[0]["codes"] == ["citation_value_mismatch"]
    assert flags[0]["resolved_case_id"] == bad_id

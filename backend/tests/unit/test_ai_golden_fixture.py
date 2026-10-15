"""Guard the AI evaluation golden set (backend/tests/fixtures/ai_golden.jsonl).

The eval harness (scripts/eval_model.py) treats this file as the frozen source
of truth for grounding and abstention scoring. These tests pin its shape so the
fixture cannot silently rot (entries removed, statuses changed, facts dropped)
without the suite noticing.
"""

from __future__ import annotations

import pytest
from scripts.eval_model import GOLDEN_DEFAULT, _fact_present, _load_golden

VALID_KINDS = {"grounded", "abstention", "abstention_unknown"}
VALID_MODES = {"case", "graph", "copilot", "report"}
SHOWCASE_PREFIX = "SHOW-2026-"

# Expected composition of the frozen set (update deliberately if it changes).
EXPECTED_TOTAL = 33
EXPECTED_GROUNDED = 29
EXPECTED_ABSTENTION = 3  # foreign cases the caller cannot access -> 403
EXPECTED_UNKNOWN = 1  # nonexistent case -> 404


@pytest.fixture(scope="module")
def golden() -> list[dict]:
    return _load_golden(GOLDEN_DEFAULT)


def test_fixture_file_exists() -> None:
    assert GOLDEN_DEFAULT.is_file(), f"missing golden set: {GOLDEN_DEFAULT}"


def test_load_golden_does_not_raise(golden: list[dict]) -> None:
    # _load_golden raises on unknown kinds, missing id/question/facts, dupes.
    assert golden, "golden set must not be empty"


def test_entry_counts_are_pinned(golden: list[dict]) -> None:
    kinds = [e["kind"] for e in golden]
    assert len(golden) == EXPECTED_TOTAL, f"entry count changed: {len(golden)}"
    assert kinds.count("grounded") == EXPECTED_GROUNDED
    assert kinds.count("abstention") == EXPECTED_ABSTENTION
    assert kinds.count("abstention_unknown") == EXPECTED_UNKNOWN


def test_ids_are_unique_and_descriptive(golden: list[dict]) -> None:
    ids = [e["id"] for e in golden]
    assert len(ids) == len(set(ids))
    for entry_id in ids:
        assert entry_id.strip(), "ids must be non-blank"


def test_kinds_and_modes_are_valid(golden: list[dict]) -> None:
    for entry in golden:
        assert entry["kind"] in VALID_KINDS, entry["id"]
        assert entry.get("mode") in VALID_MODES, entry["id"]


def test_grounded_entries_target_showcase_cases(golden: list[dict]) -> None:
    """Grounded questions must cite a showcase case number the harness resolves."""
    case_numbers: set[str] = set()
    for entry in golden:
        if entry["kind"] != "grounded":
            continue
        case_number = entry.get("case_number")
        assert case_number, f"{entry['id']}: grounded entry missing case_number"
        assert str(case_number).startswith(SHOWCASE_PREFIX), (
            f"{entry['id']}: {case_number!r} is not a showcase case"
        )
        case_numbers.add(case_number)
    # All five showcase cases should be exercised.
    assert len(case_numbers) >= 5, f"only {len(case_numbers)} showcase cases covered"


def test_grounded_entries_have_facts(golden: list[dict]) -> None:
    for entry in golden:
        if entry["kind"] != "grounded":
            continue
        facts = entry.get("expected_facts")
        assert facts, f"{entry['id']}: grounded entry has no expected_facts"
        for fact in facts:
            assert isinstance(fact, str) and fact.strip(), f"{entry['id']}: bad fact {fact!r}"


def test_abstention_entries_declare_expected_status(golden: list[dict]) -> None:
    """Abstentions must pin the exact HTTP status (403 foreign / 404 unknown)."""
    for entry in golden:
        if entry["kind"] == "abstention":
            assert entry.get("expected_status") == 403, (
                f"{entry['id']}: foreign-case abstention must expect 403"
            )
            assert entry.get("case_number"), f"{entry['id']}: missing case_number"
        elif entry["kind"] == "abstention_unknown":
            assert entry.get("expected_status") == 404, (
                f"{entry['id']}: unknown-case abstention must expect 404"
            )


def test_fact_matching_normalises_case_and_underscores() -> None:
    # Case numbers keep their hyphens (they appear verbatim in answers).
    assert _fact_present("SHOW-2026-001", "the case is SHOW-2026-001 indeed")
    assert _fact_present("show-2026-001", "Case: SHOW-2026-001")
    assert _fact_present("bina bose", "Victim: Bina_Bose reported")
    assert _fact_present("loan fraud", "incident type: loan_fraud")
    assert not _fact_present("Delhi", "the answer mentions Mumbai only")


def test_questions_are_non_empty(golden: list[dict]) -> None:
    for entry in golden:
        question = entry.get("question", "")
        assert question.strip(), f"{entry['id']}: empty question"
        assert isinstance(entry.get("kind"), str)

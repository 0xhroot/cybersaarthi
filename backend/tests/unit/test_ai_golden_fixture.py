"""Guard the AI evaluation golden set (backend/tests/fixtures/ai_golden.jsonl).

The eval harness (scripts/eval_model.py) treats this file as the frozen source
of truth for grounding, abstention, analysis and hypothesize scoring. These
tests pin its shape so the fixture cannot silently rot (entries removed,
statuses changed, facts dropped, modes weakened) without the suite noticing,
and pin the new-mode scoring helpers (metric quotes, draft honesty regex,
fail-closed record verification).
"""

from __future__ import annotations

import uuid

import pytest
from app.db.postgres import Database
from app.models import Case
from scripts.eval_model import (
    DRAFT_CONFIDENCE_RE,
    GOLDEN_DEFAULT,
    METRIC_QUOTE_RE,
    METRIC_QUOTE_STRICT_RE,
    _fact_present,
    _load_golden,
    _record_belongs_to_case,
)

VALID_KINDS = {"grounded", "abstention", "abstention_unknown", "analysis", "hypothesize"}
VALID_MODES = {"case", "graph", "copilot", "report", "analysis", "hypothesize"}
SHOWCASE_PREFIX = "SHOW-2026-"

# Expected composition of the frozen set (update deliberately if it changes).
EXPECTED_TOTAL = 41
EXPECTED_GROUNDED = 30  # incl. one think-profile entry exercising Phase 1
EXPECTED_ABSTENTION = 3 + 2  # foreign cases -> 403, incl. analysis/hypothesize
EXPECTED_UNKNOWN = 1 + 1  # nonexistent case -> 404, incl. analysis mode
EXPECTED_ANALYSIS = 2
EXPECTED_HYPOTHESIZE = 2


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
    assert kinds.count("analysis") == EXPECTED_ANALYSIS
    assert kinds.count("hypothesize") == EXPECTED_HYPOTHESIZE


def test_ids_are_unique_and_descriptive(golden: list[dict]) -> None:
    ids = [e["id"] for e in golden]
    assert len(ids) == len(set(ids))
    for entry_id in ids:
        assert entry_id.strip(), "ids must be non-blank"


def test_kinds_and_modes_are_valid(golden: list[dict]) -> None:
    for entry in golden:
        assert entry["kind"] in VALID_KINDS, entry["id"]
        assert entry.get("mode") in VALID_MODES, entry["id"]


def test_new_mode_entries_run_and_score_the_same_mode(golden: list[dict]) -> None:
    """analysis/hypothesize entries must target a showcase case with their own
    mode — the harness scores exactly the mode it sends, so a mismatch would
    silently score the wrong contract."""
    new_mode_entries = [e for e in golden if e["kind"] in {"analysis", "hypothesize"}]
    assert new_mode_entries, "new-mode entries missing from the golden set"
    for entry in new_mode_entries:
        assert entry.get("mode") == entry["kind"], entry["id"]
        case_number = entry.get("case_number")
        assert case_number and str(case_number).startswith(SHOWCASE_PREFIX), (
            f"{entry['id']}: new-mode entries must target a showcase case"
        )


def test_security_abstentions_cover_the_new_modes(golden: list[dict]) -> None:
    """Cross-case denial must be exercised for analysis and hypothesize too —
    not only for the older modes (fail closed across the whole surface)."""
    covered = {
        e["mode"]
        for e in golden
        if e["kind"] in {"abstention", "abstention_unknown"}
    }
    assert {"analysis", "hypothesize"} <= covered


def test_think_profile_entry_exists(golden: list[dict]) -> None:
    """Phase 1's think path must be exercised by the eval (profile field)."""
    think_entries = [e for e in golden if e.get("profile") == "think"]
    assert think_entries, "no entry runs with profile=think"
    for entry in think_entries:
        assert entry["kind"] == "grounded", entry["id"]
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


# -- analysis scoring helpers ------------------------------------------------


def test_metric_quote_regexes_parse_both_contract_shapes() -> None:
    entity = "3a5af37c-e73c-4736-91a1-a8daf6b98b70"
    # DATA-line echo (the shape models naturally produce).
    echo = f"quote: metric=degree entity_id={entity} value=0.4213 score=1.0 rank=1"
    match = METRIC_QUOTE_RE.search(echo)
    assert match is not None
    assert match.group(1) == "degree"
    assert match.group(2).lower() == entity
    assert float(match.group(3)) == 0.4213
    # Strict @-form (earlier contract, still accepted).
    strict = f"metric:betweenness@{entity} = 6352.2204"
    match = METRIC_QUOTE_STRICT_RE.search(strict)
    assert match is not None
    assert match.group(1) == "betweenness"
    assert match.group(2).lower() == entity
    assert float(match.group(3)) == 6352.2204
    # Neither regex matches a number that lacks its entity id (unverifiable).
    assert METRIC_QUOTE_RE.search("metric=degree value=0.42") is None
    assert METRIC_QUOTE_STRICT_RE.search("metric:degree = 0.42") is None


# -- hypothesize scoring helpers ----------------------------------------------


def test_draft_confidence_gate_matches_the_prompt_ban() -> None:
    """The prompt forbids numeric confidence, percentages and odds; the gate
    must flag exactly those and leave qualitative hedging alone."""
    banned = [
        "confidence 0.8",
        "with high confidence",
        "probability 73%",
        "73 % likely",
        "odds of 2:1 against",
        "a 15% chance",
    ]
    for text in banned:
        assert DRAFT_CONFIDENCE_RE.search(text), f"should flag: {text!r}"
    allowed = [
        "This may be refuted by bank records.",
        "It is unlikely that the accounts share an owner.",
        "Possible owners are listed in the evidence.",
        "Missing: account opening documents.",
    ]
    for text in allowed:
        assert not DRAFT_CONFIDENCE_RE.search(text), f"should allow: {text!r}"


# -- fail-closed record verification -------------------------------------------


async def test_record_belongs_to_case_fails_closed(database: Database) -> None:
    """An id no row of THIS case explains must never verify: unknown ids,
    malformed ids and rows of another case all return False."""
    case = Case(id=uuid.uuid4(), case_number=f"EV-{uuid.uuid4().hex[:8]}", title="eval draft check")
    other = Case(id=uuid.uuid4(), case_number=f"EV-{uuid.uuid4().hex[:8]}", title="other case")
    factory = database.session_factory()
    async with factory() as session:
        # flush only — closing the session rolls the rows back.
        session.add_all([case, other])
        await session.flush()

        assert await _record_belongs_to_case(str(case.id), str(case.id), session) is True
        assert await _record_belongs_to_case(str(uuid.uuid4()), str(case.id), session) is False
        assert await _record_belongs_to_case("not-a-uuid", str(case.id), session) is False
        assert await _record_belongs_to_case(str(other.id), str(case.id), session) is False

"""Unit tests: AI hypothesis draft parsing (strict, fail-honest).

Drafts are human-review proposals only — these tests pin that malformed model
output is counted and skipped (never repaired), that ids are UUID-validated
and deduped, and that unverified citations are flagged rather than trusted.
"""

from __future__ import annotations

import json

from app.ai.drafts import (
    MAX_DRAFTS,
    MAX_TITLE_CHARS,
    mark_unverified_ids,
    parse_hypothesis_drafts,
)


def _block(obj: object) -> str:
    return f"```hypothesis\n{json.dumps(obj)}\n```"


def test_valid_block_is_parsed() -> None:
    eid = "3a5af37c-e73c-4736-91a1-a8daf6b98b70"
    answer = (
        "Here are candidates:\n\n"
        + _block(
            {
                "title": "Mule account reuse",
                "statement": "Account A was reused across both phishing waves.",
                "evidence_ids": [eid],
                "refutation": "A bank record showing separate owners.",
                "missing": "Account opening documents.",
            }
        )
        + "\n\nClosing thought."
    )
    drafts, errors = parse_hypothesis_drafts(answer)
    assert errors == 0
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["title"] == "Mule account reuse"
    assert draft["statement"] == "Account A was reused across both phishing waves."
    assert draft["evidence_ids"] == [eid]
    assert draft["refutation"] == "A bank record showing separate owners."
    assert draft["missing"] == "Account opening documents."


def test_multiple_blocks_keep_order() -> None:
    answers = [
        _block({"title": f"T{i}", "statement": f"S{i}", "evidence_ids": []})
        for i in range(3)
    ]
    drafts, errors = parse_hypothesis_drafts("\n".join(answers))
    assert errors == 0
    assert [d["title"] for d in drafts] == ["T0", "T1", "T2"]


def test_pretty_printed_json_block_is_parsed() -> None:
    block = (
        "```hypothesis\n"
        '{\n  "title": "T",\n  "statement": "S",\n  "evidence_ids": []\n}\n'
        "```"
    )
    drafts, errors = parse_hypothesis_drafts(block)
    assert errors == 0
    assert drafts[0]["title"] == "T"


def test_malformed_json_is_counted_not_repaired() -> None:
    answer = "```hypothesis\n{not json}\n```"
    drafts, errors = parse_hypothesis_drafts(answer)
    assert drafts == []
    assert errors == 1


def test_missing_title_or_statement_is_counted() -> None:
    answer = "\n".join(
        [
            _block({"title": "", "statement": "S"}),
            _block({"title": "T", "statement": "   "}),
            _block({"title": "T"}),  # no statement key at all
        ]
    )
    drafts, errors = parse_hypothesis_drafts(answer)
    assert drafts == []
    assert errors == 3


def test_non_object_json_is_counted() -> None:
    drafts, errors = parse_hypothesis_drafts("```hypothesis\n[1, 2, 3]\n```")
    assert drafts == []
    assert errors == 1


def test_evidence_ids_are_uuid_filtered_and_deduped() -> None:
    eid = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    answer = _block(
        {
            "title": "T",
            "statement": "S",
            "evidence_ids": [eid, eid.lower(), "not-a-uuid", 42, eid.upper()],
        }
    )
    drafts, errors = parse_hypothesis_drafts(answer)
    assert errors == 0
    assert drafts[0]["evidence_ids"] == [eid.lower()]


def test_non_list_evidence_ids_become_empty() -> None:
    answer = _block({"title": "T", "statement": "S", "evidence_ids": "oops"})
    drafts, errors = parse_hypothesis_drafts(answer)
    assert errors == 0
    assert drafts[0]["evidence_ids"] == []


def test_title_and_statement_are_bounded() -> None:
    answer = _block({"title": "x" * 600, "statement": "y" * 9_000})
    drafts, errors = parse_hypothesis_drafts(answer)
    assert errors == 0
    assert len(drafts[0]["title"]) == MAX_TITLE_CHARS
    assert len(drafts[0]["statement"]) == 4_000


def test_draft_count_is_capped_and_excess_is_counted() -> None:
    answer = "\n".join(
        _block({"title": f"T{i}", "statement": "S"}) for i in range(MAX_DRAFTS + 2)
    )
    drafts, errors = parse_hypothesis_drafts(answer)
    assert len(drafts) == MAX_DRAFTS
    assert errors == 2


def test_no_blocks_returns_empty_not_an_error() -> None:
    drafts, errors = parse_hypothesis_drafts("No structured suggestions here.")
    assert drafts == []
    assert errors == 0


def test_mark_unverified_ids_flags_only_unknown_ids() -> None:
    known = "AAAAAAAa-bbbb-cccc-dddd-eeeeeeeeeeee"
    unknown = "11111111-2222-3333-4444-555555555555"
    drafts = [
        {"evidence_ids": [known, unknown]},
        {"evidence_ids": []},
    ]
    mark_unverified_ids(drafts, {known})
    assert drafts[0]["unverified_ids"] == [unknown]
    assert drafts[1]["unverified_ids"] == []

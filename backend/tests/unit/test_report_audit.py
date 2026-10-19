"""Unit tests: report-audit deterministic helpers (phase 6, feature 10).

Replays the frozen golden fixture (``report_audit_checks.json``) through the
pure helpers - spans, amounts, dates, arithmetic, chronology, currency
conflicts, counter-evidence tokens and support-assessment validity - and
covers the shape-validation contracts of the model reply parsers. No model,
database, network or storage is involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.report_audit import (
    REPORT_AUDIT_RULES_VERSION,
    assessment_is_valid,
    check_arithmetic,
    chronology_issues,
    claim_tokens,
    currency_conflicts,
    draft_sha256,
    normalize_claims,
    normalize_digits,
    parse_amounts,
    parse_assessment,
    parse_claims_reply,
    parse_dates,
    unverified_quotes,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "report_audit_checks.json"
)


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rules_version_frozen() -> None:
    assert REPORT_AUDIT_RULES_VERSION == "1.0.0"


def test_normalize_digits_maps_devanagari() -> None:
    assert normalize_digits("२०२६-०१-१४ ५०००") == "2026-01-14 5000"


def test_draft_sha256_is_deterministic() -> None:
    assert draft_sha256("abc") == draft_sha256("abc")
    assert draft_sha256("abc") != draft_sha256("abd")


def test_golden_fixture_replay() -> None:
    data = _golden()
    assert data["cases"], "golden fixture must not be empty"
    for case in data["cases"]:
        name = case["name"]
        kind = case["kind"]
        expect = case["expect"]
        if kind == "dates":
            parsed, unparsed = parse_dates(case["text"])
            assert parsed == expect["dates"], name
            assert unparsed == expect["unparsed"], name
        elif kind == "amounts":
            assert parse_amounts(case["text"]) == expect["amounts"], name
        elif kind == "arithmetic":
            result = check_arithmetic(case["text"], parse_amounts(case["text"]))
            assert result == expect["result"], name
        elif kind == "chronology":
            assert chronology_issues(case["claims"]) == expect["issues"], name
        elif kind == "currency":
            claims = [
                {
                    "claim_index": index,
                    "char_start": item["char_start"],
                    "amounts": parse_amounts(item["text"]),
                }
                for index, item in enumerate(case["claims"])
            ]
            assert currency_conflicts(claims) == expect["conflicts"], name
        elif kind == "tokens":
            tokens = claim_tokens(case["text"], parse_amounts(case["text"]))
            assert tokens == expect["tokens"], name
        elif kind == "claims":
            claims, truncated = normalize_claims(
                case["raw_claims"], draft=case["draft"], max_claims=case["max_claims"]
            )
            assert truncated == expect["truncated"], name
            keys = (
                "claim_index",
                "claim_id",
                "span_valid",
                "category_valid",
                "extraction_valid",
                "extraction_problems",
                "cited_ids",
            )
            got = [{key: claim[key] for key in keys} for claim in claims]
            assert got == expect["claims"], name
        elif kind == "assessment":
            result = parse_assessment(json.dumps(case["reply"]))
            assert result is not None, name
            valid, bad = assessment_is_valid(result, case["excerpts"])
            assert valid == expect["valid"], name
            assert bad == expect["unverified"], name
        else:  # pragma: no cover - fixture authoring guard
            raise AssertionError(f"unknown golden case kind {kind!r}")


def test_parse_claims_reply_rejects_bad_shapes() -> None:
    assert parse_claims_reply('{"claims": []}') == []
    assert parse_claims_reply("not json at all") is None
    assert parse_claims_reply('{"claims": "not a list"}') is None
    assert parse_claims_reply('{"claims": [1, 2]}') is None
    assert parse_claims_reply('{"no_claims": []}') is None


def test_normalize_claims_flags_duplicate_ids_and_bad_fields() -> None:
    draft = "Account balance is 5,000."
    claims, truncated = normalize_claims(
        [
            {
                "claim_id": "dup",
                "text": draft,
                "char_start": 0,
                "char_end": len(draft),
                "category": "quantity",
                "cited_ids": [],
            },
            {
                "claim_id": "dup",
                "text": draft,
                "char_start": 0,
                "char_end": len(draft),
                "category": "quantity",
                "cited_ids": [],
            },
            {
                "claim_id": "bad",
                "text": draft,
                "char_start": "zero",
                "char_end": len(draft),
                "category": "quantity",
                "cited_ids": ["evidence:x", 7],
            },
        ],
        draft=draft,
        max_claims=30,
    )
    assert truncated == 0
    assert claims[0]["extraction_valid"] is True
    assert claims[1]["extraction_valid"] is False  # duplicate claim_id
    assert claims[1]["extraction_problems"] == ["claim_id"]
    assert claims[2]["extraction_valid"] is False
    assert set(claims[2]["extraction_problems"]) == {"char_span", "cited_ids"}
    assert claims[2]["cited_ids"] == []  # malformed id lists are never trusted


def test_parse_assessment_rejects_bad_shapes() -> None:
    assert (
        parse_assessment('{"assessment": "made_up", "explanation": "x", "quoted_spans": []}')
        is None
    )
    assert parse_assessment('{"assessment": "supported", "quoted_spans": []}') is None
    assert (
        parse_assessment('{"assessment": "supported", "explanation": "x", "quoted_spans": "nope"}')
        is None
    )
    assert (
        parse_assessment('{"assessment": "supported", "explanation": "x", "quoted_spans": [1]}')
        is None
    )
    assert parse_assessment("not json") is None


def test_unverified_quotes_is_substring_exact() -> None:
    assert unverified_quotes(["a b"], "prefix a b suffix") == []
    assert unverified_quotes(["a b c"], "prefix a b suffix") == ["a b c"]


def test_parse_dates_day_first_is_documented_and_stable() -> None:
    # Day-first for slash dates is the documented convention (Indian context).
    parsed, unparsed = parse_dates("filed 05/02/2026 and 2026-02-05")
    assert parsed == ["2026-02-05", "2026-02-05"]
    assert unparsed == 0

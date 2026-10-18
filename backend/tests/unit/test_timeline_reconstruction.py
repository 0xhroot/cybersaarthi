"""Phase 3 feature B: timeline reconstruction - pure parsing/drafts, fixtures.

Pins the deterministic timestamp parser (originals and zones preserved, one
documented naive->UTC assumption that is always flagged, nothing invented),
the record/artifact draft generation, and the duplicate/conflict/overlap
annotation. The golden fixture runner asserts exact parse outcomes and draft
counts; the guard asserts the set actually exercises clean, missing and
ambiguous timestamps plus records with no time fields at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.timeline_reconstruction import (
    EventDraft,
    ExistingEventFacts,
    annotate_drafts,
    classify_time_semantics,
    drafts_from_artifact,
    drafts_from_record,
    looks_like_time_field,
    parse_timestamp,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_intelligence"
    / "timeline_checks.json"
)


def _load() -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["parse_cases"] and data["record_cases"], "fixture file must not be empty"
    return data


# -- golden fixture runner ------------------------------------------------------


def test_fixture_set_exercises_every_outcome() -> None:
    """Anti-vacuous guard: clean, missing and ambiguous outcomes are covered."""
    data = _load()
    parse_cases = data["parse_cases"]
    assert any(c["expect"]["parseable"] for c in parse_cases)
    assert any(not c["expect"]["parseable"] for c in parse_cases)
    assert any(c["expect"].get("tz_assumed") for c in parse_cases if c["expect"]["parseable"])
    assert any(
        c["expect"].get("granularity") == "date" for c in parse_cases if c["expect"]["parseable"]
    )
    assert any(c["expect"].get("tz") for c in parse_cases if c["expect"]["parseable"])

    record_cases = data["record_cases"]
    assert any(c["expect"]["drafts"] > 0 for c in record_cases)
    assert any(c["expect"]["drafts"] == 0 for c in record_cases)
    assert any(c["expect"]["missing"] > 0 for c in record_cases)
    assert any(c["expect"]["ambiguous"] > 0 for c in record_cases)
    ids = [c["id"] for c in parse_cases] + [c["id"] for c in record_cases]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"


def test_every_parse_case_produces_expected_timestamp() -> None:
    for case in _load()["parse_cases"]:
        parsed = parse_timestamp(case["value"])
        expect = case["expect"]
        if not expect["parseable"]:
            assert parsed is None, case["id"]
            continue
        assert parsed is not None, case["id"]
        assert parsed.occurred_at is not None, case["id"]
        assert parsed.occurred_at.isoformat() == expect["utc"], case["id"]
        assert parsed.tz == expect["tz"], case["id"]
        assert parsed.granularity == expect["granularity"], case["id"]
        assert parsed.tz_assumed is expect["tz_assumed"], case["id"]
        # The original string is always preserved verbatim (trimmed only).
        if isinstance(case["value"], str):
            assert parsed.original == case["value"].strip(), case["id"]


def test_every_record_case_produces_expected_drafts() -> None:
    for case in _load()["record_cases"]:
        drafts, _skipped = drafts_from_record(
            record_id="rec-1",
            evidence_file_id="ev-1",
            record_no=1,
            raw_data=case["raw_data"],
            filename="statement.csv",
        )
        expect = case["expect"]
        assert len(drafts) == expect["drafts"], case["id"]
        assert sum(1 for d in drafts if d.missing_timestamp) == expect["missing"], case["id"]
        assert sum(1 for d in drafts if d.tz_assumed) == expect["ambiguous"], case["id"]
        for draft in drafts:
            if not draft.missing_timestamp:
                assert draft.occurred_at is not None and draft.occurred_at.tzinfo is UTC, case["id"]
            assert draft.original, case["id"]
            assert draft.locator()["field"], case["id"]


# -- direct parser and semantics tests -------------------------------------------


def test_parser_handles_datetime_instances_with_and_without_zone() -> None:
    aware = parse_timestamp(datetime(2026, 3, 15, 14, 30, tzinfo=UTC))
    assert aware is not None and aware.tz == "UTC" and not aware.tz_assumed
    naive = parse_timestamp(datetime(2026, 3, 15, 14, 30))
    assert naive is not None and naive.tz_assumed and naive.tz is None


def test_negative_utc_offset_is_labelled() -> None:
    parsed = parse_timestamp("2026-03-15T14:30:00-07:00")
    assert parsed is not None
    assert parsed.tz == "-07:00"
    assert parsed.occurred_at is not None
    assert parsed.occurred_at.isoformat() == "2026-03-15T21:30:00+00:00"


def test_semantics_classification_is_deterministic() -> None:
    assert classify_time_semantics("extracted_at") == "extraction"
    assert classify_time_semantics("uploaded_at") == "uploaded"
    assert classify_time_semantics("document_created") == "document_created"
    assert classify_time_semantics("txn_date") == "record_occurs_on"
    assert classify_time_semantics("settlement_date") == "record_occurs_on"
    assert looks_like_time_field("txn_date") and not looks_like_time_field("city")


def test_missing_and_present_fields_are_distinguished() -> None:
    """Empty values yield nothing; unparseable strong fields yield a proposal."""
    drafts, skipped = drafts_from_record(
        record_id="r",
        evidence_file_id="ev",
        record_no=3,
        raw_data={"txn_date": "", "incident_date": "unknown", "city": "Mumbai"},
        filename=None,
    )
    assert skipped >= 1
    assert len(drafts) == 1 and drafts[0].missing_timestamp
    assert drafts[0].original == "unknown"
    assert drafts[0].occurred_at is None, "a datetime must never be invented"


def test_artifact_events_without_established_time_stay_missing() -> None:
    drafts = drafts_from_artifact(
        artifact_id="a1",
        payload={
            "fields": {
                "transaction_dates": ["15/03/2026"],
                "events": ["Vendor call happened in March", "Payment made on 2026-03-16"],
            }
        },
        record_no=2,
        evidence_file_id="ev",
        source_record_id="rec",
        filename=None,
    )
    dates = [d for d in drafts if d.locator_field == "transaction_dates"]
    events = [d for d in drafts if d.locator_field == "events"]
    assert len(dates) == 1 and dates[0].occurred_at is not None
    assert dates[0].semantics == "record_occurs_on"
    assert len(events) == 2
    missing = [d for d in events if d.missing_timestamp]
    dated = [d for d in events if not d.missing_timestamp]
    assert len(missing) == 1 and len(dated) == 1
    assert missing[0].semantics == "statement_refers_to_event"
    assert dated[0].occurred_at is not None


# -- annotation: duplicates, conflicts, overlaps ---------------------------------


def _draft(
    *,
    record_id: str = "rec-1",
    field: str = "txn_date",
    occurred_at: datetime | None = None,
    title: str = "txn_date: 2026-03-15",
    origin: str = "record",
    evidence_file_id: str = "ev-1",
    missing: bool = False,
) -> EventDraft:
    return EventDraft(
        title=title,
        description=None,
        occurred_at=occurred_at,
        original="2026-03-15",
        tz=None,
        tz_assumed=False,
        granularity="datetime",
        semantics="record_occurs_on",
        origin=origin,
        evidence_file_id=evidence_file_id,
        source_record_id=record_id,
        record_no=1,
        locator_field=field,
        locator_index=None,
        missing_timestamp=missing,
    )


def test_duplicate_drafts_flag_the_second_not_the_first() -> None:
    at = datetime(2026, 3, 15, tzinfo=UTC)
    first = _draft(record_id="rec-1", occurred_at=at)
    second = _draft(record_id="rec-2", occurred_at=at)
    counts = annotate_drafts([first, second], [])
    assert counts["duplicates"] == 1
    assert "duplicate_proposal" not in first.flags
    assert "duplicate_proposal" in second.flags
    assert second.conflicts and second.conflicts[0]["with"]["record_no"] == 1


def test_raw_and_artifact_disagreement_is_a_conflicting_timestamp() -> None:
    raw = _draft(
        record_id="rec-1",
        field="txn_date",
        occurred_at=datetime(2026, 3, 15, tzinfo=UTC),
        origin="record",
    )
    derived = _draft(
        record_id="rec-1",
        field="transaction_dates",
        occurred_at=datetime(2026, 3, 16, tzinfo=UTC),
        origin="artifact",
        title="transaction_dates: 2026-03-16",
    )
    counts = annotate_drafts([raw, derived], [])
    assert counts["conflicts"] == 2
    assert "conflicting_timestamp" in raw.flags and "conflicting_timestamp" in derived.flags


def test_agreeing_sources_are_not_conflicts() -> None:
    at = datetime(2026, 3, 15, tzinfo=UTC)
    raw = _draft(record_id="rec-1", field="txn_date", occurred_at=at, origin="record")
    derived = _draft(
        record_id="rec-1",
        field="transaction_dates",
        occurred_at=datetime(2026, 3, 15, 9, tzinfo=UTC),
        origin="artifact",
        title="transaction_dates: 2026-03-15",
    )
    counts = annotate_drafts([raw, derived], [])
    assert counts["conflicts"] == 0


def test_overlap_with_authoritative_timeline_is_flagged_not_replaced() -> None:
    draft = _draft(occurred_at=datetime(2026, 3, 15, 10, tzinfo=UTC))
    existing = ExistingEventFacts(
        id="evt-1",
        evidence_file_id="ev-1",
        occurred_at=datetime(2026, 3, 15, 8, tzinfo=UTC),
        title="Evidence uploaded: statement.csv",
        proposal_key=None,
    )
    counts = annotate_drafts([draft], [existing])
    assert counts["overlaps"] == 1
    assert "overlaps_existing_timeline" in draft.flags
    assert draft.existing_event_id == "evt-1"


def test_missing_timestamp_drafts_never_join_duplicate_or_overlap_sets() -> None:
    missing = _draft(occurred_at=None, missing=True)
    existing = ExistingEventFacts(
        id="evt-1",
        evidence_file_id="ev-1",
        occurred_at=datetime(2026, 3, 15, 8, tzinfo=UTC),
        title="t",
        proposal_key=None,
    )
    counts = annotate_drafts([missing], [existing])
    assert counts == {"duplicates": 0, "conflicts": 0, "overlaps": 0}


def test_proposal_key_is_stable_and_content_derived() -> None:
    at = datetime(2026, 3, 15, tzinfo=UTC)
    a = _draft(occurred_at=at)
    b = _draft(occurred_at=at)
    c = _draft(occurred_at=datetime(2026, 3, 16, tzinfo=UTC))
    assert a.proposal_key() == b.proposal_key(), "identical drafts must share a key"
    assert a.proposal_key() != c.proposal_key(), "different instants are different proposals"


def test_payload_carries_semantics_and_provenance() -> None:
    payload = _draft(
        occurred_at=datetime(2026, 3, 15, tzinfo=UTC),
        missing=False,
    ).as_payload()
    assert payload["type"] == "timeline_proposal"
    assert payload["kind"] == "case_event"
    assert payload["time_semantics"] == "record_occurs_on"
    assert payload["source_locator"]["field"] == "txn_date"
    assert payload["evidence_file_id"] == "ev-1"
    assert isinstance(payload["proposal_key"], str) and payload["proposal_key"]

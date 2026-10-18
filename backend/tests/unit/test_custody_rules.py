"""Phase 2: custody rule engine (feature 9) - pure, deterministic, non-vacuous.

The rules decide pass/fail over recorded facts only: a clean, fully
documented custody history must yield ZERO findings (false-positive guard),
and each defect must surface exactly its documented rule. Severity semantics
are pinned here: missing information is info/warning and never a tampering
claim; only recomputed-hash discrepancies may be ``critical``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.custody import (
    CustodyEventFacts,
    CustodySnapshot,
    evaluate_custody,
    evaluate_orphaned_events,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _dt(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _event(
    event_id: str = "e1",
    *,
    event_type: str = "collected",
    occurred_at: datetime | None = None,
    recorded_at: datetime | None = None,
    collector: str | None = "Officer A",
    transferor: str | None = None,
    recipient: str | None = None,
    evidence_file_id: str | None = "ev1",
    recorded_sha256: str | None = None,
) -> CustodyEventFacts:
    occurred = occurred_at or _dt(2026, 3, 1)
    # Documentation normally follows the event (default +1h), never precedes it.
    recorded = recorded_at or (occurred + timedelta(hours=1))
    return CustodyEventFacts(
        id=event_id,
        event_type=event_type,
        occurred_at=occurred,
        recorded_at=recorded,
        collector=collector,
        transferor=transferor,
        recipient=recipient,
        evidence_file_id=evidence_file_id,
        recorded_sha256=recorded_sha256,
    )


def _snapshot(**overrides: object) -> CustodySnapshot:
    base: dict[str, object] = {
        "case_id": "c1",
        "evidence_id": "ev1",
        "evidence_sha256": SHA_A,
        "evidence_created_at": _dt(2026, 1, 1),
        "audit_entry_count": 1,
        "events": (),
        "object_present": True,
        "object_hash": SHA_A,
        "checked_at": _dt(2026, 10, 10),
        "future_skew_seconds": 300,
    }
    base.update(overrides)
    return CustodySnapshot(**base)  # type: ignore[arg-type]


def _rules(snapshot: CustodySnapshot) -> list[str]:
    return [issue.rule for issue in evaluate_custody(snapshot)]


# -- clean path: zero findings (false-positive guard) --------------------------


def test_clean_full_lifecycle_yields_zero_findings() -> None:
    """Collect -> transfer -> receipt -> verify, all policy-compliant.

    Non-vacuous: a rich event set is configured, yet nothing fires - optional
    location/method/notes are deliberately absent and must NOT be findings.
    """
    events = (
        _event(
            "e1",
            event_type="collected",
            occurred_at=_dt(2026, 2, 1),
            collector="Officer A",
            recorded_sha256=SHA_A,
        ),
        _event(
            "e2",
            event_type="transferred",
            occurred_at=_dt(2026, 3, 1),
            collector=None,
            transferor="Officer A",
            recipient="Lab B",
        ),
        _event(
            "e3",
            event_type="received",
            occurred_at=_dt(2026, 3, 5),
            collector=None,
            recipient="Lab B",
        ),
        _event(
            "e4",
            event_type="verified",
            occurred_at=_dt(2026, 4, 1),
            collector=None,
            recorded_sha256=SHA_A,
        ),
    )
    issues = evaluate_custody(_snapshot(events=events))
    assert issues == ()


def test_matching_hash_and_audit_documentation_silence_all_hash_rules() -> None:
    assert _rules(_snapshot()) == []


# -- hash integrity ------------------------------------------------------------


def test_hash_mismatch_is_critical_with_both_digests() -> None:
    issues = evaluate_custody(_snapshot(object_hash=SHA_B))
    assert [i.rule for i in issues] == ["custody.hash_mismatch"]
    issue = issues[0]
    assert issue.severity == "critical"
    assert issue.observed["expected_sha256"] == SHA_A
    assert issue.observed["calculated_sha256"] == SHA_B
    assert issue.missing == ()


def test_missing_recorded_hash_is_info_documentation_gap_not_tampering() -> None:
    issues = evaluate_custody(_snapshot(evidence_sha256=None))
    assert [i.rule for i in issues] == ["custody.hash_missing"]
    assert issues[0].severity == "info"
    assert issues[0].missing == ("evidence.sha256",)


def test_missing_source_bytes_is_warning_never_a_tampering_claim() -> None:
    issues = evaluate_custody(_snapshot(object_present=False, object_hash=None))
    assert [i.rule for i in issues] == ["custody.source_missing"]
    assert issues[0].severity == "warning"
    assert "not proof of tampering" in issues[0].message


def test_event_recorded_hash_discrepancy_is_critical_and_scoped_to_event() -> None:
    events = (_event("e9", recorded_sha256=SHA_B),)
    issues = evaluate_custody(_snapshot(events=events, object_hash=SHA_A))
    assert [i.rule for i in issues] == ["custody.recorded_hash_mismatch"]
    assert issues[0].event_ids == ("e9",)
    assert issues[0].severity == "critical"


def test_event_recorded_hash_matching_object_is_silent() -> None:
    events = (_event("e9", recorded_sha256=SHA_A),)
    assert _rules(_snapshot(events=events)) == []


# -- policy party fields -------------------------------------------------------


def test_transferred_without_recipient_names_the_missing_field() -> None:
    events = (
        _event("e2", event_type="transferred", collector=None, transferor="Officer A"),
        # Acknowledged by a receipt so only the policy-field rule can fire.
        _event(
            "e3",
            event_type="received",
            occurred_at=_dt(2026, 3, 5),
            collector=None,
            recipient="Lab B",
        ),
    )
    issues = evaluate_custody(_snapshot(events=events))
    assert [i.rule for i in issues] == ["custody.missing_required_field"]
    assert issues[0].event_ids == ("e2",)
    assert issues[0].missing == ("recipient",)


def test_collected_without_collector_is_a_finding() -> None:
    events = (_event("e1", event_type="collected", collector=None),)
    issues = evaluate_custody(_snapshot(events=events))
    assert [i.rule for i in issues] == ["custody.missing_required_field"]
    assert issues[0].missing == ("collector",)


def test_optional_fields_absent_never_fire() -> None:
    """location/method/notes are optional: absence must stay silent."""
    events = (_event("e1", event_type="collected", collector="Officer A"),)
    assert evaluate_custody(_snapshot(events=events)) == ()


# -- duplicates and chronology -------------------------------------------------


def test_duplicate_type_and_time_flags_both_events() -> None:
    when = _dt(2026, 3, 1)
    events = (
        _event("e1", occurred_at=when, recorded_at=when),
        _event("e2", occurred_at=when, recorded_at=when),
    )
    issues = evaluate_custody(_snapshot(events=events))
    assert [i.rule for i in issues] == ["custody.duplicate_event"]
    assert issues[0].event_ids == ("e1", "e2")
    assert issues[0].observed["count"] == 2


def test_future_occurrence_beyond_skew_is_flagged() -> None:
    events = (_event("e1", occurred_at=_dt(2027, 1, 1)),)
    issues = evaluate_custody(_snapshot(events=events))
    assert "custody.chronology_future" in [i.rule for i in issues]
    future = next(i for i in issues if i.rule == "custody.chronology_future")
    assert future.observed["tolerance_seconds"] == 300


def test_documented_before_it_happened_is_flagged() -> None:
    events = (
        _event(
            "e1",
            occurred_at=_dt(2026, 6, 1),
            recorded_at=_dt(2026, 5, 1),
            collector="Officer A",
        ),
    )
    issues = evaluate_custody(_snapshot(events=events))
    assert [i.rule for i in issues] == ["custody.chronology_recorded_before_occurred"]


def test_receipt_before_every_transfer_is_out_of_order() -> None:
    events = (
        _event(
            "e3",
            event_type="received",
            occurred_at=_dt(2026, 2, 1),
            collector=None,
            recipient="Lab B",
        ),
        _event(
            "e2",
            event_type="transferred",
            occurred_at=_dt(2026, 3, 1),
            collector=None,
            transferor="Officer A",
            recipient="Lab B",
        ),
    )
    rules = _rules(_snapshot(events=events))
    assert "custody.chronology_received_before_transfer" in rules
    # The same receipt also fails to acknowledge the later transfer.
    assert "custody.unacknowledged_transfer" in rules


def test_acknowledged_transfer_is_silent() -> None:
    events = (
        _event(
            "e2",
            event_type="transferred",
            occurred_at=_dt(2026, 3, 1),
            collector=None,
            transferor="Officer A",
            recipient="Lab B",
        ),
        _event(
            "e3",
            event_type="received",
            occurred_at=_dt(2026, 3, 5),
            collector=None,
            recipient="Lab B",
        ),
    )
    assert _rules(_snapshot(events=events)) == []


def test_unacknowledged_transfer_reports_the_transfer_and_latest_receipt() -> None:
    events = (
        _event(
            "e2",
            event_type="transferred",
            occurred_at=_dt(2026, 3, 1),
            collector=None,
            transferor="Officer A",
            recipient="Lab B",
        ),
    )
    issues = evaluate_custody(_snapshot(events=events))
    assert [i.rule for i in issues] == ["custody.unacknowledged_transfer"]
    assert issues[0].event_ids == ("e2",)
    assert issues[0].observed["latest_received_at"] is None
    assert issues[0].missing == ("receipt (received event at or after the transfer)",)


def test_standalone_receipt_without_any_transfer_is_not_a_finding() -> None:
    """Semantics: receipts acknowledge transfers; with none recorded there is
    no pairing to contradict - only ``no_documented_custody`` concerns apply
    and this snapshot has audit documentation."""
    events = (
        _event(
            "e3",
            event_type="received",
            occurred_at=_dt(2026, 3, 5),
            collector=None,
            recipient="Lab B",
        ),
    )
    assert _rules(_snapshot(events=events)) == []


# -- documentation presence and orphans ---------------------------------------


def test_no_events_and_no_audit_is_an_info_level_gap_only() -> None:
    issues = evaluate_custody(_snapshot(audit_entry_count=0))
    assert [i.rule for i in issues] == ["custody.no_documented_custody"]
    assert issues[0].severity == "info"


def test_upload_audit_entry_satisfies_documentation() -> None:
    assert _rules(_snapshot(audit_entry_count=1)) == []


def test_orphaned_events_reference_loss_is_detected_and_scoped() -> None:
    tied = _event("e1", evidence_file_id="ev1")
    lost_a = _event("e2", evidence_file_id=None)
    lost_b = _event("e3", evidence_file_id=None)
    clean = evaluate_orphaned_events((tied,), case_id="c1")
    assert clean == ()
    issues = evaluate_orphaned_events((tied, lost_a, lost_b), case_id="c1")
    assert [i.rule for i in issues] == ["custody.orphaned_event"]
    assert issues[0].event_ids == ("e2", "e3")
    assert issues[0].evidence_id is None
    assert issues[0].observed["orphaned_count"] == 2


# -- payload stability ---------------------------------------------------------


def test_findings_are_deterministic_and_free_of_wall_clock_values() -> None:
    """Same facts -> byte-identical payloads (content-addressed dedupe works),
    and the payload never embeds the evaluation time."""
    snapshot = _snapshot(object_hash=SHA_B)
    first = [i.as_payload() for i in evaluate_custody(snapshot)]
    second = [i.as_payload() for i in evaluate_custody(snapshot)]
    assert first == second
    for payload in first:
        assert "checked_at" not in payload
        assert payload["rule_set_version"] == "1.0.0"
        assert payload["policy_version"] == "1.0.0"
        assert payload["evidence_id"] == "ev1"

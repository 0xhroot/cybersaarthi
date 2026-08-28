"""Unit tests for deterministic relationship extraction."""

from __future__ import annotations

import uuid

from app.services.extraction import Mention
from app.services.relationships import MAX_RELATIONSHIPS_PER_RECORD, extract_relationships


def _mention(entity_type: str, canonical: str, start: int = -1, end: int = -1) -> Mention:
    return Mention(
        entity_type=entity_type,
        raw=canonical,
        canonical=canonical,
        display=canonical,
        blocking_key=canonical[:4],
        source="field",
        confidence=None,
        start=start,
        end=end,
    )


def _resolved(mentions: list[Mention]) -> dict[tuple[str, str], uuid.UUID]:
    return {(m.entity_type, m.canonical): uuid.uuid4() for m in mentions}


def test_structured_field_pairs() -> None:
    mentions = [
        _mention("person", "rajesh kumar"),
        _mention("phone", "919876543210"),
        _mention("vehicle", "MH12AB1234"),
        _mention("organization", "techsecure"),
    ]
    rels = extract_relationships(mentions, _resolved(mentions), is_structured=True, text="")
    types = sorted(rel.relationship_type.value for rel in rels)
    assert types == ["called", "owns", "works_for"]
    assert all(rel.evidence_type == "field" for rel in rels)


def test_structured_pairs_dedupe_repeated_values() -> None:
    person = _mention("person", "rajesh kumar")
    phones = [_mention("phone", "919876543210"), _mention("phone", "919876543210")]
    rels = extract_relationships(
        [person, *phones], _resolved([person, phones[0]]), is_structured=True, text=""
    )
    assert [rel.relationship_type.value for rel in rels] == ["called"]


def test_unresolved_mentions_do_not_participate() -> None:
    person = _mention("person", "rajesh kumar")
    phone = _mention("phone", "919876543210")
    rels = extract_relationships([person, phone], _resolved([person]), is_structured=True, text="")
    assert rels == []


def test_co_occurrence_in_same_sentence_window() -> None:
    text = "Rajesh Kumar called 9876543210 yesterday."
    mentions = [
        _mention("person", "rajesh kumar", start=0, end=12),
        _mention("phone", "919876543210", start=18, end=28),
    ]
    rels = extract_relationships(mentions, _resolved(mentions), is_structured=False, text=text)
    assert len(rels) == 1
    assert rels[0].relationship_type.value == "called"
    assert rels[0].evidence_type == "co_occurrence"
    assert rels[0].snippet == text
    assert "co-occurrence" in rels[0].explanation


def test_mentions_in_separate_windows_do_not_link() -> None:
    text = "Rajesh Kumar left the city. 9876543210 was the contact."
    mentions = [
        _mention("person", "rajesh kumar", start=0, end=12),
        _mention("phone", "919876543210", start=40, end=50),
    ]
    rels = extract_relationships(mentions, _resolved(mentions), is_structured=False, text=text)
    assert rels == []


def test_structured_relationships_are_capped() -> None:
    persons = [_mention("person", f"person {i}") for i in range(5)]
    phones = [_mention("phone", f"9199{i:07d}") for i in range(5)]
    mentions = [*persons, *phones]
    rels = extract_relationships(mentions, _resolved(mentions), is_structured=True, text="")
    assert len(rels) == MAX_RELATIONSHIPS_PER_RECORD
    assert all(rel.relationship_type.value == "called" for rel in rels)


def test_account_pairs_become_transfers() -> None:
    accounts = [_mention("account", f"2200440011{i:02d}") for i in range(2)]
    rels = extract_relationships(accounts, _resolved(accounts), is_structured=True, text="")
    assert [rel.relationship_type.value for rel in rels] == ["transferred_to"]

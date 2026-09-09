"""Unit tests for entity mention extraction (field, rule, NER)."""

from __future__ import annotations

from app.services.extraction import (
    Mention,
    extract_record_mentions,
    field_type_for_header,
    sentence_windows,
)

# A model name that will never be installed, forcing the NER path to degrade to
# zero mentions so the tests stay deterministic and offline.
_NO_MODEL = "__not_installed__"


def mention_keys(mentions: list[Mention]) -> set[tuple[str, str]]:
    return {(m.entity_type, m.canonical) for m in mentions}


def test_field_alias_header_mapping() -> None:
    assert field_type_for_header("full_name") == "person"
    assert field_type_for_header("mobile_no") == "phone"


def test_substring_header_hints() -> None:
    assert field_type_for_header("mobile_no_2") == "phone"
    assert field_type_for_header("vehicle_registration") == "vehicle"
    assert field_type_for_header("organisation_name") == "organization"


def test_unmapped_header_returns_none() -> None:
    assert field_type_for_header("random_column") is None


def test_field_mentions_mapped_by_alias() -> None:
    record = {
        "name": "Rajesh Kumar",
        "phone": "+91-98765-43210",
        "organization": "TechSecure Pvt Ltd",
        "vehicle_no": "MH12AB1234",
        "city": "Mumbai",
    }
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert ("person", "rajesh kumar") in keys
    assert ("phone", "919876543210") in keys
    assert ("organization", "techsecure") in keys
    assert ("vehicle", "MH12AB1234") in keys
    assert ("location", "mumbai") in keys


def test_unmapped_header_is_ignored() -> None:
    record = {"misc_notes": "nothing useful"}
    assert extract_record_mentions(record, _NO_MODEL) == []


def test_packed_phone_field_splits_values() -> None:
    record = {"phone": "9876543210 9123456789"}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert keys == {("phone", "919876543210"), ("phone", "919123456789")}


def test_rule_phone_mention_in_free_text() -> None:
    record = {"text": "Suspect contacted 9876543210 from Mumbai."}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert ("phone", "919876543210") in keys


def test_rule_vehicle_mention_in_free_text() -> None:
    record = {"text": "Car MH12AB1234 spotted at Mall Road"}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert ("vehicle", "MH12AB1234") in keys


def test_grouped_aadhaar_is_document_not_phone() -> None:
    record = {"text": "Aadhaar 1234 5678 9012 seen"}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert keys == {("document", "123456789012")}


def test_bare_twelve_digit_run_is_not_a_phone() -> None:
    # Without a label an unbroken 12-digit run is treated as an account/UID,
    # never a phone number.
    record = {"text": "220044001122"}
    assert extract_record_mentions(record, _NO_MODEL) == []


def test_account_label_extracts_account() -> None:
    record = {"text": "Transfer made from account 220044001122 confirmed."}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert ("account", "220044001122") in keys


def test_document_label_extracts_document() -> None:
    record = {"text": "Passport BJ1234567 details verified"}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert ("document", "BJ1234567") in keys


def test_ner_is_offline_safe() -> None:
    # A missing/lazy-loaded model yields zero NER mentions, not a crash.
    record = {"text": "Rakesh Sharma met at Infosys in Bengaluru."}
    assert extract_record_mentions(record, _NO_MODEL) == []


def test_dedupe_mentions() -> None:
    record = {"name": "Rajesh Kumar", "subject_name": "Rajesh Kumar"}
    keys = mention_keys(extract_record_mentions(record, _NO_MODEL))
    assert [key for key in keys if key[0] == "person"] == [("person", "rajesh kumar")]


def test_mention_carries_provenance() -> None:
    mentions = extract_record_mentions({"phone": "9876543210"}, _NO_MODEL)
    assert len(mentions) == 1
    assert mentions[0].source == "field"
    assert mentions[0].blocking_key == "919876543210"


def test_sentence_windows() -> None:
    text = "First sentence. Second line\nThird!"
    assert sentence_windows(text) == [(0, 15), (16, 27), (28, 34)]

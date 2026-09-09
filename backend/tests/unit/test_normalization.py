"""Unit tests for value normalisation and blocking keys."""

from __future__ import annotations

from app.services.normalization import (
    blocking_key,
    normalize_account,
    normalize_document,
    normalize_location,
    normalize_organization,
    normalize_person,
    normalize_phone,
    normalize_value,
    normalize_vehicle,
)


def test_phone_canonical_adds_india_code() -> None:
    # 10-digit local numbers collapse onto the +91 international form so that
    # "+91-98765-43210", "09876543210" and "9876543210" all resolve together.
    assert normalize_phone("+91-98765-43210").canonical == "919876543210"
    assert normalize_phone("+91 98765 43210").canonical == "919876543210"
    assert normalize_phone("09876543210").canonical == "919876543210"
    assert normalize_phone("9876543210").canonical == "919876543210"


def test_phone_keeps_explicit_international_number() -> None:
    result = normalize_phone("+1 415 555 0000")
    assert result.is_valid
    assert result.canonical == "14155550000"


def test_phone_keeps_short_desk_numbers() -> None:
    result = normalize_phone("1234567")
    assert result.is_valid
    assert result.canonical == "1234567"


def test_phone_rejects_too_short() -> None:
    result = normalize_phone("12345")
    assert result.is_valid is False
    assert result.canonical == ""


def test_phone_rejects_non_numeric() -> None:
    assert normalize_phone("call me").is_valid is False


def test_vehicle_normalization() -> None:
    result = normalize_vehicle("mh12 ab1234")
    assert result.is_valid
    assert result.canonical == "MH12AB1234"
    assert result.display == "MH12 AB1234"


def test_vehicle_rejects_letter_only() -> None:
    assert normalize_vehicle("ABC").is_valid is False


def test_vehicle_rejects_digit_only() -> None:
    assert normalize_vehicle("123456").is_valid is False


def test_account_normalization() -> None:
    result = normalize_account("220044001122")
    assert result.is_valid
    assert result.canonical == "220044001122"


def test_account_normalization_removes_separators() -> None:
    result = normalize_account("AB/CD 123")
    assert result.canonical == "ABCD123"


def test_account_rejects_too_short() -> None:
    assert normalize_account("12345").is_valid is False


def test_document_normalization_digits() -> None:
    result = normalize_document("1234 5678 9012")
    assert result.is_valid
    assert result.canonical == "123456789012"


def test_document_normalization_alphanumeric() -> None:
    result = normalize_document("AB123456")
    assert result.is_valid
    assert result.canonical == "AB123456"


def test_document_rejects_too_short() -> None:
    assert normalize_document("AB12").is_valid is False


def test_person_normalization_strips_honorifics() -> None:
    result = normalize_person("Mr. Rajesh Kumar")
    assert result.canonical == "rajesh kumar"
    assert result.display == "Rajesh Kumar"


def test_person_normalization_strips_punctuated_honorifics() -> None:
    result = normalize_person("Dr. Anita Shroff.")
    assert result.canonical == "anita shroff"


def test_person_normalization_lowercases() -> None:
    assert normalize_person("RAJESH KUMAR").canonical == "rajesh kumar"


def test_person_normalization_display_capitalises() -> None:
    result = normalize_person("rajesh kumar")
    assert result.display == "Rajesh Kumar"


def test_person_rejects_empty_and_honorific_only() -> None:
    assert normalize_person("").is_valid is False
    assert normalize_person("Mr.").is_valid is False


def test_organization_strips_common_suffixes() -> None:
    assert normalize_organization("TechSecure Pvt Ltd.").canonical == "techsecure"
    assert normalize_organization("The Global Systems Inc").canonical == "global systems"


def test_location_normalization() -> None:
    result = normalize_location("Mumbai, Maharashtra")
    assert result.is_valid
    assert result.canonical == "mumbai maharashtra"


def test_blocking_key_person_uses_surname_prefix() -> None:
    # Surname variants (Mehra/Mehta) land in the same bucket so fuzzy review can fire.
    assert blocking_key("person", "arjun mehra") == "meh_a"
    assert blocking_key("person", "arjun mehta") == "meh_a"
    assert blocking_key("person", "rajesh kumar") == "kum_r"


def test_blocking_key_single_token_person() -> None:
    assert blocking_key("person", "gabbar") == "gabb"


def test_blocking_key_phone_is_canonical() -> None:
    assert blocking_key("phone", "919876543210") == "919876543210"


def test_blocking_key_document_uses_digit_prefix() -> None:
    assert blocking_key("document", "123456789012") == "123456"


def test_normalize_value_dispatches_by_type() -> None:
    assert normalize_value("person", "Ms. Anita Roy").canonical == "anita roy"
    assert normalize_value("phone", "9820000000").canonical == "919820000000"
    assert normalize_value("vehicle", "dl1c1234567").canonical == "DL1C1234567"
    assert normalize_value("bad_type", "anything").is_valid is False

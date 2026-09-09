"""Deterministic normalisation of entity values into canonical forms.

Every entity type gets a ``(is_valid, canonical, display)`` outcome. Canonical
values drive identity matching; display values keep a human-friendly surface
form. Blocking keys bound the candidate comparison set so resolution never
degrades into a full cross-product scan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HONORIFICS = {
    "mr",
    "mrs",
    "ms",
    "mx",
    "dr",
    "prof",
    "sri",
    "shri",
    "smt",
    "kum",
    "er",
    "c",
    "master",
    "miss",
    "mister",
    "warrant",
    "inspector",
    "constable",
    "sir",
}

ORGANIZATION_SUFFIXES = (
    "inc",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "pvt",
    "private",
    "pllc",
    "co",
    "company",
    "gmbh",
    "sa",
    "pt",
)

PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
VEHICLE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[\d]{1,2}[A-Z]{1,2}[\d]{1,4}(?![A-Za-z0-9])")
# Aadhaar-like UIDs: only the grouped form is trusted, so a bare 12-digit
# bank account number is not misclassified as an identity document.
AADHAAR_RE = re.compile(r"\b(?:\d{4}[ -]\d{4}[ -]\d{4}|\d{4}\s\d{4}\s\d{4})\b")
ACCOUNT_LABEL_RE = re.compile(
    r"(?i)\b(?:account\s*(?:no\.?|number)?|a/c)\s*[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9 .-]{4,28}?)"
    r"(?=\s+[A-Za-z]{2,}\b|\s*$|\.\s|\Z)"
)
DOCUMENT_LABEL_RE = re.compile(
    r"(?i)\b(?:passport|pan no\.?|pancard|document no\.?|"
    r"id(?:entification)? number|dl no\.?)\s*[:#]?\s*"
    r"([A-Z0-9][A-Z0-9 .-]{4,28}?)"
    r"(?=\s+[A-Za-z]{2,}\b|\s*$|\.\s|\Z)"
)


@dataclass(frozen=True)
class NormalizedValue:
    is_valid: bool
    canonical: str
    display: str


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def normalize_phone(raw: str) -> NormalizedValue:
    digits = _digits(raw)
    digits = digits.lstrip("0")
    if len(digits) == 10 and digits[0] != "0":
        digits = "91" + digits
    if not digits or not (7 <= len(digits) <= 15):
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, digits, raw.strip())


def normalize_vehicle(raw: str) -> NormalizedValue:
    canonical = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if (
        not canonical
        or not (4 <= len(canonical) <= 12)
        or not (re.search(r"\d", canonical) and re.search(r"[A-Z]", canonical))
    ):
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, canonical, raw.strip().upper())


def normalize_account(raw: str) -> NormalizedValue:
    canonical = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not canonical or len(canonical) < 6 or len(canonical) > 30:
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, canonical, raw.strip())


def normalize_document(raw: str) -> NormalizedValue:
    system = re.sub(r"\D", "", raw)
    if 10 <= len(system) <= 16:
        return NormalizedValue(True, system, raw.strip())
    canonical = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not canonical or not (6 <= len(canonical) <= 30):
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, canonical, raw.strip().upper())


def normalize_person(raw: str) -> NormalizedValue:
    tokens = [word for word in re.split(r"\s+", raw.strip().lower()) if word]
    tokens = [token.rstrip(".:,") for token in tokens]
    tokens = [token for token in tokens if token and token not in HONORIFICS]
    if not tokens:
        return NormalizedValue(False, "", raw.strip())
    canonical = " ".join(tokens)
    display = " ".join(token.capitalize() for token in tokens)
    return NormalizedValue(True, canonical, display)


def _clean_text(raw: str) -> str:
    text = raw.strip().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_organization(raw: str) -> NormalizedValue:
    tokens = _clean_text(raw).split()
    if not tokens:
        return NormalizedValue(False, "", raw.strip())
    if tokens[0] == "the":
        tokens = tokens[1:]
    while tokens and tokens[-1] in ORGANIZATION_SUFFIXES:
        tokens = tokens[:-1]
    if not tokens:
        return NormalizedValue(False, "", raw.strip())
    canonical = " ".join(tokens)
    display = raw.strip()
    return NormalizedValue(True, canonical, display)


def normalize_location(raw: str) -> NormalizedValue:
    canonical = _clean_text(raw)
    if not canonical:
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, canonical, raw.strip())


def normalize_event(raw: str) -> NormalizedValue:
    canonical = _clean_text(raw)
    if not canonical:
        return NormalizedValue(False, "", raw.strip())
    return NormalizedValue(True, canonical, raw.strip())


def normalize_value(entity_type: str, raw: str) -> NormalizedValue:
    value = str(raw).strip()
    if not value:
        return NormalizedValue(False, "", value)
    if entity_type == "person":
        return normalize_person(value)
    if entity_type == "phone":
        return normalize_phone(value)
    if entity_type == "vehicle":
        return normalize_vehicle(value)
    if entity_type == "account":
        return normalize_account(value)
    if entity_type == "document":
        return normalize_document(value)
    if entity_type == "organization":
        return normalize_organization(value)
    if entity_type == "location":
        return normalize_location(value)
    if entity_type == "event":
        return normalize_event(value)
    return NormalizedValue(False, "", value)


def blocking_key(entity_type: str, canonical: str) -> str:
    """Bucket key used to prune the candidate set during resolution."""

    if entity_type in {"phone", "account", "vehicle"}:
        return canonical
    if entity_type == "person":
        tokens = canonical.split()
        if len(tokens) >= 2:
            return f"{tokens[-1][:3]}_{tokens[0][0]}"
        return tokens[0][:4]
    if entity_type == "document":
        return canonical[:6]
    return canonical[:4]

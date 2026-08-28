"""Entity mention extraction from a single source record.

Three deterministic sources feed mentions:

* **FIELD** - structured headers on CSV/JSON records (field-alias mapping);
* **RULE** - regular-expression extractors for phones, vehicles, Aadhaar and
  labelled account/document numbers in free text;
* **NER** - spaCy named entity recognition for persons, organisations,
  locations and events.

Each mention carries provenance (source, offsets), and has been validated and
normalised so only defensible mentions flow into resolution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.nlp import extract_ner_mentions
from app.services.normalization import (
    AADHAAR_RE,
    ACCOUNT_LABEL_RE,
    DOCUMENT_LABEL_RE,
    PHONE_RE,
    VEHICLE_RE,
    blocking_key,
    normalize_value,
)

FIELD_ALIASES: dict[str, str] = {
    # person
    "name": "person",
    "full_name": "person",
    "person_name": "person",
    "suspect_name": "person",
    "accused": "person",
    "accused_name": "person",
    "contact_person": "person",
    "subject_name": "person",
    "victim_name": "person",
    "witness_name": "person",
    "applicant_name": "person",
    "name_of_person": "person",
    # phone
    "phone": "phone",
    "phone_number": "phone",
    "phone_no": "phone",
    "mobile": "phone",
    "mobile_number": "phone",
    "mobile_no": "phone",
    "contact": "phone",
    "contact_no": "phone",
    "telephone": "phone",
    "caller": "phone",
    "caller_number": "phone",
    "callee": "phone",
    "receiver_number": "phone",
    # vehicle
    "vehicle_no": "vehicle",
    "vehicle_number": "vehicle",
    "registration_no": "vehicle",
    "reg_no": "vehicle",
    "vehicle_registration": "vehicle",
    "vehicle": "vehicle",
    "car_no": "vehicle",
    "bike_no": "vehicle",
    # account
    "account_no": "account",
    "account_number": "account",
    "bank_account": "account",
    "account_id": "account",
    # document
    "aadhaar": "document",
    "aadhaar_no": "document",
    "aadhaar_number": "document",
    "pan": "document",
    "pan_number": "document",
    "pancard": "document",
    "passport": "document",
    "passport_number": "document",
    "document_no": "document",
    "document_id": "document",
    "id_card": "document",
    "driving_license": "document",
    "dl_no": "document",
    # organization
    "organization": "organization",
    "organisation": "organization",
    "org": "organization",
    "company": "organization",
    "employer": "organization",
    "works_for": "organization",
    "institute": "organization",
    "firm": "organization",
    "bank_name": "organization",
    # location
    "location": "location",
    "address": "location",
    "city": "location",
    "place": "location",
    "visit_place": "location",
    "location_visited": "location",
    "area": "location",
    "district": "location",
    "state": "location",
    "destination": "location",
    # event
    "event": "event",
    "incident": "event",
    "event_name": "event",
    "activity": "event",
}

# Ordered fallback: substring triggers applied only when the exact alias misses.
# Kept deliberately conservative to avoid false positives (e.g. "pan" inside
# "city_planning" or "contact" inside an address column).
SUBSTRING_HINTS: tuple[tuple[str, str], ...] = (
    ("mobile_no", "phone"),
    ("mobile_number", "phone"),
    ("vehicle", "vehicle"),
    ("_reg_no", "vehicle"),
    ("reg_number", "vehicle"),
    ("aadhaar", "document"),
    ("aadhar", "document"),
    ("passport", "document"),
    ("pancard", "document"),
    ("employer", "organization"),
    ("organisation", "organization"),
    ("company", "organization"),
    ("address", "location"),
)

FIELD_TEXT_COLUMNS = ("remarks", "note", "notes", "description", "remarks_description", "summary")

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Mention:
    entity_type: str
    raw: str
    canonical: str
    display: str
    blocking_key: str
    source: str
    confidence: float | None
    start: int = -1
    end: int = -1


def _normalized_header(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower()).strip("_")
    return text or None


def field_type_for_header(header: str) -> str | None:
    if header in FIELD_ALIASES:
        return FIELD_ALIASES[header]
    for fragment, entity_type in SUBSTRING_HINTS:
        if fragment in header:
            return entity_type
    return None


def _as_string(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return " ".join(str(item) for item in value)
    return str(value)


def _mention(
    entity_type: str,
    raw: str,
    *,
    source: str,
    confidence: float | None = None,
    start: int = -1,
    end: int = -1,
) -> Mention | None:
    normalized = normalize_value(entity_type, raw)
    if not normalized.is_valid:
        return None
    return Mention(
        entity_type=entity_type,
        raw=raw,
        canonical=normalized.canonical,
        display=normalized.display,
        blocking_key=blocking_key(entity_type, normalized.canonical),
        source=source,
        confidence=confidence,
        start=start,
        end=end,
    )


def _field_mentions(record: dict[str, Any]) -> list[Mention]:
    mentions: list[Mention] = []
    for raw_header, value in record.items():
        header = _normalized_header(raw_header)
        if header is None:
            continue
        entity_type = field_type_for_header(header)
        if entity_type is None:
            continue
        text = _as_string(value).strip()
        if not text:
            continue
        direct = _mention(entity_type, text, source="field")
        if direct is not None:
            mentions.append(direct)
            continue
        # The field may pack several values (e.g. "9876543210 9123456789").
        for token in re.split(r"[\s,;|]+", text):
            split_mention = _mention(entity_type, token, source="field")
            if split_mention is not None:
                mentions.append(split_mention)
    return mentions


def _rule_mentions(text: str) -> list[Mention]:
    mentions: list[Mention] = []
    for match in PHONE_RE.finditer(text):
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 12 and not raw.lstrip().startswith("+"):
            if raw.isdigit() or AADHAAR_RE.fullmatch(raw):
                continue  # bare/UID-like runs are accounts or identity numbers
        mention = _mention("phone", raw, source="rule", start=match.start(), end=match.end())
        if mention is not None:
            mentions.append(mention)
    for match in VEHICLE_RE.finditer(text):
        mention = _mention(
            "vehicle", match.group(0), source="rule", start=match.start(), end=match.end()
        )
        if mention is not None:
            mentions.append(mention)
    for match in AADHAAR_RE.finditer(text):
        mention = _mention(
            "document", match.group(0), source="rule", start=match.start(), end=match.end()
        )
        if mention is not None:
            mentions.append(mention)
    for match in ACCOUNT_LABEL_RE.finditer(text):
        mention = _mention(
            "account", match.group(1), source="rule", start=match.start(), end=match.end()
        )
        if mention is not None:
            mentions.append(mention)
    for match in DOCUMENT_LABEL_RE.finditer(text):
        mention = _mention(
            "document", match.group(1), source="rule", start=match.start(), end=match.end()
        )
        if mention is not None:
            mentions.append(mention)
    return mentions


def _ner_mentions(text: str, model_name: str) -> list[Mention]:
    mentions: list[Mention] = []
    for ner in extract_ner_mentions(text, model_name):
        normalized = normalize_value(ner.entity_type, ner.text)
        if not normalized.is_valid:
            continue
        mentions.append(
            Mention(
                entity_type=ner.entity_type,
                raw=ner.text,
                canonical=normalized.canonical,
                display=normalized.display,
                blocking_key=blocking_key(ner.entity_type, normalized.canonical),
                source="ner",
                confidence=None,
                start=ner.start,
                end=ner.end,
            )
        )
    return mentions


def _record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for header, value in record.items():
        normalized = _normalized_header(header) or ""
        if normalized and normalized in FIELD_ALIASES:
            continue  # field-mapped columns are handled separately
        parts.append(_as_string(value))
    return " ".join(part for part in parts if part.strip())


def _dedupe(mentions: list[Mention]) -> list[Mention]:
    seen: set[tuple[str, str]] = set()
    unique: list[Mention] = []
    for mention in mentions:
        key = (mention.entity_type, mention.canonical)
        if key in seen:
            continue
        seen.add(key)
        unique.append(mention)
    return unique


def extract_record_mentions(record: dict[str, Any], model_name: str) -> list[Mention]:
    """Extract, validate and normalise all entity mentions in one record."""

    mentions = _field_mentions(record)
    text = _record_text(record)
    mentions.extend(_rule_mentions(text))
    mentions.extend(_ner_mentions(text, model_name))
    return _dedupe(mentions)


def sentence_windows(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of sentence-like windows in ``text``."""
    windows: list[tuple[int, int]] = []
    start = 0
    for part in SENTENCE_SPLIT_RE.split(text):
        end = start + len(part)
        if part.strip():
            windows.append((start, end))
        start = end + 1
    return windows

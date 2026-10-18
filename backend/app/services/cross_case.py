"""Cross-case pattern discovery (phase 4, feature B) - deterministic layer.

The pipeline is: explicit authorized scope -> per-case indicator extraction
(documented normalization rules, bounded) -> hash-key grouping (no all-pairs
comparison) -> candidate artifacts with a deterministic classification ->
human review. The local model is never consulted here; it can only explain an
already-recorded candidate (feature B4, a later subphase), and even then it
may only cite identifiers that are already on the candidate's own provenance
lists.

Security invariants enforced here and re-checked at every stage:

* every stage works only on the scope stored on the job at submission time;
* the runner re-derives ``crosscase.read`` *and* per-case visibility from
  fresh rows before reading anything and between bounded stages, failing the
  job closed (``CROSS_CASE_SCOPE_REVOKED``) on any revocation;
* read paths re-fetch visibility per response and omit - never redact - a
  candidate that touches an inaccessible case;
* ``similarity_name_only`` candidates are informational: the server refuses
  to approve them, so name similarity can never become an authoritative link.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiHTTPException
from app.core import rbac
from app.core.codes import (
    CODE_ARTIFACT_NOT_FOUND,
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_CROSS_CASE_ACTIVE,
    CODE_CROSS_CASE_SCOPE_REVOKED,
)
from app.core.config import Settings, get_settings
from app.models import (
    AnalysisJob,
    Case,
    CaseMember,
    DerivedArtifact,
    Entity,
    EntityAlias,
    EvidenceFile,
    Role,
    SourceRecord,
    User,
    UserRole,
)
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services.authorization import still_authorized_for_cross_case
from app.services.normalization import PHONE_RE, normalize_account, normalize_phone

logger = logging.getLogger(__name__)

CROSSCASE_RULES_VERSION = "crosscase/1.0.0"
CROSSCASE_ARTIFACT_KIND = "cross_case_link"
CROSSCASE_ANCHOR_FEATURE = "cross_case"

# -- vocabulary -----------------------------------------------------------------

IDENTIFIER_KINDS: tuple[str, ...] = (
    "account_ref",
    "device",
    "domain",
    "email",
    "evidence_hash",
    "phone",
    "txn_id",
    "url",
)
NAME_KIND = "name"
REVIEWED_ALIAS_KIND = "reviewed_alias"
INDICATOR_KINDS: tuple[str, ...] = (*IDENTIFIER_KINDS, NAME_KIND, REVIEWED_ALIAS_KIND)

CLASSIFICATIONS: tuple[str, ...] = (
    "exact_identifier",
    "normalized_identifier",
    "reviewed_alias",
    "similarity_name_only",
)

CLASSIFICATION_SEMANTICS = (
    "deterministic label over the candidate's shared signals: exact_identifier "
    "(the shared value's raw strings are identical on every side), "
    "normalized_identifier (identical only after the documented normalization), "
    "reviewed_alias (at least one side contributes a Phase 3-reviewed alias for "
    "the value), similarity_name_only (a shared normalized name with no shared "
    "identifier - informational, review disabled). Not a probability."
)
SCORE_SEMANTICS = (
    "0-100 signal-strength band: a fixed base per classification plus bounded "
    "bonuses for additional shared identifier kinds and supporting-record "
    "breadth. It is NOT a probability, NOT a confidence score, and is only "
    "comparable within one rules version."
)
GRAPH_FRESHNESS_NOTE = (
    "discovery reads entity aliases and source records directly and never "
    "queries Neo4j, so it does not depend on graph projection freshness; a "
    "projection sync cannot make a candidate stale or fresh"
)
LIMITATIONS: tuple[str, ...] = (
    "a shared identifier is a candidate signal, never proof that one person, "
    "account or event is behind both cases",
    "indicators are extracted per run from the authorized cases' own records, "
    "entities and reviewed aliases; coverage equals ingestion coverage and "
    "merged, review or rejected entities never contribute",
    "normalization can over- or under-merge by design; every original value is "
    "preserved verbatim on its own side for the reviewer to compare",
    "the run is bounded (scope, records, indicators, candidates); bounds are "
    "reported, never silently truncated",
    "review is mandatory: approval records a reviewed cross-case relationship "
    "and never merges entities, writes canonical relationships or touches the "
    "graph",
)

# -- documented normalization ---------------------------------------------------

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# First-hit-wins key rules over flattened ``raw_data`` keys (leaf key matched,
# case-insensitively). Reading a key the source actually provided is not
# inference; a value with no listed key is only classified by full-value
# pattern match below, never by guessing from content alone.
TXN_KEYS = frozenset(
    {"transaction_id", "txn_id", "upi_txn_id", "utr", "reference_no", "ref_no", "transaction_ref"}
)
ACCOUNT_KEYS = frozenset(
    {"account", "account_no", "account_number", "account_id", "bank_account", "upi_id", "vpa"}
)
PHONE_KEYS = frozenset(
    {
        "phone",
        "phone_number",
        "mobile",
        "mobile_number",
        "contact",
        "contact_number",
        "beneficiary_phone",
        "payee_phone",
        "receiver_number",
        "sender_phone",
    }
)
EMAIL_KEYS = frozenset({"email", "email_id", "email_address", "mail"})
URL_KEYS = frozenset({"url", "link", "website", "upi_link"})
DEVICE_KEYS = frozenset({"device", "device_id", "deviceid", "imei", "ip_address"})
NAME_KEYS = frozenset({"name", "full_name", "person_name"})

KEY_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("txn_id", TXN_KEYS),
    ("account_ref", ACCOUNT_KEYS),
    ("phone", PHONE_KEYS),
    ("email", EMAIL_KEYS),
    ("url", URL_KEYS),
    ("device", DEVICE_KEYS),
    ("name", NAME_KEYS),
)

# Entity types that carry an indicator kind; the rest contribute nothing.
ENTITY_KIND_BY_TYPE: dict[str, str] = {
    "person": NAME_KIND,
    "organization": NAME_KIND,
    "phone": "phone",
    "account": "account_ref",
}


def normalize_email(value: str) -> str:
    """Case-folded and trimmed; local-part case-sensitivity is ignored."""
    return value.strip().casefold()


def normalize_url(value: str) -> str:
    """Case-folded, trimmed, one trailing slash stripped."""
    normalized = value.strip().casefold()
    return normalized[:-1] if normalized.endswith("/") else normalized


def normalize_domain(value: str) -> str | None:
    """Lower-cased host without a leading ``www.``; from a URL or an email."""
    candidate = value.strip()
    if "@" in candidate:
        candidate = candidate.rsplit("@", 1)[1]
    candidate = candidate.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    candidate = candidate.removeprefix("www.").casefold()
    return candidate if DOMAIN_RE.match(candidate) else None


def normalize_txn(value: str) -> str | None:
    """Alphanumerics only, upper-cased (``TXN-SIH-001`` -> ``TXNSIH001``)."""
    canonical = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return canonical if len(canonical) >= 4 else None


def normalize_device(value: str) -> str | None:
    """Trimmed and case-folded with internal whitespace removed."""
    canonical = re.sub(r"\s+", "", value.strip()).casefold()
    return canonical if len(canonical) >= 3 else None


def normalize_name(value: str) -> str | None:
    """Case-folded with collapsed whitespace and edge punctuation stripped."""
    canonical = re.sub(r"\s+", " ", value.strip()).casefold().strip(" .,")
    has_letter = any(character.isalpha() for character in canonical)
    return canonical if len(canonical) >= 2 and has_letter else None


def normalize_reviewed_alias(value: str) -> str | None:
    """Case-folded with collapsed whitespace (no pattern assumptions)."""
    canonical = re.sub(r"\s+", " ", value.strip()).casefold()
    return canonical if canonical else None


def _normalize_for(kind: str, value: str) -> str | None:
    """Documented per-kind normalization; ``None`` means 'not a valid value'."""
    if kind == "phone":
        parsed = normalize_phone(value)
        return parsed.canonical if parsed.is_valid else None
    if kind == "account_ref":
        parsed = normalize_account(value)
        return parsed.canonical if parsed.is_valid else None
    if kind == "txn_id":
        return normalize_txn(value)
    if kind == "email":
        stripped = value.strip()
        return normalize_email(stripped) if EMAIL_RE.match(stripped) else None
    if kind == "url":
        stripped = value.strip()
        return normalize_url(stripped) if URL_RE.match(stripped) else None
    if kind == "domain":
        return normalize_domain(value)
    if kind == "device":
        return normalize_device(value)
    if kind == "evidence_hash":
        # An evidence file's sha256 is already a canonical lowercase hex digest
        # when it came from the upload; accept only that exact form (trimmed,
        # case-folded) so a placeholder or truncated value is skipped rather
        # than guessed at.
        canonical = value.strip().lower()
        return canonical if SHA256_RE.fullmatch(canonical) else None
    if kind in (NAME_KIND, REVIEWED_ALIAS_KIND):
        return normalize_name(value) if kind == NAME_KIND else normalize_reviewed_alias(value)
    return None


def detect_unkeyed_kind(value: str) -> tuple[str, str] | None:
    """Pattern-only kind for values under no documented key (full matches).

    Emails and URLs are unambiguous patterns; a phone match requires the whole
    value to look like one (<=24 chars) so long digit strings that only look
    numeric are not silently promoted to phone identifiers.
    """
    stripped = value.strip()
    if EMAIL_RE.match(stripped):
        return ("email", normalize_email(stripped))
    if URL_RE.match(stripped):
        return ("url", normalize_url(stripped))
    if len(stripped) <= 24 and PHONE_RE.fullmatch(stripped):
        parsed = normalize_phone(stripped)
        if parsed.is_valid:
            return ("phone", parsed.canonical)
    return None


# -- JSONB payload narrowing (payloads are untyped dicts; narrow before use) ---


def _payload_str_list(payload: dict[str, object], key: str) -> list[str]:
    """A stored list-of-strings under *key*, or [] when absent/mistyped."""
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _payload_sides(payload: dict[str, object]) -> list[dict[str, object]]:
    """The stored ``sides`` list, keeping only dict entries."""
    value = payload.get("sides")
    if not isinstance(value, list):
        return []
    return [side for side in value if isinstance(side, dict)]


# -- indicators -----------------------------------------------------------------


@dataclass(frozen=True)
class Indicator:
    """One deterministic cross-case signal with full provenance."""

    kind: str
    value_normalized: str
    value_original: str
    case_id: str
    entity_id: str | None = None
    source_record_id: str | None = None
    evidence_file_id: str | None = None
    reviewed: bool = False

    def sort_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.kind,
            self.value_normalized,
            self.value_original,
            self.entity_id or "",
            self.source_record_id or "",
            self.evidence_file_id or "",
        )


@dataclass
class CaseExtraction:
    """Per-case extraction result plus honest counter state."""

    case_id: str
    indicators: list[Indicator] = field(default_factory=list)
    records_scanned: int = 0
    records_bounded: bool = False
    evidence_files_scanned: int = 0
    evidence_files_bounded: bool = False
    entity_rows: int = 0
    entities_bounded: bool = False
    alias_rows: int = 0
    aliases_bounded: bool = False
    indicators_bounded: bool = False
    values_skipped_invalid: int = 0


def _flatten_raw(raw: dict[str, Any], *, depth: int = 0) -> list[tuple[str, str]]:
    """Flatten one nesting level; scalars only (never dict/list leaves)."""
    out: list[tuple[str, str]] = []
    for key, value in raw.items():
        if isinstance(value, dict) and depth < 1:
            for sub_key, sub_value in _flatten_raw(value, depth=depth + 1):
                out.append((f"{key}.{sub_key}", str(sub_value)))
        elif isinstance(value, bool):
            continue
        elif isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                out.append((key, text))
    return out


def _emit(
    out: list[Indicator],
    counters: CaseExtraction,
    *,
    kind: str,
    original: str,
    case_id: str,
    entity_id: str | None = None,
    source_record_id: str | None = None,
    evidence_file_id: str | None = None,
    reviewed: bool = False,
) -> None:
    normalized = _normalize_for(kind, original)
    if normalized is None:
        counters.values_skipped_invalid += 1
        return
    out.append(
        Indicator(
            kind=kind,
            value_normalized=normalized,
            value_original=original,
            case_id=case_id,
            entity_id=entity_id,
            source_record_id=source_record_id,
            evidence_file_id=evidence_file_id,
            reviewed=reviewed,
        )
    )


def extract_record_indicators(
    record: SourceRecord, *, case_id: str, counters: CaseExtraction
) -> list[Indicator]:
    """Documented record rules: key table first, full-value patterns second."""
    raw = record.raw_data
    if not isinstance(raw, dict):
        return []
    out: list[Indicator] = []
    record_id = str(record.id)
    evidence_id = str(record.evidence_file_id)
    for key, value in _flatten_raw(raw):
        leaf_key = key.rsplit(".", 1)[-1].casefold()
        kind: str | None = None
        for candidate, keys in KEY_RULES:
            if leaf_key in keys:
                kind = candidate
                break
        if kind is None:
            detected = detect_unkeyed_kind(value)
            if detected is not None:
                _emit(
                    out,
                    counters,
                    kind=detected[0],
                    original=value,
                    case_id=case_id,
                    source_record_id=record_id,
                    evidence_file_id=evidence_id,
                )
                if detected[0] == "email":
                    domain = normalize_domain(value)
                    if domain is not None:
                        _emit(
                            out,
                            counters,
                            kind="domain",
                            original=domain,
                            case_id=case_id,
                            source_record_id=record_id,
                            evidence_file_id=evidence_id,
                        )
                continue
            continue
        _emit(
            out,
            counters,
            kind=kind,
            original=value,
            case_id=case_id,
            source_record_id=record_id,
            evidence_file_id=evidence_id,
        )
        if kind == "email":
            domain = normalize_domain(value)
            if domain is not None:
                _emit(
                    out,
                    counters,
                    kind="domain",
                    original=domain,
                    case_id=case_id,
                    source_record_id=record_id,
                    evidence_file_id=evidence_id,
                )
        elif kind == "url":
            domain = normalize_domain(value)
            if domain is not None:
                _emit(
                    out,
                    counters,
                    kind="domain",
                    original=domain,
                    case_id=case_id,
                    source_record_id=record_id,
                    evidence_file_id=evidence_id,
                )
    return out


def extract_entity_indicators(
    entity: Entity, *, case_id: str, counters: CaseExtraction
) -> list[Indicator]:
    """Active entities contribute by type; merged/rejected entities never do."""
    kind = ENTITY_KIND_BY_TYPE.get(entity.entity_type)
    if kind is None:
        return []
    out: list[Indicator] = []
    for original in dict.fromkeys([entity.canonical_value, entity.display_value]):
        _emit(
            out,
            counters,
            kind=kind,
            original=str(original),
            case_id=case_id,
            entity_id=str(entity.id),
        )
    return out


def extract_alias_indicators(
    alias: EntityAlias,
    *,
    entity: Entity,
    case_id: str,
    counters: CaseExtraction,
) -> list[Indicator]:
    """Reviewed aliases (Phase 3 ``alias_type="resolution"``) always emit their
    own signal kind, plus the natural identifier kind when the value matches a
    documented pattern or the entity's type."""
    reviewed = alias.alias_type == "resolution"
    out: list[Indicator] = []
    original = str(alias.alias_value)
    if reviewed:
        _emit(
            out,
            counters,
            kind=REVIEWED_ALIAS_KIND,
            original=original,
            case_id=case_id,
            entity_id=str(entity.id),
            source_record_id=alias.source_record_id or None,
            reviewed=True,
        )
    natural_kind = ENTITY_KIND_BY_TYPE.get(entity.entity_type)
    if natural_kind is not None:
        _emit(
            out,
            counters,
            kind=natural_kind,
            original=original,
            case_id=case_id,
            entity_id=str(entity.id),
            source_record_id=alias.source_record_id or None,
            reviewed=reviewed,
        )
    detected = detect_unkeyed_kind(original)
    if detected is not None and detected[0] != natural_kind:
        _emit(
            out,
            counters,
            kind=detected[0],
            original=original,
            case_id=case_id,
            entity_id=str(entity.id),
            source_record_id=alias.source_record_id or None,
            reviewed=reviewed,
        )
    return out


def collect_case_indicators(
    *,
    case_id: str,
    records: list[SourceRecord],
    evidence_files: list[EvidenceFile],
    entities: list[Entity],
    aliases: list[EntityAlias],
    max_indicators: int,
) -> CaseExtraction:
    """Bounded, deterministic per-case extraction (sorted then truncated)."""
    counters = CaseExtraction(
        case_id=case_id,
        records_scanned=len(records),
        evidence_files_scanned=len(evidence_files),
        entity_rows=len(entities),
        alias_rows=len(aliases),
    )
    out: list[Indicator] = []
    for record in records:
        out.extend(extract_record_indicators(record, case_id=case_id, counters=counters))
    for entity in entities:
        out.extend(extract_entity_indicators(entity, case_id=case_id, counters=counters))
    entities_by_id = {str(entity.id): entity for entity in entities}
    for alias in aliases:
        matched_entity = entities_by_id.get(str(alias.entity_id))
        if matched_entity is None:
            continue
        out.extend(
            extract_alias_indicators(
                alias, entity=matched_entity, case_id=case_id, counters=counters
            )
        )
    for evidence in evidence_files:
        _emit(
            out,
            counters,
            kind="evidence_hash",
            original=str(evidence.sha256).lower(),
            case_id=case_id,
            evidence_file_id=str(evidence.id),
        )
    out.sort(key=Indicator.sort_key)
    if len(out) > max_indicators:
        counters.indicators_bounded = True
        out = out[:max_indicators]
    counters.indicators = out
    return counters


# -- candidate construction -----------------------------------------------------

BASE_SCORE: dict[str, int] = {
    "exact_identifier": 60,
    "reviewed_alias": 55,
    "normalized_identifier": 45,
    "similarity_name_only": 15,
}


def _capped(values: list[str], limit: int) -> tuple[list[str], bool]:
    unique = sorted(dict.fromkeys(values))
    if len(unique) > limit:
        return unique[:limit], True
    return unique, False


def _build_case_index(
    indicators: list[Indicator],
) -> tuple[dict[str, list[int]], dict[str, list[int]], dict[str, list[int]]]:
    """entity_id / source_record_id / evidence_file_id -> indicator positions.

    Built once per case (not per candidate group) so grouping stays O(n).
    """
    entity_index: dict[str, list[int]] = defaultdict(list)
    record_index: dict[str, list[int]] = defaultdict(list)
    file_index: dict[str, list[int]] = defaultdict(list)
    for index, indicator in enumerate(indicators):
        if indicator.entity_id:
            entity_index[indicator.entity_id].append(index)
        if indicator.source_record_id:
            record_index[indicator.source_record_id].append(index)
        if indicator.evidence_file_id:
            file_index[indicator.evidence_file_id].append(index)
    return entity_index, record_index, file_index


def _contributing_indices(
    key_indicators: list[Indicator],
    *,
    entity_index: dict[str, list[int]],
    record_index: dict[str, list[int]],
    file_index: dict[str, list[int]],
    indicators: list[Indicator],
) -> list[Indicator]:
    """Key indicators plus everything carried by the same entity/record/file."""
    picked: dict[int, Indicator] = {}
    for indicator in key_indicators:
        picked[id(indicator)] = indicator
        if indicator.entity_id:
            for index in entity_index.get(indicator.entity_id, []):
                picked[id(indicators[index])] = indicators[index]
        if indicator.source_record_id:
            for index in record_index.get(indicator.source_record_id, []):
                picked[id(indicators[index])] = indicators[index]
        if indicator.evidence_file_id:
            for index in file_index.get(indicator.evidence_file_id, []):
                picked[id(indicators[index])] = indicators[index]
    return sorted(picked.values(), key=Indicator.sort_key)


def _classify(
    *,
    kind: str,
    side_originals: dict[str, list[str]],
    side_reviewed: dict[str, bool],
    additional_shared_kinds: list[str],
    side_values_by_kind: dict[str, dict[str, list[str]]],
    cases: list[str],
) -> str:
    if kind == REVIEWED_ALIAS_KIND:
        return "reviewed_alias"
    if any(side_reviewed[case_id] for case_id in cases):
        return "reviewed_alias"
    if kind in IDENTIFIER_KINDS:
        reference = side_originals[cases[0]]
        if all(side_originals[case_id] == reference for case_id in cases[1:]):
            return "exact_identifier"
        return "normalized_identifier"
    # Name-keyed group: an actually shared identifier (same normalized value on
    # every side) upgrades the label; anything weaker stays informational.
    shared_identifier_kinds = [k for k in additional_shared_kinds if k in IDENTIFIER_KINDS]
    if shared_identifier_kinds:
        upgrade_kind = shared_identifier_kinds[0]
        reference = side_values_by_kind[upgrade_kind][cases[0]]
        if all(side_values_by_kind[upgrade_kind][case_id] == reference for case_id in cases[1:]):
            return "exact_identifier"
        return "normalized_identifier"
    return "similarity_name_only"


def build_candidate(
    *,
    kind: str,
    value_normalized: str,
    members: dict[str, list[Indicator]],
    indicators_by_case: dict[str, list[Indicator]],
    indices_by_case: dict[
        str,
        tuple[dict[str, list[int]], dict[str, list[int]], dict[str, list[int]]],
    ],
    scope_case_ids: list[str],
    scope_hash: str,
    max_supporting_ids: int,
) -> dict[str, Any]:
    """One candidate payload from a shared (kind, value) group."""
    cases = sorted(members)
    side_originals: dict[str, list[str]] = {}
    side_reviewed: dict[str, bool] = {}
    side_values_by_kind: dict[str, dict[str, list[str]]] = {k: {} for k in IDENTIFIER_KINDS}
    sides: list[dict[str, Any]] = []

    for case_id in cases:
        indicators = indicators_by_case[case_id]
        entity_index, record_index, file_index = indices_by_case[case_id]
        contributing = _contributing_indices(
            members[case_id],
            entity_index=entity_index,
            record_index=record_index,
            file_index=file_index,
            indicators=indicators,
        )

        originals, originals_capped = _capped(
            [indicator.value_original for indicator in members[case_id]], max_supporting_ids
        )
        entity_ids, entity_capped = _capped(
            [i.entity_id for i in contributing if i.entity_id], max_supporting_ids
        )
        record_ids, record_capped = _capped(
            [i.source_record_id for i in contributing if i.source_record_id], max_supporting_ids
        )
        file_ids, file_capped = _capped(
            [i.evidence_file_id for i in contributing if i.evidence_file_id], max_supporting_ids
        )
        capped_flag = any([originals_capped, entity_capped, record_capped, file_capped])

        contributing_kinds = sorted({indicator.kind for indicator in contributing})
        for identifier_kind in IDENTIFIER_KINDS:
            values = sorted(
                {
                    indicator.value_normalized
                    for indicator in contributing
                    if indicator.kind == identifier_kind
                }
            )
            if values:
                side_values_by_kind[identifier_kind][case_id] = values

        side_originals[case_id] = originals
        side_reviewed[case_id] = any(i.reviewed for i in members[case_id])
        sides.append(
            {
                "case_id": case_id,
                "value_originals": originals,
                "originals_capped": originals_capped,
                "entity_ids": entity_ids,
                "source_record_ids": record_ids,
                "evidence_file_ids": file_ids,
                "supporting_ids_capped": capped_flag,
                "reviewed_alias": side_reviewed[case_id],
                "contributing_kinds": contributing_kinds,
            }
        )

    additional_shared: list[str] = []
    conflicts: list[dict[str, Any]] = []
    for identifier_kind in IDENTIFIER_KINDS:
        if identifier_kind == kind:
            continue
        per_side = side_values_by_kind[identifier_kind]
        if not all(case_id in per_side for case_id in cases):
            continue  # absence on one side is not disagreement
        common = set(per_side[cases[0]])
        for case_id in cases[1:]:
            common &= set(per_side[case_id])
        if common:
            additional_shared.append(identifier_kind)
        else:
            conflicts.append(
                {
                    "kind": identifier_kind,
                    "per_case_values": {case_id: per_side[case_id][:3] for case_id in cases},
                }
            )

    classification = _classify(
        kind=kind,
        side_originals=side_originals,
        side_reviewed=side_reviewed,
        additional_shared_kinds=additional_shared,
        side_values_by_kind=side_values_by_kind,
        cases=cases,
    )
    supporting_records = sum(
        len(side["source_record_ids"]) + len(side["evidence_file_ids"]) for side in sides
    )
    score = BASE_SCORE[classification]
    score += min(20, 5 * len(additional_shared))
    score += min(15, 3 * max(0, supporting_records - len(cases)))
    score = max(0, min(100, score))
    reviewable = classification != "similarity_name_only"

    return {
        "crosscase_rules_version": CROSSCASE_RULES_VERSION,
        "scope": {
            "case_ids": list(scope_case_ids),
            "scope_hash": scope_hash,
            "cases_in_group": cases,
        },
        "group": {"indicator_kind": kind, "value_normalized": value_normalized},
        "classification": classification,
        "classification_semantics": CLASSIFICATION_SEMANTICS,
        "score": score,
        "score_semantics": SCORE_SEMANTICS,
        "signal_kinds": sorted({kind, *additional_shared}),
        "additional_shared_kinds": additional_shared,
        "conflicting_attributes": {"flagged": bool(conflicts), "evidence": conflicts},
        "sides": sides,
        "reviewable": reviewable,
        "review_disabled_reason": (
            None
            if reviewable
            else (
                "name similarity without a shared identifier is informational only; "
                "it can never become an authoritative link"
            )
        ),
        "limitations": list(LIMITATIONS),
        "graph_freshness_note": GRAPH_FRESHNESS_NOTE,
    }


def build_candidates(
    indicators_by_case: dict[str, list[Indicator]],
    *,
    scope_case_ids: list[str],
    scope_hash: str,
    max_candidates: int,
    max_supporting_ids: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group by (kind, normalized value); only groups spanning >=2 cases.

    Hash-map grouping: no pairwise comparison is ever performed across
    different values, and only the group key decides which pairs can arise.
    """
    groups: dict[tuple[str, str], dict[str, list[Indicator]]] = {}
    for case_id in sorted(indicators_by_case):
        for indicator in indicators_by_case[case_id]:
            key = (indicator.kind, indicator.value_normalized)
            groups.setdefault(key, {}).setdefault(case_id, []).append(indicator)

    indices_by_case = {
        case_id: _build_case_index(indicators) for case_id, indicators in indicators_by_case.items()
    }
    shared_keys = sorted(key for key, members in groups.items() if len(members) >= 2)
    bounded = len(shared_keys) > max_candidates
    stats: dict[str, Any] = {
        "groups_total": len(groups),
        "groups_shared": len(shared_keys),
        "candidates_bounded": bounded,
    }
    candidates = [
        build_candidate(
            kind=kind,
            value_normalized=value_normalized,
            members=groups[(kind, value_normalized)],
            indicators_by_case=indicators_by_case,
            indices_by_case=indices_by_case,
            scope_case_ids=scope_case_ids,
            scope_hash=scope_hash,
            max_supporting_ids=max_supporting_ids,
        )
        for kind, value_normalized in shared_keys[:max_candidates]
    ]
    return candidates, stats


# -- scope verification (submit-time, no existence disclosure) ------------------


class CrossCaseScopeDenied(Exception):
    """The requested scope contains at least one case the caller may not read.

    The HTTP layer answers with a 404 that does not say *which* id failed, so
    scope probing can never be used to test case existence.
    """


def _scope_hash(case_ids: list[str]) -> str:
    return hashlib.sha256(",".join(case_ids).encode()).hexdigest()[:12]


async def _user_is_admin(session: AsyncSession, user: User) -> bool:
    role_rows = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
    )
    return any(rbac.is_admin_role(name) for name in role_rows.scalars())


async def visible_case_ids(session: AsyncSession, user: User, case_ids: list[str]) -> set[str]:
    """Fresh per-call visibility for a bounded scope (admin/owner/member).

    ``case_ids`` are string uuids (as stored in payloads); the id columns are
    ``uuid.UUID``, so they are converted once for the ``IN`` queries. A
    malformed id is never treated as visible.
    """
    uuids: list[uuid.UUID] = []
    for value in case_ids:
        try:
            uuids.append(uuid.UUID(value))
        except ValueError:
            continue
    if not uuids:
        return set()
    if await _user_is_admin(session, user):
        existing = await session.execute(select(Case.id).where(Case.id.in_(uuids)))
        return {str(row) for row in existing.scalars()}
    case_rows = await session.execute(select(Case.id, Case.owner_id).where(Case.id.in_(uuids)))
    visible: set[str] = set()
    for case_id, owner_id in case_rows.all():
        if owner_id is not None and owner_id == user.id:
            visible.add(str(case_id))
    member_rows = await session.execute(
        select(CaseMember.case_id).where(
            CaseMember.user_id == user.id, CaseMember.case_id.in_(uuids)
        )
    )
    visible |= {str(row) for row in member_rows.scalars()}
    return visible


async def verify_scope(
    session: AsyncSession, *, user: User, case_ids: list[str]
) -> tuple[list[str], str]:
    """Deduplicated, sorted, fully visible scope + its hash or ScopeDenied."""
    ids = sorted({str(case_id) for case_id in case_ids})
    visible = await visible_case_ids(session, user, ids)
    if set(ids) != visible:
        raise CrossCaseScopeDenied(
            "one or more cases in the requested scope are not accessible to this account"
        )
    return ids, _scope_hash(ids)


# -- submission + job lifecycle -------------------------------------------------


async def submit_cross_case_job(
    session: AsyncSession,
    *,
    anchor_case_id: uuid.UUID,
    case_ids: list[str],
    actor_id: uuid.UUID,
    timeout_seconds: int,
) -> tuple[AnalysisJob, bool]:
    """Idempotent submission anchored to the requesting case.

    The authorized scope (ids + hash) is written to the job's JSONB summary at
    submission time; the runner re-reads *that* record and re-verifies every
    id against fresh rows before touching any evidence.
    """
    ids = sorted({str(case_id) for case_id in case_ids})
    scope_hash = _scope_hash(ids)
    job, created = await jobs_svc.submit_case_feature_job(
        session,
        case_id=anchor_case_id,
        feature=CROSSCASE_ANCHOR_FEATURE,
        actor_id=actor_id,
        timeout_seconds=timeout_seconds,
        active_code=CODE_CROSS_CASE_ACTIVE,
        scope_hash=scope_hash,
    )
    if created:
        job.result_summary = {"scope_case_ids": ids, "scope_hash": scope_hash}
        await session.flush()
    return job, created


async def _load_scope_rows(
    session: AsyncSession,
    case_id: uuid.UUID,
    settings: Settings,
) -> tuple[
    list[SourceRecord], list[EvidenceFile], list[Entity], list[EntityAlias], dict[str, bool]
]:
    """Bounded, case-scoped rows. ``bounded`` flags every truncation."""
    record_rows = await session.execute(
        select(SourceRecord)
        .join(EvidenceFile, SourceRecord.evidence_file_id == EvidenceFile.id)
        .where(EvidenceFile.case_id == str(case_id), SourceRecord.status != "failed")
        .order_by(EvidenceFile.created_at, EvidenceFile.id, SourceRecord.record_no)
        .limit(settings.CROSSCASE_MAX_RECORDS + 1)
    )
    records = list(record_rows.scalars())
    records_bounded = len(records) > settings.CROSSCASE_MAX_RECORDS
    records = records[: settings.CROSSCASE_MAX_RECORDS]

    file_rows = await session.execute(
        select(EvidenceFile)
        .where(EvidenceFile.case_id == str(case_id), EvidenceFile.deleted_at.is_(None))
        .order_by(EvidenceFile.created_at, EvidenceFile.id)
        .limit(settings.CROSSCASE_MAX_RECORDS + 1)
    )
    files = list(file_rows.scalars())
    files_bounded = len(files) > settings.CROSSCASE_MAX_RECORDS
    files = files[: settings.CROSSCASE_MAX_RECORDS]

    entity_rows = await session.execute(
        select(Entity)
        .where(Entity.case_id == str(case_id), Entity.status == "active")
        .order_by(Entity.created_at, Entity.id)
        .limit(settings.CROSSCASE_MAX_INDICATORS + 1)
    )
    entities = list(entity_rows.scalars())
    entities_bounded = len(entities) > settings.CROSSCASE_MAX_INDICATORS
    entities = entities[: settings.CROSSCASE_MAX_INDICATORS]

    entity_ids = [str(entity.id) for entity in entities]
    if entity_ids:
        alias_rows = await session.execute(
            select(EntityAlias)
            .where(EntityAlias.entity_id.in_(entity_ids))
            .order_by(EntityAlias.created_at, EntityAlias.id)
            .limit(settings.CROSSCASE_MAX_INDICATORS + 1)
        )
        aliases = list(alias_rows.scalars())
    else:
        aliases = []
    aliases_bounded = len(aliases) > settings.CROSSCASE_MAX_INDICATORS
    aliases = aliases[: settings.CROSSCASE_MAX_INDICATORS]

    bounded = {
        "records_bounded": records_bounded,
        "files_bounded": files_bounded,
        "entities_bounded": entities_bounded,
        "aliases_bounded": aliases_bounded,
    }
    return records, files, entities, aliases, bounded


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    actor_id: uuid.UUID,
) -> None:
    """Cooperative stop: cancel wins over timeout; never reports success."""
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "cross_case.canceled"
    else:
        job.error = f"cross-case discovery timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "cross_case.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=uuid.UUID(str(job.case_id)),
        metadata={"scope_cases": summary.get("scope_cases", 0)} if summary else {},
    )
    await session.commit()


async def _fail_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    code: str,
    error: str,
    summary: dict[str, Any] | None = None,
    denial: bool = False,
    stage: str = "authorize",
) -> None:
    """Terminal failure with typed code + audit; safe from pending or running."""
    if jobs_svc.is_terminal(job.status):
        return
    payload: dict[str, Any] = dict(summary) if summary else {}
    payload["error_code"] = code
    job.result_summary = payload
    job.error = error[:500]
    jobs_svc.transition(job, "failed")
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=uuid.UUID(str(job.actor_id)) if job.actor_id else None,
        action="cross_case.denied" if denial else "cross_case.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=uuid.UUID(str(job.case_id)),
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


async def execute_cross_case(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings | None = None,
) -> None:
    """Run one pending cross-case job to a terminal state (fail closed).

    Authorization over the *whole* stored scope is proven before any evidence
    is read and re-checked between bounded stages; a single revoked case fails
    the job with ``CROSS_CASE_SCOPE_REVOKED`` instead of narrowing the run.
    """
    settings = settings or get_settings()
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    anchor_case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    scope_payload = job.result_summary or {}
    raw_scope = _payload_str_list(scope_payload, "scope_case_ids")
    if actor_id is None or not raw_scope:
        await _fail_job(
            session,
            job,
            code="CROSS_CASE_FAILED",
            error="job record carries no actor or no cross-case scope",
            stage="authorize",
        )
        return
    try:
        scope_case_ids = [uuid.UUID(str(value)) for value in raw_scope]
    except (ValueError, TypeError):
        await _fail_job(
            session,
            job,
            code="CROSS_CASE_FAILED",
            error="job record carries a malformed cross-case scope",
            stage="authorize",
        )
        return

    if not await still_authorized_for_cross_case(
        session, user_id=actor_id, case_ids=scope_case_ids, permission=rbac.PERM_CROSSCASE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CROSS_CASE_SCOPE_REVOKED,
            error=(
                "cross-case scope is no longer authorized for this account; "
                "re-submit after checking case access"
            ),
            denial=True,
            stage="authorize",
        )
        return
    if job.cancel_requested:
        await _stop_job(session, job, stop="cancel", summary={}, actor_id=actor_id)
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "scope_cases": len(scope_case_ids),
        "scope_hash": scope_payload.get("scope_hash"),
        "cases_scanned": 0,
        "records_scanned": 0,
        "records_bounded": False,
        "evidence_files_scanned": 0,
        "files_bounded": False,
        "entity_rows": 0,
        "entities_bounded": False,
        "alias_rows": 0,
        "aliases_bounded": False,
        "indicators_extracted": 0,
        "indicators_bounded": False,
        "values_skipped_invalid": 0,
        "groups_shared": 0,
        "candidates_bounded": False,
        "candidates_expected": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
    }
    stage = "load"

    async def check_stop() -> bool:
        """Cooperative stop + fresh whole-scope authorization per stage."""
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop_job(session, job, stop=stop, summary=summary, actor_id=actor_id)
            return True
        if not await still_authorized_for_cross_case(
            session,
            user_id=actor_id,
            case_ids=scope_case_ids,
            permission=rbac.PERM_CROSSCASE_READ,
        ):
            await _fail_job(
                session,
                job,
                code=CODE_CROSS_CASE_SCOPE_REVOKED,
                error="cross-case scope revoked mid-run; discovery stopped",
                denial=True,
                summary=summary,
                stage=stage,
            )
            return True
        return False

    try:
        indicators_by_case: dict[str, list[Indicator]] = {}
        for case_id in scope_case_ids:
            stage = "extract"
            records, files, entities, aliases, bounded = await _load_scope_rows(
                session, case_id, settings
            )
            extraction = collect_case_indicators(
                case_id=str(case_id),
                records=records,
                evidence_files=files,
                entities=entities,
                aliases=aliases,
                max_indicators=settings.CROSSCASE_MAX_INDICATORS,
            )
            indicators_by_case[str(case_id)] = extraction.indicators
            summary["cases_scanned"] += 1
            summary["records_scanned"] += extraction.records_scanned
            summary["evidence_files_scanned"] += extraction.evidence_files_scanned
            summary["entity_rows"] += extraction.entity_rows
            summary["alias_rows"] += extraction.alias_rows
            summary["indicators_extracted"] += len(extraction.indicators)
            summary["values_skipped_invalid"] += extraction.values_skipped_invalid
            summary["indicators_bounded"] = bool(
                summary["indicators_bounded"] or extraction.indicators_bounded
            )
            summary["records_bounded"] = bool(
                summary["records_bounded"] or bounded["records_bounded"]
            )
            summary["files_bounded"] = bool(summary["files_bounded"] or bounded["files_bounded"])
            summary["entities_bounded"] = bool(
                summary["entities_bounded"] or bounded["entities_bounded"]
            )
            summary["aliases_bounded"] = bool(
                summary["aliases_bounded"] or bounded["aliases_bounded"]
            )
            if await check_stop():
                return

        stage = "candidates"
        scope_strings = [str(case_id) for case_id in scope_case_ids]
        candidates, stats = build_candidates(
            indicators_by_case,
            scope_case_ids=scope_strings,
            scope_hash=str(summary.get("scope_hash") or ""),
            max_candidates=settings.CROSSCASE_MAX_CANDIDATES,
            max_supporting_ids=settings.CROSSCASE_MAX_SUPPORTING_IDS,
        )
        summary["groups_shared"] = stats["groups_shared"]
        summary["candidates_bounded"] = stats["candidates_bounded"]
        summary["candidates_expected"] = len(candidates)

        stage = "record"
        for candidate in candidates:
            if await check_stop():
                return
            _artifact, created = await artifacts_svc.record_artifact(
                session,
                case_id=anchor_case_id,
                kind=CROSSCASE_ARTIFACT_KIND,
                origin="deterministic",
                payload=candidate,
                parser_version=CROSSCASE_RULES_VERSION,
                analysis_job_id=job.id,
                created_by=actor_id,
                status="pending_review",
                source_locator={
                    "cases": candidate["scope"]["cases_in_group"],
                    "indicator_kind": candidate["group"]["indicator_kind"],
                },
            )
            summary["artifacts_created" if created else "artifacts_reused"] += 1

        job.result_summary = summary
        jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="cross_case.analysis_completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=anchor_case_id,
            metadata={
                "scope_cases": summary["scope_cases"],
                "indicators_extracted": summary["indicators_extracted"],
                "candidates": summary["candidates_expected"],
            },
        )
        await session.commit()
    except Exception:
        logger.exception("cross-case job crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code="CROSS_CASE_FAILED",
            error=f"unexpected error during stage {stage}",
            summary=summary,
            stage=stage,
        )


async def run_cross_case_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    try:
        async with factory() as session:
            await execute_cross_case(session, job_id=job_id, settings=settings)
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background cross-case job failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code="CROSS_CASE_FAILED",
                    error="background cross-case task crashed",
                )


# -- read-time scope recheck (B7) ----------------------------------------------


async def visible_candidates(
    session: AsyncSession,
    *,
    user: User,
    anchor_case_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[DerivedArtifact], int]:
    """Candidates for one anchor case, omitting any with an unseen side.

    Visibility is re-derived per response from fresh rows (never from the
    submission-time scope or any cache). Every candidate stored for the anchor
    case is fetched (they are content-hash deduplicated and bounded), the
    invisible ones are dropped whole, and only then is the page sliced, so
    ``total`` counts visible candidates, not raw rows.
    """
    query = (
        select(DerivedArtifact)
        .where(
            DerivedArtifact.case_id == str(anchor_case_id),
            DerivedArtifact.kind == CROSSCASE_ARTIFACT_KIND,
        )
        .order_by(DerivedArtifact.created_at.desc())
    )
    rows = list((await session.execute(query)).scalars())
    side_cases: set[str] = set()
    for row in rows:
        for side in _payload_sides(row.payload or {}):
            case_value = side.get("case_id")
            if case_value:
                side_cases.add(str(case_value))
    visible = await visible_case_ids(session, user, sorted(side_cases)) if side_cases else set()
    # A candidate is kept only when it lists at least one side and every side
    # is visible right now; a malformed/sideless candidate is dropped, never
    # shown vacuously.
    kept = [
        row
        for row in rows
        if (
            (sides := _payload_sides(row.payload or {}))
            and all(str(side.get("case_id")) in visible for side in sides)
        )
    ]
    page = kept[offset : offset + limit]
    return page, len(kept)


def candidate_is_reviewable(artifact: DerivedArtifact) -> bool:
    """``similarity_name_only`` candidates are informational, never approvable."""
    if artifact.kind != CROSSCASE_ARTIFACT_KIND:
        return True
    payload = artifact.payload or {}
    return bool(payload.get("reviewable", True))


def candidate_side_cases(artifact: DerivedArtifact) -> set[str]:
    """Every case id a cross-case candidate references (anchor + every side)."""
    cases: set[str] = set()
    if artifact.case_id:
        cases.add(str(artifact.case_id))
    for side in _payload_sides(artifact.payload or {}):
        if side.get("case_id"):
            cases.add(str(side["case_id"]))
    return cases


async def guard_cross_case_artifact(
    session: AsyncSession, user: User, artifact: DerivedArtifact
) -> None:
    """Fail closed (404, no existence disclosure) unless the caller may see
    *every* case of a cross-case candidate. No-op for other artifact kinds."""
    if artifact.kind != CROSSCASE_ARTIFACT_KIND:
        return
    sides = _payload_sides(artifact.payload or {})
    side_cases = {str(side.get("case_id")) for side in sides if side.get("case_id")}
    side_cases.add(str(artifact.case_id))
    # Fail closed: a candidate with no derivable sides cannot be authorized, so
    # it is shown as not-found rather than leaked.
    if not sides or len(side_cases) <= 1:
        raise ApiHTTPException(
            404,
            CODE_ARTIFACT_NOT_FOUND,
            f"artifact {artifact.id} not found",
        )
    visible = await visible_case_ids(session, user, sorted(side_cases))
    if set(side_cases) != visible:
        raise ApiHTTPException(
            404,
            CODE_ARTIFACT_NOT_FOUND,
            f"artifact {artifact.id} not found",
        )


def assert_candidate_decision_allowed(artifact: DerivedArtifact, decision: str) -> None:
    """Refuse approving an informational (name-similarity-only) candidate."""
    if decision == "approved" and not candidate_is_reviewable(artifact):
        raise ApiHTTPException(
            409,
            CODE_ARTIFACT_NOT_REVIEWABLE,
            "name-similarity-only candidates are informational and cannot be approved",
        )


__all__ = [
    "CLASSIFICATIONS",
    "CROSSCASE_ANCHOR_FEATURE",
    "CROSSCASE_ARTIFACT_KIND",
    "CROSSCASE_RULES_VERSION",
    "GRAPH_FRESHNESS_NOTE",
    "IDENTIFIER_KINDS",
    "Indicator",
    "CrossCaseScopeDenied",
    "assert_candidate_decision_allowed",
    "build_candidate",
    "build_candidates",
    "candidate_side_cases",
    "candidate_is_reviewable",
    "collect_case_indicators",
    "detect_unkeyed_kind",
    "execute_cross_case",
    "extract_alias_indicators",
    "extract_entity_indicators",
    "extract_record_indicators",
    "guard_cross_case_artifact",
    "normalize_domain",
    "normalize_email",
    "normalize_name",
    "normalize_reviewed_alias",
    "normalize_url",
    "run_cross_case_job",
    "submit_cross_case_job",
    "verify_scope",
    "visible_case_ids",
    "visible_candidates",
]

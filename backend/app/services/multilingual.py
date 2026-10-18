"""Multilingual complaint intelligence (phase 5A, feature 7).

A complaint is an ordinary evidence file (``txt``/``pdf``/``csv``/``json``)
analyzed in English, Hindi or Marathi. This module adds no intake path: it
reuses the upload, parsing, job, artifact, provenance and review services.

Design (see ``docs/ai/PHASE_5_6_7_PLAN.md`` §2):

- **Language identification** is deterministic Unicode script profiling
  (``profile_scripts``); the local model's label is cross-checked against it
  and any disagreement is flagged for human review, never silently resolved.
- **Translation** runs only when requested or required (non-English text) and
  is stored separately from the preserved original; material values
  (amounts, identifiers, dates, negations) are verified deterministically.
- **Field extraction** is validated per-value against the ORIGINAL text; a
  value that does not occur (verbatim or normalized) is flagged, never
  dropped or corrected.
- Everything lands as ``extraction`` / ``translation`` derived artifacts
  (``pending_review``) through the shared services; investigators edit,
  approve or reject via the existing review route.

The model never executes anything, sees only one authorized bounded excerpt,
and its reply is fenced as untrusted-adjacent: it is validated, not trusted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CompletionResult
from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_EMPTY_EVIDENCE,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INTEGRITY_MISMATCH,
    CODE_INTEGRITY_SOURCE_MISSING,
    CODE_LANGUAGE_UNSUPPORTED,
    CODE_MULTILINGUAL_ACTIVE,
    CODE_MULTILINGUAL_FAILED,
    CODE_OCR_REQUIRED,
    CODE_UNSUPPORTED_FORMAT,
)
from app.core.config import Settings
from app.core.enums import EvidenceFormat
from app.models import AnalysisJob, DerivedArtifact, EvidenceFile, SourceRecord
from app.repositories.evidence_repository import EvidenceRepository
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import authorization as authz_svc
from app.services.parsing import OCRRequiredError, ParseError, parse
from app.services.structured_extraction import parse_json_object
from app.services.validation import (
    UploadValidationError,
    detect_encoding,
    detect_format,
    fingerprint,
)

logger = logging.getLogger(__name__)

MULTILINGUAL_RULES_VERSION = "1.0.0"

# Deterministic field keys the model must return (subset used for validation).
_FIELD_KEYS = (
    "person_names",
    "organization_names",
    "account_references",
    "phone_numbers",
    "email_addresses",
    "amounts",
    "dates",
    "referenced_identifiers",
    "event_statements",
    "negations",
)
_LANGUAGE_LABELS = {"english", "hindi", "marathi", "mixed", "unknown"}
_NON_ENGLISH = {"hindi", "marathi", "mixed"}

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT_RE = re.compile(r"[\s\.,;:!?\-_/()\[\]{}\"'`~@#$%^&*+=|\\<>]+")
# ASCII phone/account-like tokens and dates we expect to survive translation.
_MATERIAL_RE = re.compile(
    r"(\d[\d,\.]*\d|\d)"  # numbers (possibly grouped)
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"  # emails
    r"|\b[A-Za-z]{2,}\d{4,}\b"  # account-like refs (letters+digits)
)
_DATE_LIKE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b")


class MultilingualRejected(Exception):
    """Typed refusal for a multilingual run (code + human message)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MultilingualRunError(Exception):
    """Internal run failure carrying a typed code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- deterministic language / value helpers ---------------------------------


def _is_devanagari(ch: str) -> bool:
    return "\u0900" <= ch <= "\u097f"


def _is_latin(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("\u00c0" <= ch <= "\u024f")


def _is_digit(ch: str) -> bool:
    return ch.isdigit()


def profile_scripts(text: str) -> dict[str, Any]:
    """Deterministic Unicode-script profile of a complaint excerpt.

    Counts letter and digit runes by script. ``candidate`` is a script-based
    language guess that is *evidence*, not an authority: Devanagari cannot
    separate Hindi from Marathi, so both map to the ``devanagari`` candidate
    and the model's finer label is cross-checked against this profile.
    """
    counts: dict[str, Any] = {
        "devanagari_letters": 0,
        "latin_letters": 0,
        "devanagari_digits": 0,
        "ascii_digits": 0,
        "other_letters": 0,
        "total_letters": 0,
    }
    for ch in unicodedata.normalize("NFC", text):
        if _is_devanagari(ch) and not _is_digit(ch):
            counts["devanagari_letters"] += 1
            counts["total_letters"] += 1
        elif _is_latin(ch):
            counts["latin_letters"] += 1
            counts["total_letters"] += 1
        elif _is_digit(ch):
            if _is_devanagari(ch):
                counts["devanagari_digits"] += 1
            else:
                counts["ascii_digits"] += 1
        elif ch.isalpha():
            counts["other_letters"] += 1
            counts["total_letters"] += 1
    letters = counts["total_letters"] or 1
    counts["devanagari_ratio"] = round(counts["devanagari_letters"] / letters, 4)
    counts["latin_ratio"] = round(counts["latin_letters"] / letters, 4)
    counts["other_ratio"] = round(counts["other_letters"] / letters, 4)

    dev = counts["devanagari_ratio"]
    lat = counts["latin_ratio"]
    other = counts["other_ratio"]
    if counts["total_letters"] == 0:
        candidate = "unknown"
    elif other >= 0.30 and other >= dev and other >= lat:
        candidate = "unsupported"
    elif dev >= 0.30 and lat >= 0.30:
        candidate = "mixed"
    elif dev >= 0.30:
        candidate = "devanagari"
    elif lat >= 0.30:
        candidate = "latin"
    else:
        candidate = "unknown"
    counts["candidate"] = candidate
    return counts


def language_consistent(profile: dict[str, Any], model_label: str) -> bool:
    """Cross-check the model's language label against the script evidence.

    - Devanagari complaint must not be labelled ``english``.
    - Latin complaint must not be labelled ``hindi``/``marathi`` (unless the
      reviewer confirms transliteration; here we flag, not block).
    - ``unknown``/``mixed`` labels are always accepted (honest hedging).
    """
    candidate = profile.get("candidate")
    if model_label in ("unknown", "mixed"):
        return True
    if candidate == "devanagari":
        return model_label in _NON_ENGLISH
    if candidate == "latin":
        return model_label == "english"
    if candidate == "mixed":
        return True
    if candidate == "unsupported":
        return False
    return True


def normalize_for_match(text: str) -> str:
    """Normalize a value for containment checks (never for storage).

    Folds Devanagari digits to ASCII, lowercases, collapses whitespace and
    strips punctuation so "₹ 5,000/-" and "5000" compare equal for *matching*
    while the original is always what is stored.
    """
    folded = unicodedata.normalize("NFC", text).translate(_DEVANAGARI_DIGITS)
    folded = folded.lower()
    folded = _PUNCT_RE.sub("", folded)
    return folded


# Deterministic marker set for instruction-like sentences inside a complaint
# (direct/indirect prompt injection). Used only to decide whether an otherwise
# source-anchored value gets auto-verified or is withheld for human review.
_INSTRUCTION_RE = re.compile(
    r"ignore\s+(?:all\s+|previous\s+|prior\s+|the\s+)*"
    r"(?:instructions?\s*|rules?\s*|prompts?\s*)"
    r"|set\s+person_names"
    r"|you\s+(?:must|are|should)\s+(?:respond|reply|output|set|return)"
    r"|reply\s+with\s+only"
    r"|output\s+(?:only\s+)?(?:one|the)\s+json"
    r"|as\s+an\s+ai\s+language\s+model"
    r"|disregard\s+(?:all\s+|previous\s+)?"
    r"|do\s+not\s+(?:follow|obey)\s+(?:the\s+)?(?:system|previous)"
    # Devanagari injection markers (Hindi/Marathi complaints).
    r"|\u092a\u093f\u091b\u0932\u0947\s+\u0928\u093f\u0930\u094d\u0926\u0947\u0936"
    r"|\u0928\u093f\u0930\u094d\u0926\u0947\u0936\u094b\u0902\s+\u0915\u094b\s+\u0928\s+\u092e\u093e\u0928\u0947\u0902?",
    re.IGNORECASE,
)


def in_instruction_context(value: str, original: str) -> bool:
    """True only when EVERY occurrence of ``value`` sits in an instruction-like
    sentence (e.g. an embedded "IGNORE ALL RULES ... set person_names to X").

    Containment alone cannot distinguish a quoted fact from a value planted by
    an injected instruction, so values whose only appearances are inside such
    sentences are withheld from the verified fields and recorded as issues for
    human review. A value that also appears in a normal sentence stays
    verified (the legitimate occurrence dominates).
    """
    if not value:
        return False
    spans = [m.start() for m in re.finditer(re.escape(value), original, re.IGNORECASE)]
    if not spans:
        return False  # no literal occurrence to judge (already source-checked)
    # Sentence/line boundaries: newline, danda, Latin sentence punctuation.
    bounds = [-1]
    for idx, ch in enumerate(original):
        if ch in "\n.!?\u0964":
            bounds.append(idx)
    bounds.append(len(original))
    for pos in spans:
        start_ = max(b for b in bounds if b < pos)
        end_ = min(b for b in bounds if b > pos)
        sentence = original[start_ + 1 : end_]
        if not _INSTRUCTION_RE.search(sentence):
            return False  # a legitimate occurrence exists
    return True


def value_in_original(value: str, original: str) -> bool:
    """Deterministic check that an extracted value occurs in the original."""
    if not value:
        return False
    if value in original:  # verbatim fast path
        return True
    norm_value = normalize_for_match(value)
    norm_original = normalize_for_match(original)
    if not norm_value:
        return False
    if norm_value in norm_original:
        return True
    # Also try matching only the digit/signature core (handles "5,000 रुपये"
    # extracted as "5,000" against original "5,000 रुपये").
    core = re.sub(r"[^0-9]", "", unicodedata.normalize("NFC", value).translate(_DEVANAGARI_DIGITS))
    if len(core) >= 3 and core in re.sub(
        r"[^0-9]", "", unicodedata.normalize("NFC", original).translate(_DEVANAGARI_DIGITS)
    ):
        return True
    return False


def check_material_values(original: str, translated: str) -> dict[str, Any]:
    """Deterministically verify material values survive a translation.

    Every number, email, account-like token and date found in the original
    must occur in the translation (after normalization). Missing values are
    reported, not corrected. Negation survival is checked separately by the
    caller (word-level, language-specific).
    """
    original_norm = unicodedata.normalize("NFC", original).translate(_DEVANAGARI_DIGITS)
    translated_norm = unicodedata.normalize("NFC", translated).translate(_DEVANAGARI_DIGITS)
    found: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    candidates = [m.group(0) for m in _MATERIAL_RE.finditer(original_norm)]
    candidates += [m.group(0) for m in _DATE_LIKE_RE.finditer(original_norm)]
    for token in candidates:
        key = token.strip().lower()
        if not key or key in seen:
            continue
        if len(key) < 3 and not key.isdigit():
            continue  # short non-numeric fragments only; "45" is material
        seen.add(key)
        if token in translated_norm or normalize_for_match(token) in normalize_for_match(
            translated_norm
        ):
            found.append(token)
        else:
            missing.append(token)
    return {
        "material_total": len(seen),
        "material_preserved": len(found),
        "material_missing": missing,
        "preserved": not missing,
    }


# negation markers that must survive translation for the meaning to hold.
_NEG_EN = re.compile(
    r"\b(not|no|never|none|neither|den(?:y|ied|ies)|refus(?:e|ed)|without)\b", re.I
)
_NEG_HI = re.compile(
    "\u0928\u0939\u0940\u0902"  # नहीं
    "|\u0928\u0939\u0940"  # नही
    "|\u0928\u093e\u0939\u0940"  # नाही (Marathi: नाहीत does not contain नही)
    "|\u0915\u094b\u0908 \u0928\u0939\u0940\u0902"  # कोई नहीं
    "|\u0915\u0926\u093e\u0930"  # कदार
    "|\u092e\u0928\u093e \u0932\u093f\u092f\u093e"  # मना लिया
    "|\u092e\u0928\u093e \u0915\u093f\u092f\u093e",  # मना किया
    re.I,
)


def negation_present(text: str) -> bool:
    """Detect a negation marker (English or Devanagari) in text."""
    return bool(_NEG_EN.search(text) or _NEG_HI.search(text))


def ambiguity_flags(record_text: str) -> list[dict[str, Any]]:
    """Deterministic ambiguity flags with locators (never invented)."""
    flags: list[dict[str, Any]] = []
    if re.search(r"[\u0966-\u096f]", record_text):
        flags.append(
            {
                "flag": "devanagari_digits",
                "detail": "amount/date written in Devanagari digits; verify the exact figure",
            }
        )
    # Ambiguous day/month order like 01/02/2024 (both <= 12).
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", record_text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= 12 and b <= 12 and a != b:
            flags.append(
                {
                    "flag": "ambiguous_date_order",
                    "detail": f"date {m.group(0)} has ambiguous day/month order",
                }
            )
            break
    # Transliteration variants: same digits appear in both Latin and
    # Devanagari contexts is rare; flag currency mentioned without an amount.
    if re.search(
        r"\u0930\u0942|\brupee|\binr\b|\bUSD\b|\bdollar\b", record_text, re.I
    ) and not re.search(r"\d", record_text):
        flags.append(
            {"flag": "currency_without_amount", "detail": "currency word with no numeric amount"}
        )
    # Legal/idiom markers an investigator should read in context.
    if re.search(
        r"\bFIR\b|\bsection \d|\bdemand notice\b"
        "|\u091a\u093e\u0930\u0941|\u092a\u0913\u0932\u0940\u0938",
        record_text,
        re.I,
    ):
        flags.append(
            {
                "flag": "legal_terminology",
                "detail": "legal terms present; confirm exact meaning in context",
            }
        )
    return flags


# --- record locator (mirrors extraction convention) --------------------------


def _locator_and_source(record: SourceRecord) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = dict(record.raw_data)
    page = raw.get("page")
    if isinstance(page, int) and isinstance(raw.get("text"), str):
        return {"record_no": record.record_no, "field": "text", "page": page}, {"text": raw["text"]}
    if isinstance(raw.get("text"), str) and len(raw) <= 2:
        return {"record_no": record.record_no, "field": "text"}, {"text": raw["text"]}
    first_field = next(iter(raw), "text")
    return {"record_no": record.record_no, "field": first_field}, raw


def _unit_content(record: SourceRecord, fmt: EvidenceFormat | None) -> str:
    raw = dict(record.raw_data)
    page = raw.get("page")
    if isinstance(page, int) and isinstance(raw.get("text"), str):
        return str(raw["text"])
    if fmt == EvidenceFormat.TXT and isinstance(raw.get("text"), str):
        return str(raw["text"])
    # csv/json rows: join string values into one analyzable excerpt.
    strings = [str(v) for v in raw.values() if isinstance(v, str)]
    if strings:
        return "\n".join(strings)
    return json.dumps(raw, ensure_ascii=False, default=str)


# --- submission --------------------------------------------------------------


def _clear_stale(job: AnalysisJob, settings: Settings) -> bool:
    """Terminal-ize a stale pending/running job left by a restart.

    Mirrors the extraction runner: no durable queue exists, so an orphaned
    job would lock its evidence forever; clearing it is honest (it never
    reports success).
    """
    try:
        if job.status == "running":
            if not jobs_svc.is_timed_out(job):
                return False
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            jobs_svc.transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or settings.MULTILINGUAL_TIMEOUT_SECONDS
            ):
                return False
            jobs_svc.transition(job, "canceled")
        else:
            return False
        return True
    except jobs_svc.InvalidJobTransition:  # pragma: no cover - raced to terminal
        return False


async def submit_multilingual(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    settings: Settings,
    translate: bool = False,
) -> tuple[AnalysisJob, bool]:
    """Validate and enqueue one multilingual run (extraction-style, idempotent).

    Typed refusals for unavailable/unsupported targets; a second submission
    while a run is active is refused (typed 409), and attempt-numbered
    idempotency keys make a retry after failure safe.
    """
    result = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == str(evidence_id),
            EvidenceFile.case_id == str(case_id),
        )
    )
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise MultilingualRejected(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    if evidence.deleted_at is not None:
        raise MultilingualRejected(
            CODE_EVIDENCE_UNAVAILABLE, "evidence is deleted; restore it before analysis"
        )
    if evidence.format is None:
        try:
            detect_format(evidence.original_filename, b"")
        except UploadValidationError as exc:
            raise MultilingualRejected(
                CODE_UNSUPPORTED_FORMAT,
                "evidence format is not supported (supported: csv, json, txt, pdf)",
            ) from exc
    elif evidence.format not in ("csv", "json", "txt", "pdf"):
        raise MultilingualRejected(
            CODE_UNSUPPORTED_FORMAT, f"evidence format {evidence.format!r} is not supported"
        )

    active_result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == "multilingual",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    active = active_result.scalar_one_or_none()
    if active is not None and not _clear_stale(active, settings):
        raise MultilingualRejected(
            CODE_MULTILINGUAL_ACTIVE, "a multilingual run is already active for this evidence"
        )
    if active is not None:
        await session.flush()

    attempt_result = await session.execute(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == "multilingual",
        )
    )
    attempt = int(attempt_result.scalar_one()) + 1
    idempotency_key = f"multilingual:{evidence_id}:a{attempt}"
    try:
        job, created = await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature="multilingual",
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            evidence_file_id=evidence_id,
            timeout_seconds=settings.MULTILINGUAL_TIMEOUT_SECONDS,
        )
    except IntegrityError:
        await session.rollback()
        dup = await session.execute(
            select(AnalysisJob).where(
                AnalysisJob.case_id == str(case_id),
                AnalysisJob.idempotency_key == idempotency_key,
            )
        )
        row = dup.scalar_one_or_none()
        if row is None:
            raise
        return row, False
    summary = dict(job.result_summary or {})
    summary["translate_requested"] = bool(translate)
    job.result_summary = summary
    await session.flush()
    return job, created


# --- execution ---------------------------------------------------------------


def _parse_analysis(completion_text: str) -> dict[str, Any] | None:
    """Recover and lightly validate the model's analysis JSON."""
    data = parse_json_object(completion_text)
    if data is None:
        return None
    if (
        not isinstance(data.get("language"), str)
        or data["language"].lower() not in _LANGUAGE_LABELS
    ):
        return None
    for key in _FIELD_KEYS:
        if key in data and not isinstance(data[key], list):
            return None
    return data


async def _reusable(
    session: AsyncSession, case_id: uuid.UUID, record_id: uuid.UUID, kind: str
) -> bool:
    """True when a reviewable (or reviewed) artifact already exists."""
    rows = (
        (
            await session.execute(
                select(DerivedArtifact.id).where(
                    DerivedArtifact.case_id == str(case_id),
                    DerivedArtifact.source_record_id == record_id,
                    DerivedArtifact.kind == kind,
                    DerivedArtifact.status.in_(("pending_review", "approved", "recorded")),
                )
            )
        )
        .scalars()
        .all()
    )
    return bool(rows)


async def execute_multilingual(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    storage: Any,
    extractor: Any,
) -> None:
    """Run one multilingual analysis. Own session, cooperative cancel, honest
    partial/failed states. The model is validated at every step."""
    from app.core import rbac

    job = await session.get(AnalysisJob, job_id)
    if job is None:
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    evidence_id = uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None
    summary: dict[str, Any] = {
        "units_total": 0,
        "units_skipped_empty": 0,
        "units_failed": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
        "artifacts_flagged": 0,
        "artifacts_invalid": 0,
        "translations_created": 0,
        "language_ambiguous": 0,
        "values_total": 0,
        "values_verified": 0,
        "values_withheld_injected": 0,
    }
    stage = "load"

    async def _fail(code: str, error: str, *, denial: bool = False) -> None:
        if summary:
            job.result_summary = summary
        job.error = f"{code}: {error}"[:500]
        if job.status != "running":
            jobs_svc.transition(job, "running")
        jobs_svc.transition(job, "failed")
        await session.flush()
        if actor_id is not None:
            await audit_svc.record_audit(
                session,
                actor_id=actor_id,
                action="multilingual.failed",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"code": code, "denial": denial},
            )
        await session.commit()

    if actor_id is not None and not await authz_svc.still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
    ):
        await _fail(
            CODE_CASE_ACCESS_DENIED, "case access was revoked before the run started", denial=True
        )
        return
    if job.cancel_requested:
        jobs_svc.transition(job, "canceled")
        await session.flush()
        if actor_id is not None:
            await audit_svc.record_audit(
                session,
                actor_id=actor_id,
                action="multilingual.canceled",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"stage": "before_run"},
            )
        await session.commit()
        return

    evidence = None
    if evidence_id is not None:
        repo = EvidenceRepository(session)
        evidence = await repo.get_evidence(evidence_id)
    if evidence is None or evidence.deleted_at is not None:
        await _fail(CODE_EVIDENCE_UNAVAILABLE, "evidence is no longer available")
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    try:
        stage = "fetch"
        if not await _to_thread(storage.exists, evidence.stored_key):
            raise MultilingualRunError(CODE_INTEGRITY_SOURCE_MISSING, "stored object unavailable")
        raw = await _to_thread(storage.download, evidence.stored_key)
        if fingerprint(raw) != evidence.sha256:
            raise MultilingualRunError(
                CODE_INTEGRITY_MISMATCH, "bytes do not match recorded sha256"
            )

        stage = "parse"
        records = await _load_records(session, evidence=evidence, raw=raw)
        fmt = EvidenceFormat(evidence.format) if evidence.format else None
        units: list[tuple[SourceRecord, str]] = []
        for record in records[: settings.MULTILINGUAL_MAX_UNITS]:
            content = _unit_content(record, fmt)
            if not content.strip():
                summary["units_skipped_empty"] += 1
                continue
            units.append((record, content))
        summary["units_total"] = len(units)
        jobs_svc.advance(job, processed=0, total=len(units))
        await session.flush()
        await session.commit()
        if not units:
            if fmt == EvidenceFormat.PDF:
                raise MultilingualRunError(CODE_OCR_REQUIRED, "PDF has no extractable text layer")
            raise MultilingualRunError(CODE_EMPTY_EVIDENCE, "no extractable complaint text")

        translate_requested = bool((job.result_summary or {}).get("translate_requested"))

        stage = "analyze"
        for index, (record, content) in enumerate(units, start=1):
            await session.refresh(job)
            stop = jobs_svc.should_stop(job)
            if stop is not None:
                await _stop(
                    session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
                )
                return
            if actor_id is not None and not await authz_svc.still_authorized_for_case(
                session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
            ):
                await _fail(CODE_CASE_ACCESS_DENIED, "access revoked mid-run", denial=True)
                return

            profile = profile_scripts(content)
            if profile["candidate"] == "unsupported":
                raise MultilingualRunError(
                    CODE_LANGUAGE_UNSUPPORTED,
                    "complaint uses an unsupported script (only English, Hindi and "
                    "Marathi are supported)",
                )

            if await _reusable(session, case_id, record.id, "extraction"):
                summary["artifacts_reused"] += 1
                jobs_svc.advance(job, processed=index)
                await session.commit()
                continue

            try:
                completion = await extractor.analyze_complaint(
                    label=f"complaint record {record.record_no} of {evidence.original_filename}",
                    text=content,
                )
            except Exception as exc:  # AI-layer failure -> honest partial
                summary["units_failed"] += 1
                logger.warning("multilingual model call failed: %s", str(exc)[:200])
                break

            data = _parse_analysis(completion.text)
            await _record_analysis(
                session,
                job=job,
                record=record,
                content=content,
                profile=profile,
                data=data,
                case_id=case_id,
                actor_id=actor_id,
                evidence=evidence,
                summary=summary,
                settings=settings,
            )

            # Translation: requested, or required because text is non-English.
            model_label = (data or {}).get("language", "unknown")
            # Translate when requested, when the text is non-English, or when
            # the model's label disagrees with the script evidence (the
            # reviewer needs an English rendering to judge the flag).
            needs_translation = (
                translate_requested
                or model_label in _NON_ENGLISH
                or not language_consistent(profile, model_label)
            )
            if needs_translation:
                try:
                    t_label = f"complaint record {record.record_no} of {evidence.original_filename}"
                    t_completion = await extractor.translate_complaint(label=t_label, text=content)
                except Exception as exc:
                    logger.warning("multilingual translation failed: %s", str(exc)[:200])
                else:
                    await _record_translation(
                        session,
                        job=job,
                        record=record,
                        original=content,
                        source_language=model_label,
                        completion=t_completion,
                        case_id=case_id,
                        actor_id=actor_id,
                        evidence=evidence,
                        summary=summary,
                        settings=settings,
                    )

            jobs_svc.advance(job, processed=index)
            await session.commit()

        if (
            summary["units_failed"]
            and summary["artifacts_created"] == 0
            and summary["artifacts_reused"] == 0
        ):
            await _fail(CODE_MULTILINGUAL_FAILED, "all complaint units failed to analyze")
            return

        stage = "complete"
        job.result_summary = summary
        if summary["units_failed"]:
            job.error = f"{summary['units_failed']} unit(s) failed (model)"
            jobs_svc.transition(job, "partial")
        else:
            jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="multilingual.completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata=_counts(summary),
        )
        await session.commit()
    except MultilingualRunError as exc:
        await session.rollback()
        await session.refresh(job)
        await _fail(exc.code, exc.message)
    except Exception:
        logger.exception("multilingual run crashed", extra={"job_id": str(job_id)})
        await session.rollback()
        await session.refresh(job)
        await _fail(CODE_MULTILINGUAL_FAILED, f"unexpected error during stage {stage}")


async def _record_analysis(
    session: AsyncSession,
    *,
    job: AnalysisJob,
    record: SourceRecord,
    content: str,
    profile: dict[str, Any],
    data: dict[str, Any] | None,
    case_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    evidence: EvidenceFile,
    summary: dict[str, Any],
    settings: Settings,
) -> None:
    """Validate one analysis reply and persist it as an extraction artifact."""
    locator, _source = _locator_and_source(record)
    if data is not None:
        language = data["language"].lower()
        consistent = language_consistent(profile, language)
        if not consistent:
            summary["language_ambiguous"] += 1
        fields: dict[str, list[str]] = {}
        issues: list[dict[str, Any]] = []
        for key in _FIELD_KEYS:
            values = [str(v) for v in (data.get(key) or []) if str(v).strip()]
            verified_values: list[str] = []
            for value in values:
                summary["values_total"] += 1
                if not value_in_original(value, content):
                    issues.append(
                        {"field": key, "value": value[:120], "code": "value_not_in_source"}
                    )
                elif in_instruction_context(value, content):
                    # Source-anchored, but only inside an injected instruction:
                    # withheld for human review, never auto-verified.
                    summary["values_withheld_injected"] += 1
                    issues.append(
                        {
                            "field": key,
                            "value": value[:120],
                            "code": "value_in_injected_context",
                        }
                    )
                else:
                    summary["values_verified"] += 1
                    verified_values.append(value)
            fields[key] = verified_values
        payload = {
            "multilingual": True,
            "language": language,
            "script_profile": profile,
            "language_consistent": consistent,
            "fields": fields,
            "ambiguity_flags": ambiguity_flags(content),
            "record_no": record.record_no,
            "rules_version": MULTILINGUAL_RULES_VERSION,
        }
        status = "pending_review"
        validation = "flagged" if (issues or not consistent) else "valid"
        if issues:
            summary["artifacts_flagged"] += 1
    else:
        payload = {
            "multilingual": True,
            "extraction_failed": True,
            "record_no": record.record_no,
            "raw_response": content[:200],
        }
        status = "failed"
        validation = "invalid"
        issues = [{"code": "unparseable_model_output"}]
        summary["artifacts_invalid"] += 1

    _, created = await artifacts_svc.record_artifact(
        session,
        case_id=case_id,
        kind="extraction",
        origin="llm",
        payload=payload,
        evidence_file_id=uuid.UUID(str(record.evidence_file_id)),
        source_record_id=record.id,
        source_locator=locator,
        validation_status=validation,
        validation_errors=issues or None,
        prompt_version=MULTILINGUAL_RULES_VERSION,
        model_profile="multilingual",
        analysis_job_id=job.id,
        created_by=actor_id,
        status=status,
    )
    if created:
        summary["artifacts_created"] += 1


async def _record_translation(
    session: AsyncSession,
    *,
    job: AnalysisJob,
    record: SourceRecord,
    original: str,
    source_language: str,
    completion: CompletionResult,
    case_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    evidence: EvidenceFile,
    summary: dict[str, Any],
    settings: Settings,
) -> None:
    """Validate a translation reply (material values) and persist it."""
    locator, _source = _locator_and_source(record)
    data = parse_json_object(completion.text)
    if data is None or not isinstance(data.get("translated_text"), str):
        summary["units_failed"] += 1
        return
    translated = data["translated_text"]
    material = check_material_values(original, translated)
    neg_ok = (not negation_present(original)) or negation_present(translated)
    issues: list[dict[str, Any]] = [
        {"code": "material_value_missing", "value": value[:120]}
        for value in material["material_missing"]
    ]
    if not neg_ok:
        issues.append({"code": "negation_not_preserved"})
    payload = {
        "source_language": source_language,
        "translated_text": translated,
        "material_check": material,
        "negation_preserved": neg_ok,
        "record_no": record.record_no,
        "rules_version": MULTILINGUAL_RULES_VERSION,
    }
    validation = "flagged" if issues else "valid"
    if validation == "flagged":
        summary["artifacts_flagged"] += 1
    _, created = await artifacts_svc.record_artifact(
        session,
        case_id=case_id,
        kind="translation",
        origin="llm",
        payload=payload,
        evidence_file_id=uuid.UUID(str(record.evidence_file_id)),
        source_record_id=record.id,
        source_locator=locator,
        validation_status=validation,
        validation_errors=issues or None,
        prompt_version=MULTILINGUAL_RULES_VERSION,
        model_profile="multilingual",
        analysis_job_id=job.id,
        created_by=actor_id,
        status="pending_review",
    )
    if created:
        summary["translations_created"] += 1


async def _stop(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> None:
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "multilingual.canceled"
    else:
        job.error = f"multilingual timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "multilingual.timed_out"
    await session.flush()
    if actor_id is not None:
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action=action,
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata=_counts(summary),
        )
    await session.commit()


def _counts(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        k: summary[k]
        for k in (
            "units_total",
            "artifacts_created",
            "artifacts_reused",
            "artifacts_flagged",
            "artifacts_invalid",
            "translations_created",
            "language_ambiguous",
            "values_total",
            "values_verified",
            "values_withheld_injected",
        )
        if k in summary
    }


async def _load_records(
    session: AsyncSession, *, evidence: EvidenceFile, raw: bytes
) -> list[SourceRecord]:
    """Existing or idempotently-created source records (shared unique key)."""
    repo = EvidenceRepository(session)
    existing = await repo.get_source_records(evidence.id)
    if existing:
        return existing
    if evidence.format:
        fmt = EvidenceFormat(evidence.format)
    else:
        fmt = detect_format(evidence.original_filename, raw)
    encoding = evidence.encoding or detect_encoding(raw)
    try:
        parsed = parse(raw, fmt, encoding)
    except OCRRequiredError as exc:
        raise MultilingualRunError(CODE_OCR_REQUIRED, str(exc)) from exc
    except ParseError as exc:
        # A TXT parse failure means the file held no analyzable paragraph
        # content (or undecodable bytes); report emptiness honestly instead of
        # pretending the run succeeded with nothing.
        code = CODE_EMPTY_EVIDENCE if fmt == EvidenceFormat.TXT else CODE_UNSUPPORTED_FORMAT
        raise MultilingualRunError(code, f"could not parse: {exc}") from exc
    created: list[SourceRecord] = []
    for record_no, raw_data in enumerate(parsed, start=1):
        row = await repo.create_source_record(
            evidence_file_id=evidence.id, record_no=record_no, raw_data=raw_data
        )
        if row is None:
            row = await repo.get_source_record(evidence.id, record_no)
        if row is not None:
            created.append(row)
    updates: dict[str, Any] = {}
    if not evidence.record_count:
        updates["record_count"] = len(parsed)
    if not evidence.format:
        updates["format"] = fmt.value
    if not evidence.encoding:
        updates["encoding"] = encoding
    if updates:
        await repo.update_evidence(
            evidence.id, status=evidence.status, status_detail=evidence.status_detail, **updates
        )
    return created


async def _to_thread(fn: Any, *args: Any) -> Any:
    return await asyncio.to_thread(fn, *args)


async def run_multilingual_job(app: Any, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory = database.session_factory()
    try:
        async with factory() as session:
            await execute_multilingual(
                session,
                job_id=job_id,
                settings=settings,
                storage=app.state.storage,
                extractor=app.state.ai_service,
            )
    except Exception:
        logger.exception("background multilingual failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                job.error = "background multilingual task crashed"
                jobs_svc.transition(job, "failed")
                await session.commit()

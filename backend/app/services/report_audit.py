"""AI report auditor (phase 6, feature 10): audit a report *draft*.

The auditor reviews a draft for unsupported claims, invalid citations,
numeric/timeline discrepancies and candidate counter-evidence. It never
modifies the draft: an ``AIMessage`` row or the investigator-supplied text is
read once, pinned by ``draft_hash`` and left untouched.

Pipeline (job feature ``report_audit``):

1. **Snapshot** - authorization re-checked; the draft text is retrieved once
   and hashed; a later read compares the hash and marks the audit stale when
   a referenced message changed.
2. **Claim extraction (model -> deterministic validation)** - claims with
   verbatim ``char_start``/``char_end`` spans, a closed-set category and
   cited source ids. Spans that do not reproduce the draft, unknown
   categories and malformed ids become explicit findings; nothing is
   silently dropped.
3. **Deterministic checks** - citations are validated server-side
   (``citations.validate_citation``: shape, existence, case scope, locator,
   quoted-value equality); amounts/currency are parsed with documented
   ASCII + Devanagari digit rules; totals are re-added; dates are parsed and
   timeline-category claims are ordered against the draft itself and against
   case ``TimelineEvent`` dates. Cross-case or malformed citations are
   *findings*, never retrievals.
4. **Semantic support (model -> deterministic quote validation)** - for each
   claim with valid citations and available excerpts the model answers
   ``supported|partially_supported|contradicted|not_established`` and must
   quote the sources verbatim; any quoted span that does not occur in the
   supplied excerpts invalidates the assessment (flagged, never trusted).
5. **Counter-evidence (deterministic)** - case-scoped substring retrieval
   over bounded source records; matches are *candidate* counter-evidence.
   The payload always records ``records_searched`` and distinguishes "no
   records found" from a verified absence.
6. **Findings** - one ``report_claim_review`` artifact per run
   (``origin="llm"``, ``pending_review``, always ``flagged``: model claims
   and assessments are machine-validated but not human-reviewed).

Invariants: deterministic code owns spans, ids, numbers, dates, severities
and access control; the model only extracts claims and assesses support.
Excerpts are authorized server-side per citation - the model gets no
database, shell, filesystem or network access, and draft/evidence text is
fenced as untrusted data by the AI layer.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    REPORT_AUDIT_CLAIM_PROMPT_VERSION,
    REPORT_AUDIT_SUPPORT_PROMPT_VERSION,
)
from app.core import rbac
from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_DRAFT_SOURCE_INVALID,
    CODE_DRAFT_TOO_LARGE,
    CODE_DRAFT_UNAVAILABLE,
    CODE_MESSAGE_NOT_REPORT_MODE,
    CODE_REPORT_AUDIT_ACTIVE,
    CODE_REPORT_AUDIT_FAILED,
)
from app.core.config import Settings
from app.models import (
    AIConversation,
    AIMessage,
    AnalysisJob,
    DerivedArtifact,
    Entity,
    EvidenceFile,
    Finding,
    Hypothesis,
    Relationship,
    SourceRecord,
    TimelineEvent,
    User,
)
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import authorization as authz_svc
from app.services.citations import CitationRef, validate_citation
from app.services.structured_extraction import parse_json_object

logger = logging.getLogger(__name__)

# Deterministic check rules + payload vocabulary version (bumped together).
REPORT_AUDIT_RULES_VERSION = "1.0.0"

CLAIM_CATEGORIES = frozenset(
    {
        "factual_statement",
        "attribution",
        "quantity",
        "timeline",
        "identity",
        "causal",
        "opinion_hedge",
    }
)
ASSESSMENTS = frozenset({"supported", "partially_supported", "contradicted", "not_established"})

# Documented closed finding set and its deterministic severities
# (plan section 4: high = invalid citation / contradicted / numeric mismatch /
# timeline discrepancy; medium = partially supported / not established;
# info = candidate counter-evidence).
FINDING_SEVERITY: dict[str, str] = {
    "claim_extraction_invalid": "high",
    "invalid_citation": "high",
    "numeric_mismatch": "high",
    "currency_mismatch": "high",
    "timeline_discrepancy": "high",
    "contradicted": "high",
    "partially_supported": "medium",
    "not_established": "medium",
    "assessment_unverified": "medium",
    "counter_evidence_candidate": "info",
}
_SEVERITY_RANK = {"none": 0, "info": 1, "medium": 2, "high": 3}

# Bounds (module constants keep the config surface small; the per-run budgets
# that matter for safety live in Settings).
_MAX_CITATION_CHECKS = 120  # validate_citation calls per run
_MAX_CITED_PER_CLAIM = 12  # ids checked per claim (rest stays unchecked+flagged)
_MAX_COUNTER_RECORDS = 300  # case source records scanned for counter-evidence
_MAX_COUNTER_TOKENS = 6  # search tokens per claim
_MAX_COUNTER_MATCHES_PER_CLAIM = 3
_MAX_EXCERPT_RECORDS = 8  # records per cited evidence
_MAX_EXCERPT_RECORD_CHARS = 600
_EXCERPT_TOTAL_CHARS = 3600
_MAX_TIMELINE_EVENTS = 200

# Bare-uuid citations are resolved to their kind in this documented order;
# ids with an explicit ``kind:`` prefix skip resolution entirely.
_KIND_ORDER: tuple[tuple[str, Any], ...] = (
    ("evidence_file", EvidenceFile),
    ("source_record", SourceRecord),
    ("entity", Entity),
    ("relationship", Relationship),
    ("finding", Finding),
    ("timeline_event", TimelineEvent),
    ("hypothesis", Hypothesis),
    ("derived_artifact", DerivedArtifact),
)
_CITED_PREFIXES = {
    "evidence": "evidence_file",
    "record": "source_record",
    "source_record": "source_record",
    "entity": "entity",
    "relationship": "relationship",
    "finding": "finding",
    "timeline": "timeline_event",
    "timeline_event": "timeline_event",
    "hypothesis": "hypothesis",
    "artifact": "derived_artifact",
    "derived_artifact": "derived_artifact",
    # explicit names also pass through
    "evidence_file": "evidence_file",
}


class ReportAuditRejected(Exception):
    """Typed submission refusal (code + message, no traceback to clients)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ReportAuditRunError(Exception):
    """Typed in-run failure (the job fails with this code, nothing is faked)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- deterministic text helpers (pure; golden-fixture replayed) -------------


def draft_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<iso>\d{4}-\d{1,2}-\d{1,2})(?!\d)"
    r"|(?<![\d/-])(?P<dmy>\d{1,2}[/-]\d{1,2}[/-]\d{4})(?![\d/-])"
    r"|(?P<mon_first>\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
    r"\s+\d{1,2},?\s+\d{4}\b)"
    r"|(?P<day_first>\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+\d{4}\b)",
    re.IGNORECASE,
)

_AMOUNT_PATTERN = re.compile(
    r"(?<![\d.,])"
    r"(?:\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+|\d+(?:\.\d+)?)"
    r"(?![\d])"
)

_CURRENCY_PATTERN = re.compile(r"₹|रु|\bINR\b|\bRs\.?\b|\$|\bUSD\b|€|\bEUR\b|£|\bGBP\b")

_TOTAL_PATTERN = re.compile(r"\b(total|sum|altogether|in total)\b", re.IGNORECASE)

_LONG_RUN_PATTERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")


def normalize_digits(text: str) -> str:
    """Devanagari digits -> ASCII so every parser has one digit rule."""
    return text.translate(_DEVANAGARI_DIGITS)


def _month_index(token: str) -> int | None:
    return _MONTHS.get(token[:3].lower())


def _date_from_match(match: re.Match[str]) -> date | None:
    try:
        if match.group("iso"):
            year, month, day = (int(part) for part in match.group("iso").split("-"))
            return date(year, month, day)
        if match.group("dmy"):
            parts = re.split(r"[/-]", match.group("dmy"))
            day, month, year = (int(part) for part in parts)
            return date(year, month, day)  # documented: day-first for slash dates
        if match.group("mon_first"):
            cleaned = match.group("mon_first").replace(",", "")
            pieces = cleaned.split()
            month_val = _month_index(pieces[0])
            if month_val is None:
                return None
            return date(int(pieces[2]), month_val, int(pieces[1]))
        if match.group("day_first"):
            pieces = match.group("day_first").split()
            month_val = _month_index(pieces[1])
            if month_val is None:
                return None
            return date(int(pieces[2]), month_val, int(pieces[0]))
    except ValueError:
        return None
    return None


def parse_dates(text: str) -> tuple[list[str], int]:
    """All dates in text order as ISO strings + count of date-like failures.

    Accepts ISO (YYYY-MM-DD), day-first DD/MM/YYYY and DD-MM-YYYY, and
    English month-name forms, each with Devanagari digits. Invalid
    date-shaped text (e.g. 31/02/2026) is counted, never guessed.
    """
    norm = normalize_digits(text)
    parsed: list[str] = []
    unparsed = 0
    for match in _DATE_PATTERN.finditer(norm):
        value = _date_from_match(match)
        if value is None:
            unparsed += 1
        else:
            parsed.append(value.isoformat())
    return parsed, unparsed


def _mask_dates(text: str) -> str:
    """Blank date-shaped spans (same length) so amount parsing cannot read
    ``2026`` out of ``2026-01-14``."""
    return _DATE_PATTERN.sub(lambda m: " " * len(m.group(0)), text)


def _currency_code(token: str) -> str | None:
    if token == "₹":
        return "INR"
    if token == "$":
        return "USD"
    if token == "€":
        return "EUR"
    if token == "£":
        return "GBP"
    if token == "रु":
        return "INR"
    upper = token.upper().rstrip(".")
    if upper.startswith("RS"):
        return "INR"
    if upper in {"INR", "USD", "EUR", "GBP"}:
        return upper
    return None


def _decimal_value(token: str) -> Decimal | None:
    try:
        if re.fullmatch(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?", token):
            # comma grouping: international (1,234.56) and Indian (1,23,456.50)
            return Decimal(token.replace(",", ""))
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
            # dot-grouped thousands (international) with no decimal part
            return Decimal(token.replace(".", ""))
        return Decimal(token)
    except (ValueError, ArithmeticError):  # pragma: no cover - defensive
        return None


def parse_amounts(text: str) -> list[dict[str, Any]]:
    """Money/number mentions with the nearest currency token.

    Documents the numeric conventions: ASCII + Devanagari digits, comma
    grouping (``1,234.56``), dot-grouped thousands (``1.234`` - no decimal
    part), plain decimals; currency inferred within +/-8 characters
    (``INR``/``Rs``/``₹`` -> INR, ``$``/``USD`` -> USD, ...). Date-shaped
    spans are masked first. Unparseable numeric expressions are ignored.
    """
    norm = normalize_digits(text)
    masked = _mask_dates(norm)
    amounts: list[dict[str, Any]] = []
    for match in _AMOUNT_PATTERN.finditer(masked):
        token = match.group(0)
        value = _decimal_value(token)
        if value is None:
            continue
        before = masked[max(0, match.start() - 8) : match.start()]
        after = masked[match.end() : match.end() + 8]
        currency: str | None = None
        before_hits = list(_CURRENCY_PATTERN.finditer(before))
        if before_hits:
            currency = _currency_code(before_hits[-1].group(0))
        else:
            after_hits = list(_CURRENCY_PATTERN.finditer(after))
            if after_hits:
                currency = _currency_code(after_hits[0].group(0))
        amounts.append({"raw": token, "currency": currency, "value": str(value)})
    return amounts


def check_arithmetic(claim_text: str, amounts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Re-add the components of a stated total inside one claim.

    Only applies when the claim states a total/sum AND carries at least three
    parsed numbers (components + stated). ``None`` means "not applicable" -
    never a pass.
    """
    if not _TOTAL_PATTERN.search(normalize_digits(claim_text)):
        return None
    values: list[Decimal] = []
    for item in amounts:
        try:
            values.append(Decimal(str(item["value"])))
        except Exception:  # noqa: BLE001 - values come from parse_amounts
            return None
    if len(values) < 3:
        return None
    stated = values[-1]
    components = values[:-1]
    computed = sum(components, Decimal(0))
    return {
        "ok": computed == stated,
        "stated": str(stated),
        "computed": str(computed),
        "components": [str(item) for item in components],
    }


def chronology_issues(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decreasing dates across timeline claims in *draft* order.

    ``claims`` entries: ``{"claim_index", "char_start", "dates": [iso]}``.
    A claim is flagged at most once; the running maximum is the reference so
    one out-of-order date does not cascade.
    """
    flat: list[tuple[int, str]] = []
    for item in sorted(claims, key=lambda c: int(c["char_start"])):
        for day in item["dates"]:
            flat.append((int(item["claim_index"]), str(day)))
    issues: list[dict[str, Any]] = []
    flagged: set[int] = set()
    running_max: str | None = None
    for claim_index, day in flat:
        if running_max is not None and day < running_max and claim_index not in flagged:
            issues.append({"claim_index": claim_index, "previous_date": running_max, "date": day})
            flagged.add(claim_index)
        if running_max is None or day > running_max:
            running_max = day
    return issues


def currency_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same digit string written with different currencies across claims.

    ``claims`` entries: ``{"claim_index", "char_start", "amounts": [...]}``
    (see :func:`parse_amounts`). The *later* draft claim carries the finding;
    each claim is flagged at most once per run.
    """
    first_seen: dict[str, tuple[int, str, str]] = {}
    conflicts: list[dict[str, Any]] = []
    flagged: set[int] = set()
    for item in sorted(claims, key=lambda c: int(c["char_start"])):
        claim_index = int(item["claim_index"])
        for amount in item["amounts"]:
            currency = amount.get("currency")
            if not currency:
                continue
            key = "".join(ch for ch in str(amount["value"]) if ch.isdigit())
            if not key:
                continue
            previous = first_seen.get(key)
            if previous is None:
                first_seen[key] = (claim_index, str(currency), str(amount["raw"]))
            elif previous[1] != currency and claim_index not in flagged:
                conflicts.append(
                    {
                        "claim_index": claim_index,
                        "against_claim_index": previous[0],
                        "digit_key": key,
                        "currency": str(currency),
                        "other_currency": previous[1],
                        "raw": str(amount["raw"]),
                        "other_raw": previous[2],
                    }
                )
                flagged.add(claim_index)
    return conflicts


def claim_tokens(claim_text: str, amounts: list[dict[str, Any]]) -> list[str]:
    """Bounded counter-evidence tokens for one claim: parsed amounts (raw,
    normalized, Indian comma form) and long digit runs (account/txn ids)."""
    tokens: list[str] = []

    def add(value: str) -> None:
        cleaned = value.strip()
        if len(cleaned) >= 3 and cleaned not in tokens:
            tokens.append(cleaned)

    for item in amounts[:4]:
        add(str(item["raw"]))
        value = str(item["value"])
        add(value)
        # comma form matches records written as "5,000" (Indian/intl);
        # skip it for huge digit runs - records carry the raw digits there
        if "." not in value and value.isdigit() and int(value) < 10**9:
            add(f"{int(value):,}")
    for match in _LONG_RUN_PATTERN.finditer(normalize_digits(claim_text)):
        add(match.group(0))
    return tokens[:_MAX_COUNTER_TOKENS]


def parse_claims_reply(text: str) -> list[dict[str, Any]] | None:
    """Shape-validate the claim-extraction reply; ``None`` = unusable."""
    data = parse_json_object(text)
    if not isinstance(data, dict):
        return None
    raw = data.get("claims")
    if not isinstance(raw, list):
        return None
    if not all(isinstance(item, dict) for item in raw):
        return None
    return [dict(item) for item in raw]


def normalize_claims(
    raw_claims: list[dict[str, Any]], *, draft: str, max_claims: int
) -> tuple[list[dict[str, Any]], int]:
    """Structural validation of every claim (nothing is dropped).

    Returns ``(claims, truncated)``. Each claim records ``span_valid``
    (verbatim reproduction), ``category_valid`` and ``extraction_valid``
    (all structural fields well-formed); failures become
    ``claim_extraction_invalid`` findings later.
    """
    truncated = max(0, len(raw_claims) - max_claims)
    claims: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_claims[:max_claims]):
        problems: list[str] = []
        raw_id = item.get("claim_id")
        claim_id: str | None = None
        if isinstance(raw_id, str) and raw_id and raw_id not in seen_ids:
            claim_id = raw_id
            seen_ids.add(raw_id)
        else:
            problems.append("claim_id")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append("text")
            text = ""
        start = item.get("char_start")
        end = item.get("char_end")
        span_valid = False
        if (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end <= len(draft)
        ):
            span_valid = draft[start:end] == text
        else:
            problems.append("char_span")
        if not span_valid and "char_span" not in problems:
            problems.append("char_span")
        category = item.get("category")
        category_valid = isinstance(category, str) and category in CLAIM_CATEGORIES
        if not category_valid:
            problems.append("category")
        cited = item.get("cited_ids")
        if isinstance(cited, list) and all(isinstance(entry, str) for entry in cited):
            cited_ids = [str(entry) for entry in cited]
        else:
            problems.append("cited_ids")
            cited_ids = []
        claims.append(
            {
                "claim_index": index,
                "claim_id": claim_id,
                "category": category if category_valid else None,
                "category_valid": category_valid,
                "text": text,
                "char_start": start if isinstance(start, int) else None,
                "char_end": end if isinstance(end, int) else None,
                "span_valid": span_valid,
                "cited_ids": cited_ids,
                "extraction_valid": not problems,
                "extraction_problems": problems,
            }
        )
    return claims, truncated


def parse_assessment(text: str) -> dict[str, Any] | None:
    """Shape-validate one support reply; ``None`` = unusable."""
    data = parse_json_object(text)
    if not isinstance(data, dict):
        return None
    assessment = data.get("assessment")
    if not isinstance(assessment, str) or assessment not in ASSESSMENTS:
        return None
    explanation = data.get("explanation")
    if not isinstance(explanation, str):
        return None
    spans = data.get("quoted_spans")
    if not isinstance(spans, list) or not all(isinstance(span, str) for span in spans):
        return None
    return {
        "assessment": assessment,
        "explanation": explanation,
        "quoted_spans": [span for span in spans if span],
    }


def unverified_quotes(quoted_spans: list[str], excerpts: str) -> list[str]:
    """Every quoted span must occur verbatim in the supplied excerpts."""
    return [span for span in quoted_spans if span not in excerpts]


def assessment_is_valid(result: dict[str, Any], excerpts: str) -> tuple[bool, list[str]]:
    """Verdict validity: no invented quotes, and a judgement that quotes
    something. ``not_established`` may legitimately have no quote."""
    bad = unverified_quotes(list(result["quoted_spans"]), excerpts)
    if bad:
        return False, bad
    if result["assessment"] != "not_established" and not result["quoted_spans"]:
        return False, []
    return True, []


def _record_content(raw: dict[str, Any]) -> str:
    """Verbatim text of one source record (shared shape with triage)."""
    if isinstance(raw.get("text"), str):
        return str(raw["text"])
    strings = [str(value) for value in raw.values() if isinstance(value, str)]
    if strings:
        return "\n".join(strings)
    return str(raw)


def _cited_ref(cited_id: str) -> CitationRef:
    """Split ``kind:id`` tokens; bare uuids resolve via DB (kind ``""``)."""
    if ":" in cited_id:
        prefix, ident = cited_id.split(":", 1)
        kind = _CITED_PREFIXES.get(prefix.lower(), prefix.lower())
        return CitationRef(kind=kind, id=ident.strip())
    return CitationRef(kind="", id=cited_id.strip())


# --- submission --------------------------------------------------------------


def _clear_stale(job: AnalysisJob, settings: Settings) -> bool:
    """Terminal-ize a stale pending/running audit left by a restart.

    No durable queue exists (same platform limitation as every feature), so
    an orphaned job would lock its draft hash forever.
    """
    try:
        if job.status == "running":
            if not jobs_svc.is_timed_out(job):
                return False
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            jobs_svc.transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or settings.REPORT_AUDIT_TIMEOUT_SECONDS
            ):
                return False
            job.error = "superseded: pending too long without a runner"
            jobs_svc.transition(job, "failed")
        return True
    except Exception:  # noqa: BLE001 - stale clearing must never block submit
        logger.exception("stale report-audit job check failed")
        return False


async def submit_report_audit(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    settings: Settings,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    draft_text: str | None = None,
) -> tuple[AnalysisJob, bool, dict[str, Any]]:
    """Validate the draft source and enqueue one audit run.

    Exactly one source: ``conversation_id`` + ``message_id`` (a report-mode
    assistant message of this case) XOR ``draft_text``. Returns
    ``(job, created, snapshot)``; the snapshot is handed to the background
    runner in memory so the raw draft is never persisted on the job row.
    """
    if (conversation_id is None) != (message_id is None):
        raise ReportAuditRejected(
            CODE_DRAFT_SOURCE_INVALID,
            "conversation_id and message_id must be provided together",
        )
    if conversation_id is None and draft_text is None:
        raise ReportAuditRejected(
            CODE_DRAFT_SOURCE_INVALID,
            "provide draft_text or a report conversation message reference",
        )
    if conversation_id is not None and draft_text is not None:
        raise ReportAuditRejected(CODE_DRAFT_SOURCE_INVALID, "provide exactly one draft source")

    source_type = "text"
    snapshot: dict[str, Any] = {
        "source_type": "text",
        "conversation_id": None,
        "message_id": None,
    }
    if conversation_id is not None and message_id is not None:
        source_type = "message"
        conv_result = await session.execute(
            select(AIConversation).where(
                AIConversation.id == conversation_id,
                AIConversation.case_id == case_id,
            )
        )
        conversation = conv_result.scalar_one_or_none()
        if conversation is None:
            raise ReportAuditRejected(
                CODE_DRAFT_UNAVAILABLE, "report conversation not found in this case"
            )
        if conversation.mode != "report":
            raise ReportAuditRejected(
                CODE_MESSAGE_NOT_REPORT_MODE,
                "conversation is not a report conversation",
            )
        message_result = await session.execute(
            select(AIMessage).where(
                AIMessage.id == message_id,
                AIMessage.conversation_id == conversation.id,
            )
        )
        message = message_result.scalar_one_or_none()
        if message is None:
            raise ReportAuditRejected(
                CODE_DRAFT_UNAVAILABLE, "report message not found in this conversation"
            )
        if message.role != "assistant":
            raise ReportAuditRejected(
                CODE_DRAFT_SOURCE_INVALID,
                "only assistant report messages can be audited",
            )
        text = message.content
        snapshot["conversation_id"] = str(conversation.id)
        snapshot["message_id"] = str(message.id)
    else:
        assert draft_text is not None  # narrowed by the XOR checks above
        text = draft_text

    if not text.strip():
        raise ReportAuditRejected(CODE_DRAFT_SOURCE_INVALID, "draft is empty")
    if len(text) > settings.REPORT_AUDIT_MAX_DRAFT_CHARS:
        raise ReportAuditRejected(
            CODE_DRAFT_TOO_LARGE,
            f"draft exceeds {settings.REPORT_AUDIT_MAX_DRAFT_CHARS} characters",
        )
    snapshot["draft"] = text
    snapshot["source_type"] = source_type

    draft_hash = draft_sha256(text)
    active_result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.feature == "report_audit",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    for active in active_result.scalars().all():
        summary = dict(active.result_summary or {})
        if summary.get("draft_hash") != draft_hash:
            continue
        if _clear_stale(active, settings):
            await session.flush()
            break
        raise ReportAuditRejected(
            CODE_REPORT_AUDIT_ACTIVE, "an audit is already active for this draft"
        )

    attempt_result = await session.execute(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.feature == "report_audit",
        )
    )
    attempt = int(attempt_result.scalar_one()) + 1
    idempotency_key = f"report_audit:{draft_hash[:48]}:a{attempt}"
    try:
        job, created = await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature="report_audit",
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            timeout_seconds=settings.REPORT_AUDIT_TIMEOUT_SECONDS,
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
        return row, False, snapshot
    job.result_summary = {
        "draft_hash": draft_hash,
        "draft_source_type": source_type,
        "draft_chars": len(text),
        "conversation_id": snapshot["conversation_id"],
        "message_id": snapshot["message_id"],
    }
    await session.flush()
    return job, created, snapshot


# --- execution ---------------------------------------------------------------


async def _citation_outcomes(
    session: AsyncSession,
    *,
    user: User,
    case_id: uuid.UUID,
    cited_ids: list[str],
    budget: dict[str, int],
    kind_cache: dict[str, str],
) -> list[dict[str, Any]]:
    """Validate one claim's cited ids server-side (case-scoped, bounded).

    Cross-case and malformed ids become findings - never retrievals. The
    budget bounds ``validate_citation`` calls per run; ids past the budget
    are recorded unchecked and *not* marked ok (never trusted silently).
    """
    outcomes: list[dict[str, Any]] = []
    for cited_id in cited_ids[:_MAX_CITED_PER_CLAIM]:
        if budget["used"] >= _MAX_CITATION_CHECKS:
            outcomes.append(
                {
                    "cited_id": cited_id,
                    "ref_id": None,
                    "kind": None,
                    "checked": False,
                    "ok": False,
                    "codes": ["citation_budget_exceeded"],
                }
            )
            continue
        ref = _cited_ref(cited_id)
        if not ref.kind and ref.id:
            # bare uuid: resolve its actual kind in documented order (only
            # codes leave this function - no cross-case content is retrieved)
            if ref.id in kind_cache:
                kind = kind_cache[ref.id]
            else:
                kind = ""
                for candidate, model in _KIND_ORDER:
                    row = await session.get(model, ref.id)
                    if row is not None:
                        kind = candidate
                        break
                kind_cache[ref.id] = kind
            if not kind:
                # the id matches no known record anywhere: honest finding
                budget["used"] += 1
                outcomes.append(
                    {
                        "cited_id": cited_id,
                        "ref_id": ref.id,
                        "kind": "",
                        "checked": True,
                        "ok": False,
                        "codes": ["citation_record_missing"],
                    }
                )
                continue
            ref = CitationRef(kind=kind, id=ref.id)
        budget["used"] += 1
        check = await validate_citation(session, user=user, case_id=case_id, ref=ref)
        outcomes.append(
            {
                "cited_id": cited_id,
                "ref_id": ref.id,
                "kind": ref.kind,
                "checked": True,
                "ok": bool(check.ok),
                "codes": list(check.codes),
            }
        )
    if len(cited_ids) > _MAX_CITED_PER_CLAIM:
        for cited_id in cited_ids[_MAX_CITED_PER_CLAIM:]:
            outcomes.append(
                {
                    "cited_id": cited_id,
                    "ref_id": None,
                    "kind": None,
                    "checked": False,
                    "ok": False,
                    "codes": ["citation_not_checked"],
                }
            )
    return outcomes


async def _excerpt_bundle(
    session: AsyncSession,
    *,
    cited_outcomes: list[dict[str, Any]],
    settings: Settings,
) -> str:
    """Bounded verbatim excerpts for the valid citations of one claim."""
    parts: list[str] = []
    total = 0
    seen: set[str] = set()
    for outcome in cited_outcomes:
        if not outcome["ok"]:
            continue
        cited_id = str(outcome["cited_id"])
        ref_id = outcome.get("ref_id")
        kind = str(outcome.get("kind") or "")
        if cited_id in seen or not ref_id:
            continue
        seen.add(cited_id)
        body = ""
        if kind == "evidence_file":
            rows = (
                (
                    await session.execute(
                        select(SourceRecord)
                        .where(SourceRecord.evidence_file_id == ref_id)
                        .order_by(SourceRecord.record_no)
                        .limit(_MAX_EXCERPT_RECORDS)
                    )
                )
                .scalars()
                .all()
            )
            texts = [
                _record_content(dict(row.raw_data or {}))[:_MAX_EXCERPT_RECORD_CHARS]
                for row in rows
            ]
            body = "\n".join(text for text in texts if text.strip())
        elif kind == "source_record":
            row = await session.get(SourceRecord, uuid.UUID(str(ref_id)))
            if row is not None:
                body = _record_content(dict(row.raw_data or {}))[:_MAX_EXCERPT_RECORD_CHARS]
        if not body.strip():
            continue
        part = f"[{kind}:{cited_id}]\n{body}"
        parts.append(part)
        total += len(part)
        if total >= _EXCERPT_TOTAL_CHARS:
            break
    combined = "\n\n".join(parts)
    return combined[: settings.REPORT_AUDIT_CONTEXT_MAX_CHARS]


async def _scan_case_records(
    session: AsyncSession, *, case_id: uuid.UUID
) -> list[tuple[int, str, str]]:
    """Bounded, case-scoped source-record contents for counter-evidence."""
    rows = (
        await session.execute(
            select(
                SourceRecord.record_no,
                SourceRecord.raw_data,
                EvidenceFile.original_filename,
            )
            .join(EvidenceFile, EvidenceFile.id == SourceRecord.evidence_file_id)
            .where(EvidenceFile.case_id == str(case_id))
            .where(EvidenceFile.deleted_at.is_(None))
            .order_by(SourceRecord.record_no)
            .limit(_MAX_COUNTER_RECORDS)
        )
    ).all()
    contents: list[tuple[int, str, str]] = []
    for record_no, raw_data, filename in rows:
        text = _record_content(dict(raw_data or {}))
        if text.strip():
            contents.append((int(record_no), text, str(filename or "")))
    return contents


def _counter_matches(
    claim: dict[str, Any], records: list[tuple[int, str, str]]
) -> list[dict[str, Any]]:
    """Word-boundary substring matches for the claim's tokens (bounded)."""
    tokens = list(claim["counter_tokens"])
    matches: list[dict[str, Any]] = []
    for token in tokens:
        if len(matches) >= _MAX_COUNTER_MATCHES_PER_CLAIM:
            break
        pattern = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)
        for record_no, content, filename in records:
            hit = pattern.search(content)
            if hit is None:
                continue
            start = max(0, hit.start() - 60)
            excerpt = content[start : hit.end() + 100]
            matches.append(
                {
                    "token": token,
                    "record_no": record_no,
                    "evidence": filename,
                    "excerpt": excerpt,
                }
            )
            if len(matches) >= _MAX_COUNTER_MATCHES_PER_CLAIM:
                break
    return matches


def _finding(code: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "severity": FINDING_SEVERITY[code],
        "detail": detail,
    }


async def execute_report_audit(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    extractor: Any,
    snapshot: dict[str, Any],
) -> None:
    """Run one report audit. Own session, cooperative cancel, honest
    partial/failed states. The model is validated, never trusted."""
    job = await session.get(AnalysisJob, job_id)
    if job is None:
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    summary: dict[str, Any] = dict(job.result_summary or {})
    counts: dict[str, int] = {
        "claims_extracted": 0,
        "claims_truncated": 0,
        "claims_invalid": 0,
        "citations_checked": 0,
        "citations_invalid": 0,
        "assessments_attempted": 0,
        "assessments_valid": 0,
        "assessments_invalid": 0,
        "findings_high": 0,
        "findings_medium": 0,
        "findings_info": 0,
        "records_searched": 0,
        "counter_matches": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
        "artifacts_flagged": 0,
        "units_failed": 0,
    }
    summary.update(counts)
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
                action="report_audit.failed",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"code": code, "denial": denial},
            )
        await session.commit()

    async def _stop(*, stop: str) -> None:
        job.result_summary = summary
        if stop == "cancel":
            jobs_svc.transition(job, "canceled")
            action = "report_audit.canceled"
        else:
            job.error = f"report audit timed out after {job.timeout_seconds}s"
            jobs_svc.transition(job, "failed")
            action = "report_audit.timed_out"
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

    if actor_id is not None and not await authz_svc.still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_READ
    ):
        await _fail(
            CODE_CASE_ACCESS_DENIED,
            "case access was revoked before the run started",
            denial=True,
        )
        return
    if job.cancel_requested:
        jobs_svc.transition(job, "canceled")
        await session.flush()
        if actor_id is not None:
            await audit_svc.record_audit(
                session,
                actor_id=actor_id,
                action="report_audit.canceled",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"stage": "before_run"},
            )
        await session.commit()
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    actor: User | None = None
    if actor_id is not None:
        actor = await session.get(User, actor_id)
    if actor is None:
        await _fail(CODE_CASE_ACCESS_DENIED, "audit job has no authorized actor", denial=True)
        return

    try:
        stage = "snapshot"
        text = snapshot.get("draft") if isinstance(snapshot, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ReportAuditRunError(CODE_DRAFT_SOURCE_INVALID, "draft snapshot missing")
        if len(text) > settings.REPORT_AUDIT_MAX_DRAFT_CHARS:
            raise ReportAuditRunError(CODE_DRAFT_TOO_LARGE, "draft snapshot too large")
        draft_hash = draft_sha256(text)
        summary["draft_hash"] = draft_hash
        summary["draft_chars"] = len(text)
        jobs_svc.advance(job, processed=0, total=1)
        await session.flush()
        await session.commit()

        stage = "extract"
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(stop=stop)
            return
        raw_claims: list[dict[str, Any]] | None
        try:
            completion = await extractor.extract_report_claims(
                draft=text, max_claims=settings.REPORT_AUDIT_MAX_CLAIMS
            )
        except Exception as exc:  # noqa: BLE001 - AI-layer outage -> honest failure
            logger.warning("report-audit extraction call failed: %s", str(exc)[:200])
            raise ReportAuditRunError(
                CODE_REPORT_AUDIT_FAILED, "model call failed during claim extraction"
            ) from exc
        raw_claims = parse_claims_reply(completion.text)
        extraction_failed = raw_claims is None
        issues: list[dict[str, Any]] = []
        if raw_claims is None:
            raw_claims = []
            summary["units_failed"] += 1
            issues.append({"code": "unparseable_model_output"})
        claims, truncated = normalize_claims(
            raw_claims, draft=text, max_claims=settings.REPORT_AUDIT_MAX_CLAIMS
        )
        summary["claims_extracted"] = len(raw_claims)
        summary["claims_truncated"] = truncated
        summary["claims_invalid"] = sum(1 for claim in claims if not claim["extraction_valid"])

        stage = "validate"
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(stop=stop)
            return
        records = await _scan_case_records(session, case_id=case_id)
        summary["records_searched"] = len(records)
        budget = {"used": 0}
        kind_cache: dict[str, str] = {}
        timeline_claims: list[dict[str, Any]] = []
        amount_claims: list[dict[str, Any]] = []
        for claim in claims:
            outcome_list = await _citation_outcomes(
                session,
                user=actor,
                case_id=case_id,
                cited_ids=list(claim["cited_ids"]),
                budget=budget,
                kind_cache=kind_cache,
            )
            summary["citations_checked"] += sum(1 for o in outcome_list if o["checked"])
            summary["citations_invalid"] += sum(1 for o in outcome_list if not o["ok"])
            claim["citations"] = outcome_list
            claim["deterministic"] = {
                "amounts": [],
                "dates": [],
                "unparsed_dates": 0,
                "arithmetic": None,
            }
            amounts = parse_amounts(claim["text"])
            claim["deterministic"]["amounts"] = amounts
            dates, unparsed = parse_dates(claim["text"])
            claim["deterministic"]["dates"] = dates
            claim["deterministic"]["unparsed_dates"] = unparsed
            claim["deterministic"]["arithmetic"] = check_arithmetic(claim["text"], amounts)
            claim["counter_tokens"] = claim_tokens(claim["text"], amounts)
            if claim["category"] == "timeline" and dates:
                timeline_claims.append(
                    {
                        "claim_index": claim["claim_index"],
                        "char_start": claim["char_start"],
                        "dates": dates,
                    }
                )
            if amounts:
                amount_claims.append(
                    {
                        "claim_index": claim["claim_index"],
                        "char_start": claim["char_start"],
                        "amounts": amounts,
                    }
                )
        for issue in chronology_issues(timeline_claims):
            claims[issue["claim_index"]]["chronology_issue"] = issue
        for conflict in currency_conflicts(amount_claims):
            claims[conflict["claim_index"]]["currency_conflict"] = conflict

        # case timeline alignment (info-level context, never a verdict)
        event_dates: set[str] = set()
        timeline_rows = (
            await session.execute(
                select(TimelineEvent.occurred_at)
                .where(TimelineEvent.case_id == str(case_id))
                .order_by(TimelineEvent.occurred_at)
                .limit(_MAX_TIMELINE_EVENTS)
            )
        ).scalars()
        for occurred_at in timeline_rows:
            event_dates.add(occurred_at.date().isoformat())
        timeline_claim_dates = [day for item in timeline_claims for day in item["dates"]]

        stage = "assess"
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(stop=stop)
            return
        if not await authz_svc.still_authorized_for_case(
            session, user_id=actor.id, case_id=case_id, permission=rbac.PERM_CASE_READ
        ):
            await _fail(CODE_CASE_ACCESS_DENIED, "access revoked mid-run", denial=True)
            return
        for claim in claims:
            claim["assessment"] = None
            claim["assessment_skipped"] = None
            valid_citations = [outcome for outcome in claim.get("citations", []) if outcome["ok"]]
            if not valid_citations:
                claim["assessment_skipped"] = "no_valid_citation"
                continue
            excerpts = await _excerpt_bundle(
                session,
                cited_outcomes=valid_citations,
                settings=settings,
            )
            if not excerpts.strip():
                claim["assessment_skipped"] = "no_excerpt_available"
                continue
            summary["assessments_attempted"] += 1
            try:
                completion = await extractor.assess_claim_support(
                    claim=claim["text"][:2000], sources=excerpts
                )
            except Exception as exc:  # noqa: BLE001 - honest partial
                summary["units_failed"] += 1
                issues.append({"code": "model_call_failed"})
                claim["assessment_skipped"] = "model_call_failed"
                logger.warning("report-audit support call failed: %s", str(exc)[:200])
                continue
            result = parse_assessment(completion.text)
            if result is None:
                summary["units_failed"] += 1
                issues.append({"code": "unparseable_model_output"})
                claim["assessment_skipped"] = "unparseable_model_output"
                continue
            valid, bad_quotes = assessment_is_valid(result, excerpts)
            result["quotes_verified"] = valid
            result["unverified_quotes"] = bad_quotes
            claim["assessment"] = result
            if valid:
                summary["assessments_valid"] += 1
            else:
                summary["assessments_invalid"] += 1
                issues.append({"code": "assessment_unverified"})

        stage = "findings"
        findings_summary = {"high": 0, "medium": 0, "info": 0}
        claims_payload: list[dict[str, Any]] = []
        for claim in claims:
            findings: list[dict[str, Any]] = []
            if not claim["extraction_valid"]:
                findings.append(
                    _finding(
                        "claim_extraction_invalid",
                        {"problems": list(claim["extraction_problems"])},
                    )
                )
            for outcome in claim.get("citations", []):
                if outcome["ok"]:
                    continue
                codes = list(outcome["codes"])
                if "citation_value_mismatch" in codes:
                    findings.append(
                        _finding(
                            "numeric_mismatch",
                            {"cited_id": outcome["cited_id"], "codes": codes},
                        )
                    )
                if any(code != "citation_value_mismatch" for code in codes):
                    findings.append(
                        _finding(
                            "invalid_citation",
                            {"cited_id": outcome["cited_id"], "codes": codes},
                        )
                    )
            arithmetic = claim["deterministic"]["arithmetic"]
            if arithmetic is not None and not arithmetic["ok"]:
                findings.append(_finding("numeric_mismatch", dict(arithmetic)))
            if claim.get("chronology_issue"):
                findings.append(_finding("timeline_discrepancy", dict(claim["chronology_issue"])))
            if claim.get("currency_conflict"):
                findings.append(_finding("currency_mismatch", dict(claim["currency_conflict"])))
            assessment = claim.get("assessment")
            if assessment is not None:
                if not assessment["quotes_verified"]:
                    findings.append(
                        _finding(
                            "assessment_unverified",
                            {
                                "unverified_quotes": list(assessment["unverified_quotes"])
                                or ["no quoted span supplied"],
                            },
                        )
                    )
                elif assessment["assessment"] in FINDING_SEVERITY:
                    findings.append(
                        _finding(
                            assessment["assessment"],
                            {"explanation": assessment["explanation"]},
                        )
                    )
            matches = _counter_matches(claim, records)
            claim["counter_matches"] = matches
            if matches:
                findings.append(
                    _finding(
                        "counter_evidence_candidate",
                        {
                            "tokens": list(claim["counter_tokens"]),
                            "records": [m["record_no"] for m in matches],
                        },
                    )
                )
            if not findings:
                severity = "none"
            else:
                severity = max(
                    (item["severity"] for item in findings),
                    key=lambda value: _SEVERITY_RANK[value],
                )
            for item in findings:
                bucket = item["severity"]
                findings_summary[bucket] += 1
                summary[f"findings_{bucket}"] += 1
            counter_note = (
                "no matching records among those scanned"
                if records and not matches
                else ("no source records exist for this case" if not records else "")
            )
            claims_payload.append(
                {
                    "claim_index": claim["claim_index"],
                    "claim_id": claim["claim_id"],
                    "category": claim["category"],
                    "category_valid": claim["category_valid"],
                    "text": claim["text"],
                    "char_start": claim["char_start"],
                    "char_end": claim["char_end"],
                    "span_valid": claim["span_valid"],
                    "extraction_valid": claim["extraction_valid"],
                    "cited_ids": list(claim["cited_ids"]),
                    "citations": claim.get("citations", []),
                    "deterministic": claim["deterministic"],
                    "assessment": assessment,
                    "assessment_skipped": claim.get("assessment_skipped"),
                    "counter_evidence": {
                        "records_searched": len(records),
                        "tokens": list(claim["counter_tokens"]),
                        "matches": matches,
                        "note": counter_note,
                    },
                    "findings": findings,
                    "severity": severity,
                }
            )
        summary["counter_matches"] = sum(
            len(item["counter_evidence"]["matches"]) for item in claims_payload
        )

        stage = "record"
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(stop=stop)
            return
        unique_issues: list[dict[str, Any]] = []
        for issue in issues:
            if issue not in unique_issues:
                unique_issues.append(issue)
        summary["artifacts_flagged"] += 1  # always flagged: model-derived, unreviewed
        validation_errors: list[dict[str, Any]] = [
            {
                "code": "model_claims_unreviewed",
                "field": "claims",
                "value": None,
            },
            *unique_issues,
        ]
        payload: dict[str, Any] = {
            "report_audit": True,
            "draft_source": {
                "type": summary.get("draft_source_type", snapshot.get("source_type")),
                "conversation_id": summary.get("conversation_id"),
                "message_id": summary.get("message_id"),
                "draft_hash": draft_hash,
                "draft_chars": len(text),
            },
            "draft_hash": draft_hash,
            "draft_chars": len(text),
            "claims": claims_payload,
            "findings_summary": {
                "claims": len(claims_payload),
                "claims_with_findings": sum(1 for item in claims_payload if item["findings"]),
                **findings_summary,
            },
            "counter_evidence": {
                "records_searched": len(records),
                "claims_with_matches": sum(
                    1 for item in claims_payload if item["counter_evidence"]["matches"]
                ),
            },
            "case_timeline": {
                "event_dates": len(event_dates),
                "claim_dates_total": len(timeline_claim_dates),
                "claim_dates_matched": sum(1 for day in timeline_claim_dates if day in event_dates),
            },
            "model": {
                "claims_extracted": summary["claims_extracted"],
                "claims_truncated": summary["claims_truncated"],
                "extraction_failed": extraction_failed,
                "assessments_attempted": summary["assessments_attempted"],
                "assessments_valid": summary["assessments_valid"],
                "assessments_invalid": summary["assessments_invalid"],
            },
            "checks_scope": (
                "spans must reproduce the draft verbatim; citations are validated "
                "server-side (shape, existence, case scope, locator, quoted value); "
                "amounts use documented ASCII+Devanagari rules (comma/dot grouping); "
                "chronology orders timeline-category claims in draft order and "
                "reports alignment with case timeline dates as context; assessment "
                "validity = every quoted span occurs verbatim in the supplied "
                "excerpts (explanation prose is not machine-verified); "
                "counter-evidence lists candidate matches among scanned records "
                "and never asserts absence"
            ),
            "limitations": [
                "same digit-string amounts written with different currencies are "
                "surfaced as candidates; two legitimately different amounts may "
                "appear and the reviewer decides",
                "unparseable numeric or date expressions are ignored by the "
                "deterministic checks and counted per claim",
                "an intentionally unordered report timeline yields discrepancy "
                "findings for human review (chronology assumes draft order)",
                "the original draft is never modified; suggested corrections are "
                "proposals for a new draft",
            ],
            "claim_prompt_version": REPORT_AUDIT_CLAIM_PROMPT_VERSION,
            "support_prompt_version": REPORT_AUDIT_SUPPORT_PROMPT_VERSION,
            "rules_version": REPORT_AUDIT_RULES_VERSION,
        }
        _, created = await artifacts_svc.record_artifact(
            session,
            case_id=case_id,
            kind="report_claim_review",
            origin="llm",
            payload=payload,
            source_locator={
                "scope": "case",
                "draft_hash": draft_hash,
                "claims": len(claims_payload),
            },
            validation_status="flagged",
            validation_errors=validation_errors,
            prompt_version=REPORT_AUDIT_CLAIM_PROMPT_VERSION,
            model_profile="report_audit",
            analysis_job_id=job.id,
            created_by=actor_id,
            status="pending_review",
        )
        if created:
            summary["artifacts_created"] += 1
        else:
            summary["artifacts_reused"] += 1
        jobs_svc.advance(job, processed=1)
        await session.flush()

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
            action="report_audit.completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata=_counts(summary),
        )
        await session.commit()
    except ReportAuditRunError as exc:
        await session.rollback()
        await session.refresh(job)
        await _fail(exc.code, exc.message)
    except Exception:
        logger.exception("report-audit run crashed", extra={"job_id": str(job_id)})
        await session.rollback()
        await session.refresh(job)
        await _fail(CODE_REPORT_AUDIT_FAILED, f"unexpected error during stage {stage}")


def _counts(summary: dict[str, Any]) -> dict[str, Any]:
    """Audit metadata: integer counts and identifiers only - never draft text."""
    keys = (
        "claims_extracted",
        "claims_truncated",
        "claims_invalid",
        "citations_checked",
        "citations_invalid",
        "assessments_attempted",
        "assessments_valid",
        "assessments_invalid",
        "findings_high",
        "findings_medium",
        "findings_info",
        "records_searched",
        "counter_matches",
        "artifacts_created",
        "artifacts_reused",
        "artifacts_flagged",
        "units_failed",
    )
    return {key: summary[key] for key in keys if key in summary and isinstance(summary[key], int)}


async def run_report_audit_job(app: Any, job_id: uuid.UUID, snapshot: dict[str, Any]) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory = database.session_factory()
    try:
        async with factory() as session:
            await execute_report_audit(
                session,
                job_id=job_id,
                settings=settings,
                extractor=app.state.ai_service,
                snapshot=snapshot,
            )
    except Exception:
        logger.exception("background report audit failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                job.error = "background report-audit task crashed"
                jobs_svc.transition(job, "failed")
                await session.commit()

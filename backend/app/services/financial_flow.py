"""Deterministic financial fact extraction and analysis (Phase 4, feature A).

Pure, versioned rules. The local model never runs here and never selects what
it sees: it only explains the results these functions return (see
``AIService.explain_financial_flow`` and ``docs/ai/PHASE_4_DESIGN.md`` §4).

Data reality (A1, measured over **all 1000** development records — the full
inventory and blockers are recorded in ``docs/ai/PHASE_4_DESIGN.md`` §2.2):

* ``source_records`` carries **no** financial columns; every fact is an
  extraction from the ``raw_data`` JSON document.
* No payer/sender key and no timestamp key occurs in any record, and
  ``relationships`` has no transfer edge type.
* ``victims`` holds case-scoped loss totals in ``double precision`` columns.

Consequently this module **extracts what exists**, **marks what is absent**,
and **refuses to compute what the ingest cannot support**:

* amounts are exact ``Decimal`` end-to-end (no float arithmetic ever);
* every absent field appears in the fact's ``missing`` list and in aggregate
  counts — nothing is defaulted or invented;
* direction-dependent metrics (inflow/outflow/net) are returned as
  ``not_computable_no_direction`` rather than a fabricated zero;
* structure-network edges are typed ``association``/``relationship`` and the
  payload reports ``confirmed_transfer_edges: 0`` honestly;
* every pattern rule is either ``firing`` (with exact evidence) or
  ``not_evaluable`` (with the specific missing input) — never silently
  dropped, never fired on absent data.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import rbac
from app.core.codes import CODE_CASE_ACCESS_DENIED
from app.core.config import Settings
from app.models import AnalysisJob, Entity, EvidenceFile, Relationship, SourceRecord, Victim
from app.services import analysis_jobs as jobs_svc
from app.services import audit as audit_svc
from app.services.artifacts import record_artifact
from app.services.authorization import still_authorized_for_case
from app.services.timeline_reconstruction import parse_timestamp

logger = logging.getLogger(__name__)

FLOW_RULES_VERSION = "flow-rules/1.0.0"
FLOW_PATTERN_RULES_VERSION = "flow-patterns/1.0.0"
FLOW_ARTIFACT_KIND = "financial_finding"

# -- documented alias tables ---------------------------------------------------
# Ordered first-hit-wins lookups over ``raw_data`` keys. The observed key set in
# current data is recorded in the design doc (§2.2); aliases beyond it are kept
# so a future evidence format that *does* carry them is read correctly rather
# than silently ignored. Reading a key the source actually provided is not
# inference.

TXN_REF_ALIASES = (
    "transaction_id",
    "txn_id",
    "upi_txn_id",
    "utr",
    "reference_no",
    "ref_no",
    "transaction_ref",
)
AMOUNT_ALIASES = ("amount", "transaction_amount", "txn_amount", "value", "sum")
CURRENCY_ALIASES = ("currency", "currency_code", "ccy")
RECEIVER_ALIASES = ("beneficiary_name", "payee_name", "receiver_name", "beneficiary", "payee")
RECEIVER_PHONE_ALIASES = ("beneficiary_phone", "receiver_number", "payee_phone")
ACCOUNT_ALIASES = (
    "account",
    "account_no",
    "account_number",
    "account_id",
    "bank_account",
    "upi_id",
    "vpa",
)
BANK_ALIASES = ("bank_name", "bank", "ifsc_bank")
MERCHANT_ALIASES = ("merchant", "merchant_name", "payee_merchant")
PARTY_ALIASES = ("name", "party_name", "customer_name")
STATUS_ALIASES = ("status", "txn_status", "transaction_status", "payment_status")
TIME_ALIASES = ("date", "time", "occurred_at", "timestamp", "txn_date", "value_date", "posted_at")

# Documented status vocabulary. Keyword sets are constants (configuration, not
# hidden logic); a value matching more than one class is ``ambiguous``.
STATUS_KEYWORDS: dict[str, frozenset[str]] = {
    "completed": frozenset(
        {
            "completed",
            "complete",
            "success",
            "successful",
            "settled",
            "done",
            "posted",
            "paid",
            "confirmed",
        }
    ),
    "pending": frozenset(
        {"pending", "processing", "in_progress", "initiated", "queued", "authorized"}
    ),
    "rejected": frozenset(
        {"rejected", "failed", "declined", "denied", "returned", "dishonoured"}
    ),
    "reversed": frozenset(
        {"reversed", "reversal", "refund", "refunded", "chargeback", "cancelled", "canceled"}
    ),
}
STATUS_VOCABULARY = tuple(sorted(STATUS_KEYWORDS)) + ("ambiguous", "unknown")

# Currency tokens recognised *inside* an amount string (e.g. "INR 4500", "₹4500").
# Only an explicit literal is honoured; absence never implies a default.
_CURRENCY_TOKEN_RE = re.compile(r"(?i)\b(inr|usd|eur|gbp|rs\.?)\b|^[₹$€£]")
_CURRENCY_TOKEN_MAP = {"rs": "INR", "₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
_NUMBER_CLEAN_RE = re.compile(r"[,\s]")


class AmountParse(TypedDict, total=False):
    value: Decimal | None
    original: str | None
    precision: str | None
    warning: str | None
    currency_hint: str | None


def parse_amount(raw_value: Any) -> AmountParse:
    """Parse one raw value into an exact ``Decimal`` plus its provenance.

    The original value is always preserved verbatim (``original``); the parsed
    value is only ever derived from it, never rounded. Float sources are marked
    ``float_source`` so downstream output can carry the precision caveat.
    Non-numeric junk is rejected (``warning="amount_invalid"``) — never coerced
    into a number.
    """
    if raw_value is None:
        return AmountParse(value=None, original=None)
    if isinstance(raw_value, bool):
        return AmountParse(value=None, original=str(raw_value), warning="amount_invalid")
    if isinstance(raw_value, Decimal):
        return AmountParse(value=raw_value, original=str(raw_value), precision="decimal_source")
    if isinstance(raw_value, int):
        return AmountParse(
            value=Decimal(raw_value), original=str(raw_value), precision="int_source"
        )
    if isinstance(raw_value, float):
        # str(float) yields the shortest round-tripping decimal representation;
        # the arithmetic downstream is still Decimal. Flagged so output can say
        # the source column was binary floating point.
        try:
            return AmountParse(
                value=Decimal(str(raw_value)),
                original=str(raw_value),
                precision="float_source",
            )
        except InvalidOperation:
            return AmountParse(value=None, original=str(raw_value), warning="amount_invalid")
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return AmountParse(value=None, original=raw_value)
        hint = None
        match = _CURRENCY_TOKEN_RE.search(text)
        if match is not None:
            token = (match.group(0) or "").strip().lower()
            hint = _CURRENCY_TOKEN_MAP.get(token) or (token.upper() if len(token) == 3 else None)
        cleaned = _CURRENCY_TOKEN_RE.sub(" ", text)
        cleaned = _NUMBER_CLEAN_RE.sub("", cleaned).strip()
        try:
            return AmountParse(
                value=Decimal(cleaned),
                original=raw_value,
                precision="string_source",
                currency_hint=hint,
            )
        except InvalidOperation:
            return AmountParse(value=None, original=raw_value, warning="amount_invalid")
    return AmountParse(value=None, original=str(raw_value), warning="amount_invalid")


def classify_status(value: Any) -> str:
    """Map a raw status value onto the documented vocabulary."""
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    token = value.strip().lower().replace("-", "_").replace(" ", "_")
    hits = [name for name, words in STATUS_KEYWORDS.items() if token in words]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return "ambiguous"
    for name, words in STATUS_KEYWORDS.items():
        for word in words:
            if word in token:
                return name
    return "unknown"


def _first(raw: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str | None, Any]:
    for key in aliases:
        value = raw.get(key)
        if value is None or value == "" or value == [] or value == {}:
            continue
        return key, value
    return None, None


def normalize_ref(value: str) -> str:
    """Documented, lossless-for-comparison normalization of an account-ish ref.

    Originals are always kept alongside this form. Comparison only: trim,
    upper-case, strip separators/whitespace; no validation is implied.
    """
    return re.sub(r"[\s\-.]", "", value.strip().upper())


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


# -- facts ---------------------------------------------------------------------


@dataclass(frozen=True)
class TransactionFact:
    """One deterministic extraction from one ``SourceRecord``.

    ``fact_class`` distinguishes movement evidence from context:
    ``transaction`` (an amount or a transaction reference is present) versus
    ``account_reference`` (an account/bank/party is present with no movement
    evidence). Only ``transaction`` facts take part in money aggregates.
    """

    fact_class: str
    source_record_id: str
    evidence_file_id: str
    record_no: int
    txn_ref_original: str | None
    txn_ref_normalized: str | None
    amount: Decimal | None
    amount_original: str | None
    amount_precision: str | None
    currency: str | None
    currency_source: str | None
    receiver: str | None
    receiver_phone: str | None
    account_original: str | None
    account_normalized: str | None
    bank: str | None
    merchant: str | None
    party: str | None
    status: str
    occurred_at: datetime | None
    occurred_at_original: str | None
    occurred_at_granularity: str | None
    missing: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def dedupe_key(self) -> str:
        """Documented grouping key for de-duplicating repeated records.

        A transaction reference groups unambiguously. Without one, records that
        repeat the same amount against the same account are grouped together —
        which may over- *or* under-merge, so aggregates always report both the
        grouped and the ungrouped total and state this caveat.
        """
        if self.txn_ref_normalized:
            return f"txn:{self.txn_ref_normalized}"
        amount = str(self.amount) if self.amount is not None else "-"
        return f"amtacct:{amount}|{self.account_normalized or ''}"

    def to_payload(self) -> dict[str, Any]:
        """JSON-safe view (Decimal -> exact string, datetime -> ISO-8601)."""
        return {
            "fact_class": self.fact_class,
            "source_record_id": self.source_record_id,
            "evidence_file_id": self.evidence_file_id,
            "record_no": self.record_no,
            "source_locator": {
                "record_no": self.record_no,
                "evidence_file_id": self.evidence_file_id,
            },
            "txn_ref_original": self.txn_ref_original,
            "txn_ref_normalized": self.txn_ref_normalized,
            "amount": str(self.amount) if self.amount is not None else None,
            "amount_original": self.amount_original,
            "amount_precision": self.amount_precision,
            "currency": self.currency,
            "currency_source": self.currency_source,
            "receiver": self.receiver,
            "receiver_phone": self.receiver_phone,
            "account_original": self.account_original,
            "account_normalized": self.account_normalized,
            "bank": self.bank,
            "merchant": self.merchant,
            "party": self.party,
            "status": self.status,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "occurred_at_original": self.occurred_at_original,
            "occurred_at_granularity": self.occurred_at_granularity,
            "missing": list(self.missing),
            "limitations": list(self.limitations),
        }


def extract_fact(
    record: SourceRecord, evidence_file_id: str
) -> tuple[TransactionFact | None, str | None]:
    """Extract one fact, or ``None`` when the record holds no financial field.

    Returns ``(fact, warning)`` where ``warning`` is ``"amount_invalid"`` when a
    present amount could not be parsed as a number.
    """
    raw = record.raw_data
    if not isinstance(raw, dict):
        return None, None

    amount_key, amount_raw = _first(raw, AMOUNT_ALIASES)
    currency_key, currency_raw = _first(raw, CURRENCY_ALIASES)
    txn_key, txn_raw = _first(raw, TXN_REF_ALIASES)
    recv_key, recv_raw = _first(raw, RECEIVER_ALIASES)
    recv_phone_key, recv_phone_raw = _first(raw, RECEIVER_PHONE_ALIASES)
    acct_key, acct_raw = _first(raw, ACCOUNT_ALIASES)
    bank_key, bank_raw = _first(raw, BANK_ALIASES)
    merch_key, merch_raw = _first(raw, MERCHANT_ALIASES)
    party_key, party_raw = _first(raw, PARTY_ALIASES)
    status_key, status_raw = _first(raw, STATUS_ALIASES)
    time_key, time_raw = _first(raw, TIME_ALIASES)

    if amount_key is None and txn_key is None and acct_key is None and bank_key is None:
        if merch_key is None and recv_key is None and party_key is None:
            return None, None

    warning: str | None = None
    parsed = AmountParse(value=None, original=None)
    if amount_key is not None:
        parsed = parse_amount(amount_raw)
        warning = parsed.get("warning")

    currency: str | None = None
    currency_source: str | None = None
    if currency_key is not None and isinstance(currency_raw, str) and currency_raw.strip():
        currency = currency_raw.strip().upper()
        currency_source = "field"
    elif parsed.get("currency_hint"):
        currency = str(parsed["currency_hint"])
        currency_source = "amount_string"

    txn_original = str(txn_raw).strip() if txn_raw is not None else None
    txn_normalized = txn_original.upper() if txn_original else None

    account_original = str(acct_raw).strip() if acct_raw is not None else None
    account_normalized = normalize_ref(account_original) if account_original else None

    occurred_at: datetime | None = None
    occurred_original: str | None = None
    occurred_granularity: str | None = None
    if time_key is not None:
        parsed_ts = parse_timestamp(time_raw)
        if parsed_ts is not None and parsed_ts.occurred_at is not None:
            occurred_at = parsed_ts.occurred_at
            occurred_original = parsed_ts.original
            occurred_granularity = parsed_ts.granularity

    amount = parsed.get("value")
    fact_class = "transaction" if (amount is not None or txn_normalized) else "account_reference"

    missing: list[str] = []
    if amount is None:
        missing.append("amount")
    if currency is None:
        missing.append("currency")
    if occurred_at is None:
        missing.append("timestamp")
    if txn_normalized is None:
        missing.append("txn_ref")
    if account_original is None:
        missing.append("account")
    if fact_class == "transaction" and not recv_raw:
        missing.append("counterparty")
    if fact_class == "transaction":
        # No payer/sender key exists in any ingested record (§2.2), so the
        # direction is documented as absent rather than assumed.
        missing.append("source_direction")

    limitations: list[str] = []
    if amount is not None and currency is None:
        limitations.append("currency_unknown")
    if amount is not None and occurred_at is None:
        limitations.append("missing_timestamp")
    if parsed.get("precision") == "float_source":
        limitations.append("float_source")
    if warning == "amount_invalid":
        limitations.append("amount_invalid")
    if fact_class == "transaction":
        limitations.append("one_sided")

    status = classify_status(status_raw) if status_key is not None else "unknown"

    fact = TransactionFact(
        fact_class=fact_class,
        source_record_id=str(record.id),
        evidence_file_id=evidence_file_id,
        record_no=int(record.record_no),
        txn_ref_original=txn_original,
        txn_ref_normalized=txn_normalized,
        amount=amount if isinstance(amount, Decimal) else None,
        amount_original=parsed.get("original"),
        amount_precision=parsed.get("precision"),
        currency=currency,
        currency_source=currency_source,
        receiver=str(recv_raw).strip() if recv_raw is not None else None,
        receiver_phone=str(recv_phone_raw).strip() if recv_phone_raw is not None else None,
        account_original=account_original,
        account_normalized=account_normalized,
        bank=str(bank_raw).strip() if bank_raw is not None else None,
        merchant=str(merch_raw).strip() if merch_raw is not None else None,
        party=str(party_raw).strip() if party_raw is not None else None,
        status=status,
        occurred_at=occurred_at,
        occurred_at_original=occurred_original,
        occurred_at_granularity=occurred_granularity,
        missing=tuple(missing),
        limitations=tuple(limitations),
    )
    return fact, warning


def extract_facts(
    rows: list[SourceRecord],
) -> tuple[list[TransactionFact], dict[str, int]]:
    """Extract every fact from the scoped records (deterministic order)."""
    facts: list[TransactionFact] = []
    warnings: dict[str, int] = {
        "records_without_financial_fields": 0,
        "amount_invalid": 0,
        "amounts_parsed": 0,
    }
    for record in rows:
        fact, warning = extract_fact(record, str(record.evidence_file_id))
        if fact is None:
            warnings["records_without_financial_fields"] += 1
            continue
        if warning == "amount_invalid":
            warnings["amount_invalid"] += 1
        if fact.amount is not None:
            warnings["amounts_parsed"] += 1
        facts.append(fact)
    return facts, warnings


def extract_victim_financials(victims: list[Victim]) -> list[dict[str, Any]]:
    """Case-scoped victim loss totals (Float columns → flagged precision)."""
    out: list[dict[str, Any]] = []
    for victim in victims:
        entry: dict[str, Any] = {
            "victim_id": str(victim.id),
            "case_id": str(victim.case_id),
            "reported_amount": None,
            "amount_lost": None,
            "recovery_amount": None,
            "currency": victim.currency.strip().upper() if victim.currency else None,
            "incident_date": victim.incident_date.isoformat() if victim.incident_date else None,
            "precision": "float_source",
            "missing": [],
            "limitations": ["float_source"],
        }
        for attr in ("reported_amount", "amount_lost", "recovery_amount"):
            value = getattr(victim, attr)
            if value is None:
                entry["missing"].append(attr)
                continue
            # double precision column: Decimal(str(value)) keeps the value the
            # investigator read; float_source records that the source was binary.
            entry[attr] = str(Decimal(str(value)))
        if entry["currency"] is None:
            entry["missing"].append("currency")
            entry["limitations"].append("currency_unknown")
        if victim.incident_date is None:
            entry["missing"].append("incident_date")
        out.append(entry)
    return out


# -- aggregates ----------------------------------------------------------------


def _capped_ids(ids: list[str], limit: int) -> tuple[list[str], bool]:
    if len(ids) > limit:
        return ids[:limit], True
    return ids, False


def aggregate_facts(
    facts: list[TransactionFact], *, max_supporting_ids: int = 100
) -> dict[str, Any]:
    """Exact ``Decimal`` aggregates over transaction facts.

    Every total is reported twice — ``total_records`` (every record carrying an
    amount, duplicates included) and ``total_distinct`` (grouped by the
    documented ``dedupe_key``) — because repeated records cannot be told apart
    from genuinely repeated transfers without a transaction reference. Both
    numbers carry their exact supporting source-record ids.
    """
    transactions = [f for f in facts if f.fact_class == "transaction"]
    with_amount = [f for f in transactions if f.amount is not None]

    counts = {
        "facts_total": len(facts),
        "fact_class_transaction": len(transactions),
        "fact_class_account_reference": len(facts) - len(transactions),
        "transaction_with_amount": len(with_amount),
        "transaction_without_amount": len(transactions) - len(with_amount),
        "with_currency": sum(1 for f in with_amount if f.currency is not None),
        "without_currency": sum(1 for f in with_amount if f.currency is None),
        "with_timestamp": sum(1 for f in with_amount if f.occurred_at is not None),
        "without_timestamp": sum(1 for f in with_amount if f.occurred_at is None),
        "with_txn_ref": sum(1 for f in transactions if f.txn_ref_normalized),
        "without_txn_ref": sum(1 for f in transactions if not f.txn_ref_normalized),
    }

    buckets: dict[str | None, list[TransactionFact]] = {}
    for fact in with_amount:
        buckets.setdefault(fact.currency, []).append(fact)

    currency_buckets: list[dict[str, Any]] = []
    for currency in sorted(buckets, key=lambda c: (c is None, c or "")):
        group = buckets[currency]
        amounts = [f.amount for f in group if f.amount is not None]
        if not amounts:
            continue
        total_records = sum(amounts, Decimal("0"))
        grouped: dict[str, list[Decimal]] = {}
        for fact in group:
            if fact.amount is None:
                continue
            grouped.setdefault(fact.dedupe_key, []).append(fact.amount)
        # One contribution per distinct transaction group (that is what makes
        # this number differ from ``total_records`` when a transfer is recorded
        # twice). A group whose records disagree on the amount cannot be
        # resolved deterministically, so it is excluded and reported rather
        # than silently picking one of the values.
        distinct_total = Decimal("0")
        conflicting: list[dict[str, Any]] = []
        for key in sorted(grouped):
            values = grouped[key]
            distinct_values = set(values)
            if len(distinct_values) > 1:
                conflicting.append(
                    {
                        "key": key,
                        "amounts": sorted(str(v) for v in distinct_values),
                    }
                )
                continue
            distinct_total += values[0]
        # If every group's records disagree on the amount there is no
        # defensible distinct total. Reporting "0" would read as a real figure,
        # so it is null instead and the conflicts are listed beside it.
        total_distinct_out: str | None = (
            None if (conflicting and distinct_total == 0) else str(distinct_total)
        )
        ids, ids_capped = _capped_ids([f.source_record_id for f in group], max_supporting_ids)
        currency_buckets.append(
            {
                "currency": currency,
                "currency_unknown": currency is None,
                "count": len(group),
                "distinct_groups": len(grouped),
                "conflicting_groups": conflicting,
                "distinct_amounts": len({str(a) for a in amounts}),
                "min": str(min(amounts)),
                "max": str(max(amounts)),
                # naive: every record summed, duplicates included
                "total_records": str(total_records),
                # grouped: one contribution per distinct transaction group
                "total_distinct": total_distinct_out,
                "total_distinct_conflicts_excluded": len(conflicting),
                "dedupe_key_definition": (
                    "normalized transaction reference when present, else "
                    "(exact amount, normalized account)"
                ),
                "dedupe_caveat": (
                    "records without a transaction reference cannot be told apart "
                    "from genuinely repeated transfers; both totals are reported "
                    "and neither is presented as the unique truth"
                ),
                "supporting_source_record_ids": ids,
                "supporting_ids_capped": ids_capped,
            }
        )

    def _grouped(field: str) -> list[dict[str, Any]]:
        groups: dict[str, list[TransactionFact]] = {}
        for fact in with_amount:
            value = getattr(fact, field)
            if not value:
                continue
            groups.setdefault(str(value), []).append(fact)
        out: list[dict[str, Any]] = []
        for name in sorted(groups):
            group = groups[name]
            amounts = [f.amount for f in group if f.amount is not None]
            ids, capped = _capped_ids([f.source_record_id for f in group], max_supporting_ids)
            out.append(
                {
                    field: name,
                    "count": len(group),
                    "total_records": str(sum(amounts, Decimal("0"))),
                    "supporting_source_record_ids": ids,
                    "supporting_ids_capped": capped,
                }
            )
        return out

    return {
        "counts": counts,
        "currency_buckets": currency_buckets,
        "by_account": _grouped("account_normalized"),
        "by_bank": _grouped("bank"),
        "by_merchant": _grouped("merchant"),
        "not_computable": {
            "inflow": "not_computable_no_direction",
            "outflow": "not_computable_no_direction",
            "net": "not_computable_no_direction",
            "reason": (
                "no payer-side key exists in any ingested record and "
                "relationships contains no transfer edge type, so no movement "
                "has a direction; these are reported as absent, never as zero"
            ),
        },
    }


# -- structure network ---------------------------------------------------------


def build_structure_network(
    facts: list[TransactionFact],
    owns_edges: list[dict[str, Any]],
    *,
    max_edges: int = 500,
) -> dict[str, Any]:
    """Bounded association network derived from co-occurrence and ``owns``.

    Every edge is typed: ``association`` (derived from documented
    co-occurrence, always ``suspected``) or ``relationship`` (an edge the
    schema actually asserts, e.g. ``owns``). No edge is ever typed
    ``transfer`` — see ``confirmed_transfer_edges``.
    """
    nodes: dict[str, dict[str, Any]] = {}

    def node(kind: str, value: str, label: str, origin: str) -> str:
        key = f"{kind}:{_normalize_label(value) if kind != 'account' else normalize_ref(value)}"
        if key not in nodes:
            nodes[key] = {"id": key, "kind": kind, "label": label, "origin": origin}
        return key

    edge_ids: dict[tuple[str, str], dict[str, Any]] = {}

    def add_edge(a: str, b: str, *, edge_kind: str, derivation: str, record_id: str | None,
                 relationship_type: str | None = None, confidence: float | None = None) -> None:
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        entry = edge_ids.get(key)
        if entry is None:
            if len(edge_ids) >= max_edges:
                return
            entry = {
                "source": a,
                "target": b,
                "edge_kind": edge_kind,
                "confidence": "suspected" if edge_kind == "association" else "schema_recorded",
                "derivation": derivation,
                "relationship_type": relationship_type,
                "schema_confidence": confidence,
                "supporting_source_record_ids": [],
            }
            edge_ids[key] = entry
        if record_id is not None and record_id not in entry["supporting_source_record_ids"]:
            if len(entry["supporting_source_record_ids"]) < 100:
                entry["supporting_source_record_ids"].append(record_id)

    for fact in facts:
        present: list[str] = []
        if fact.account_normalized:
            present.append(
                node("account", fact.account_normalized, fact.account_original or "", "record")
            )
        if fact.bank:
            present.append(node("bank", fact.bank, fact.bank, "record"))
        if fact.merchant:
            present.append(node("merchant", fact.merchant, fact.merchant, "record"))
        if fact.receiver:
            present.append(node("beneficiary", fact.receiver, fact.receiver, "record"))
        if fact.party:
            present.append(node("party", fact.party, fact.party, "record"))
        if len(present) < 2:
            continue
        # Star from the account when one exists (each edge then reads "this
        # counterparty is documented with this account"); otherwise pair all.
        if fact.account_normalized and len(present) > 1:
            hub = present[0]
            for other in present[1:]:
                add_edge(hub, other, edge_kind="association", derivation="account_star",
                         record_id=fact.source_record_id)
        else:
            for i, left in enumerate(present):
                for right in present[i + 1 :]:
                    add_edge(left, right, edge_kind="association", derivation="co_occurrence",
                             record_id=fact.source_record_id)

    for edge in owns_edges:
        src_kind = "person" if edge["source_type"] == "person" else edge["source_type"]
        tgt_kind = "person" if edge["target_type"] == "person" else edge["target_type"]
        src = node(src_kind, edge["source_value"], edge["source_value"], "entity")
        tgt = node(tgt_kind, edge["target_value"], edge["target_value"], "entity")
        add_edge(
            src,
            tgt,
            edge_kind="relationship",
            derivation="schema_relationship",
            record_id=edge.get("source_record_id"),
            relationship_type=edge.get("relationship_type"),
            confidence=edge.get("confidence"),
        )

    return {
        "nodes": list(nodes.values()),
        "edges": list(edge_ids.values()),
        "nodes_total": len(nodes),
        "edges_total": len(edge_ids),
        "edges_bounded": len(edge_ids) >= max_edges,
        "max_edges": max_edges,
        "confirmed_transfer_edges": 0,
        "transfer_edge_note": (
            "no ingested record states a two-sided money movement and "
            "relationships has no transfer edge type, so no edge is a "
            "confirmed transfer; association edges are candidates for review"
        ),
        "account_node_linkage": (
            "fact-derived and entity-derived account nodes share one documented "
            "normalization; a mismatch yields two nodes rather than an assumed merge"
        ),
    }


# -- pattern rules -------------------------------------------------------------

# Rules whose input the ingest genuinely does not carry. They are declared and
# returned on every run so a limitation is visible instead of the rule quietly
# disappearing. ``reason`` values are drawn from the documented missing-input
# vocabulary: missing_timestamp | missing_direction | no_transfer_edges.
NOT_EVALUABLE_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "rapid_succession",
        "missing_timestamp",
        "requires several movements from one source inside a rolling time window; "
        "no ingested record carries a transaction timestamp",
    ),
    (
        "repeated_pair",
        "missing_direction",
        "requires an ordered account pair (payer -> payee); no record states a direction",
    ),
    (
        "circular_path",
        "no_transfer_edges",
        "requires a cycle of confirmed transfers; no transfer edge exists to traverse",
    ),
    (
        "amount_splitting",
        "missing_direction",
        "requires one source splitting identical amounts to several destinations "
        "inside a window; neither direction nor timestamps exist",
    ),
    (
        "concentration",
        "missing_direction",
        "requires counting distinct counterparties sending to or receiving from one "
        "account; direction is absent",
    ),
)


def evaluate_patterns(
    facts: list[TransactionFact],
    victim_financials: list[dict[str, Any]],
    *,
    amount_threshold: Decimal,
) -> dict[str, Any]:
    """Evaluate every declared rule: ``firing``, ``not_fired`` or ``not_evaluable``.

    A firing rule carries exact evidence and its exact supporting source-record
    ids. A rule that could not be evaluated is returned with the specific
    missing input — never dropped, and never fired on data that is absent.
    """
    transactions = [f for f in facts if f.fact_class == "transaction"]
    with_amount = [f for f in transactions if f.amount is not None]
    firing: list[dict[str, Any]] = []
    not_fired: list[str] = []

    # duplicate_amount: the same exact amount in >= 2 distinct source records.
    by_amount: dict[str, list[TransactionFact]] = {}
    for fact in with_amount:
        by_amount.setdefault(str(fact.amount), []).append(fact)
    dupes = {k: v for k, v in by_amount.items() if len(v) >= 2}
    if dupes:
        for amount_text in sorted(dupes):
            group = dupes[amount_text]
            firing.append(
                {
                    "rule": "duplicate_amount",
                    "version": FLOW_PATTERN_RULES_VERSION,
                    "status": "firing",
                    "evidence": {
                        "amount": amount_text,
                        "record_count": len(group),
                        "distinct_dedupe_keys": len({f.dedupe_key for f in group}),
                    },
                    "supporting_source_record_ids": [f.source_record_id for f in group],
                    "limitations": ["currency_unknown" if group[0].currency is None else "none"],
                    "review_status": "pending_review",
                    "pattern_not_intent": True,
                }
            )
    else:
        not_fired.append("duplicate_amount")

    # amount_threshold: investigation default, not a universality claim.
    over = [f for f in with_amount if f.amount is not None and f.amount >= amount_threshold]
    if over:
        firing.append(
            {
                "rule": "amount_threshold",
                "version": FLOW_PATTERN_RULES_VERSION,
                "status": "firing",
                "evidence": {
                    "threshold": str(amount_threshold),
                    "threshold_semantics": (
                        "investigation default constant, not a regulatory or universal limit"
                    ),
                    "matched_count": len(over),
                    "amounts": sorted({str(f.amount) for f in over}),
                },
                "supporting_source_record_ids": [f.source_record_id for f in over],
                "limitations": [
                    "currency_unknown" if all(f.currency is None for f in over) else "none"
                ],
                "review_status": "pending_review",
                "pattern_not_intent": True,
            }
        )
    else:
        not_fired.append("amount_threshold")

    # missing_currency / missing_timestamp: coverage rules over the facts.
    no_currency = [f for f in with_amount if f.currency is None]
    if no_currency:
        firing.append(
            {
                "rule": "missing_currency",
                "version": FLOW_PATTERN_RULES_VERSION,
                "status": "firing",
                "evidence": {"matched_count": len(no_currency)},
                "supporting_source_record_ids": [f.source_record_id for f in no_currency],
                "limitations": ["currency_unknown"],
                "review_status": "pending_review",
                "pattern_not_intent": True,
            }
        )
    else:
        not_fired.append("missing_currency")

    no_time = [f for f in with_amount if f.occurred_at is None]
    if no_time:
        firing.append(
            {
                "rule": "missing_timestamp",
                "version": FLOW_PATTERN_RULES_VERSION,
                "status": "firing",
                "evidence": {"matched_count": len(no_time)},
                "supporting_source_record_ids": [f.source_record_id for f in no_time],
                "limitations": ["missing_timestamp"],
                "review_status": "pending_review",
                "pattern_not_intent": True,
            }
        )
    else:
        not_fired.append("missing_timestamp")

    # victim_loss_unmatched: a victim loss total with no transaction-level fact
    # of the same exact amount. The matching rule is stated in the evidence —
    # there is no victim<->record foreign key to join on.
    transaction_amounts = {str(f.amount) for f in with_amount}
    victim_unmatched_fired = False
    for victim in victim_financials:
        reported = victim.get("reported_amount")
        if reported is None:
            reported = victim.get("amount_lost")
        if reported is None or reported in transaction_amounts:
            continue
        victim_unmatched_fired = True
        firing.append(
            {
                "rule": "victim_loss_unmatched",
                "version": FLOW_PATTERN_RULES_VERSION,
                "status": "firing",
                "evidence": {
                    "victim_id": victim["victim_id"],
                    "amount": reported,
                    "currency": victim.get("currency"),
                    "incident_date": victim.get("incident_date"),
                    "match_rule": (
                        "exact Decimal equality against a transaction fact amount; "
                        "no victim-to-record foreign key exists, so this is the only "
                        "deterministic link available"
                    ),
                    "transaction_amounts_in_case": sorted(transaction_amounts),
                },
                "supporting_source_record_ids": [],
                "supporting_victim_ids": [victim["victim_id"]],
                "limitations": ["no_transaction_level_match", "float_source"],
                "review_status": "pending_review",
                "pattern_not_intent": True,
            }
        )
    if not victim_unmatched_fired:
        not_fired.append("victim_loss_unmatched")

    not_evaluable = [
        {
            "rule": rule,
            "version": FLOW_PATTERN_RULES_VERSION,
            "status": "not_evaluable",
            "reason": reason,
            "explanation": explanation,
        }
        for rule, reason, explanation in NOT_EVALUABLE_RULES
    ]

    return {
        "firing": firing,
        "not_fired": sorted(set(not_fired)),
        "not_evaluable": not_evaluable,
        "rule_count": len(NOT_EVALUABLE_RULES) + 5,
        "rules_version": FLOW_PATTERN_RULES_VERSION,
    }


# -- payload -------------------------------------------------------------------


def build_payload(
    *,
    case_id: uuid.UUID,
    facts: list[TransactionFact],
    victim_financials: list[dict[str, Any]],
    aggregates: dict[str, Any],
    network: dict[str, Any],
    patterns: dict[str, Any],
    warnings: dict[str, int],
    scope: dict[str, Any],
    max_facts: int,
) -> dict[str, Any]:
    """Assemble the deterministic artifact payload with full disclosure."""
    bounded = len(facts) > max_facts
    kept = facts[:max_facts]

    limitations = [
        "no transactions table exists; every fact is a deterministic extraction "
        "from source_records.raw_data and coverage equals ingestion coverage",
        "no payer/sender key occurs in any record, so direction-dependent "
        "metrics (inflow/outflow/net) are reported not_computable_no_direction",
        "relationships contains no transfer edge type, so confirmed_transfer_edges "
        "is 0 and every structure edge is an association or a recorded relationship",
        "record-level amounts carry no currency attribution; totals are bucketed "
        "under currency=null flagged currency_unknown and never labelled with a "
        "default currency",
        "no ingested record carries a transaction timestamp, so time-windowed "
        "pattern rules are returned not_evaluable(missing_timestamp)",
        "pattern candidates are descriptive observations for human review; a "
        "pattern is never evidence of intent",
    ]
    if any("float_source" in f.limitations for f in facts) or any(
        "float_source" in v.get("limitations", []) for v in victim_financials
    ):
        limitations.append(
            "some amounts originate in double precision columns and carry "
            "precision=float_source; exact-Decimal guarantees apply only to "
            "string/int-sourced amounts"
        )

    return {
        "flow_rules_version": FLOW_RULES_VERSION,
        "pattern_rules_version": FLOW_PATTERN_RULES_VERSION,
        "case_id": str(case_id),
        "scope": scope,
        "facts": [f.to_payload() for f in kept],
        "facts_bounded": bounded,
        "facts_total": len(facts),
        "victim_financials": victim_financials,
        "aggregates": aggregates,
        "structure_network": network,
        "patterns": patterns,
        "extraction_warnings": warnings,
        "limitations": limitations,
        "calculation_definitions": {
            "fact": (
                "one deterministic extraction from one source record's raw_data; "
                "fact_class=transaction when an amount or transaction reference is "
                "present, otherwise account_reference"
            ),
            "amount": (
                "parsed with Decimal from the original value (JSON strings parse "
                "exactly); originals are preserved verbatim alongside; non-numeric "
                "values are rejected and counted, never coerced"
            ),
            "total_records": (
                "sum of exact Decimal amounts over every record carrying an amount, "
                "duplicates included"
            ),
            "total_distinct": (
                "one contribution per distinct transaction group (grouped by the "
                "documented dedupe key: transaction reference, else amount+account), "
                "so a transfer recorded twice counts once; groups whose records "
                "disagree on the amount are excluded and listed in "
                "conflicting_groups. Records without a transaction reference cannot "
                "be told apart from genuinely repeated transfers, so both totals "
                "are always reported together and neither is the unique truth. "
                "When every group disagrees it is null, because a zero there would "
                "be a fabricated figure"
            ),
            "currency_bucketing": (
                "amounts are summed only within one currency value; records without "
                "a currency fall into a null bucket flagged currency_unknown"
            ),
            "net_flow": "not computed: direction is absent from the ingest",
            "structure_edge": (
                "association edges are documented co-occurrence within one record "
                "(star from the account when present); relationship edges are "
                "schema-asserted (e.g. owns). No edge is a confirmed transfer"
            ),
            "pattern": (
                "deterministic rule over the extracted facts; status is firing "
                "(with exact evidence), not_fired (evaluated, no evidence) or "
                "not_evaluable (a documented input is missing)"
            ),
        },
    }


# -- job lifecycle -------------------------------------------------------------


async def _load_records(
    session: AsyncSession, case_id: uuid.UUID, limit: int
) -> tuple[list[SourceRecord], bool]:
    """Case-scoped source records in stable order, plus a bounded flag.

    The join to ``evidence_files`` is what enforces case scope; the extra row
    fetched beyond ``limit`` is how we know the scan was truncated (reported,
    never hidden).
    """
    result = await session.execute(
        select(SourceRecord)
        .join(EvidenceFile, SourceRecord.evidence_file_id == EvidenceFile.id)
        .where(EvidenceFile.case_id == str(case_id))
        .order_by(EvidenceFile.created_at, EvidenceFile.id, SourceRecord.record_no)
        .limit(limit + 1)
    )
    rows = list(result.scalars())
    bounded = len(rows) > limit
    return rows[:limit], bounded


async def _load_victims(session: AsyncSession, case_id: uuid.UUID) -> list[Victim]:
    result = await session.execute(select(Victim).where(Victim.case_id == str(case_id)))
    return list(result.scalars())


async def _load_owns_edges(session: AsyncSession, case_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        select(Relationship)
        .where(
            Relationship.case_id == str(case_id),
            Relationship.relationship_type == "owns",
        )
        .limit(1000)
    )
    rels = list(result.scalars())
    if not rels:
        return []
    entity_ids = {str(r.source_entity_id) for r in rels} | {str(r.target_entity_id) for r in rels}
    entities = list(
        (await session.execute(select(Entity).where(Entity.id.in_(list(entity_ids))))).scalars()
    )
    by_id = {str(e.id): e for e in entities}
    edges: list[dict[str, Any]] = []
    for rel in rels:
        source = by_id.get(str(rel.source_entity_id))
        target = by_id.get(str(rel.target_entity_id))
        if source is None or target is None:
            continue
        edges.append(
            {
                "source_type": source.entity_type,
                "source_value": source.canonical_value,
                "target_type": target.entity_type,
                "target_value": target.canonical_value,
                "relationship_type": rel.relationship_type,
                "confidence": rel.confidence,
                "source_record_id": str(rel.source_record_id) if rel.source_record_id else None,
            }
        )
    return edges


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """Cooperative stop: cancel wins over timeout; never reports success."""
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "flow.canceled"
    else:
        job.error = f"financial flow analysis timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "flow.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"records_scanned": summary.get("records_scanned", 0)} if summary else {},
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
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action="flow.denied" if denial else "flow.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


async def execute_financial_flow(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Run one pending financial-flow job to a terminal state.

    Authorization is proven before any record is read and re-checked between
    bounded stages, so evidence whose access was revoked mid-run stops being
    read. Analysis is deterministic; a no-data case still succeeds with an
    explicit empty result rather than a failure.
    """
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    if actor_id is None:
        await _fail_job(
            session, job, code="FLOW_FAILED", error="job has no actor reference", stage="authorize"
        )
        return
    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CASE_ACCESS_DENIED,
            error="access to this case was revoked before financial flow analysis ran",
            denial=True,
            stage="authorize",
        )
        return
    if job.cancel_requested:
        await _stop_job(
            session, job, stop="cancel", summary={}, case_id=case_id, actor_id=actor_id
        )
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "records_scanned": 0,
        "records_bounded": False,
        "facts_extracted": 0,
        "facts_transaction": 0,
        "facts_account_reference": 0,
        "victim_rows_scanned": 0,
        "currency_buckets": 0,
        "network_nodes": 0,
        "network_edges": 0,
        "patterns_firing": 0,
        "patterns_not_evaluable": 0,
        "patterns_not_fired": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
    }
    stage = "load"

    async def check_stop() -> bool:
        """Cooperative stop + fresh authorization between bounded stages."""
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop_job(
                session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
            )
            return True
        if not await still_authorized_for_case(
            session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_READ
        ):
            await _fail_job(
                session,
                job,
                code=CODE_CASE_ACCESS_DENIED,
                error="access to this case was revoked mid-run; financial flow analysis stopped",
                denial=True,
                summary=summary,
                stage=stage,
            )
            return True
        return False

    try:
        stage = "load-records"
        rows, bounded = await _load_records(session, case_id, settings.FLOW_MAX_RECORDS)
        summary["records_scanned"] = len(rows)
        summary["records_bounded"] = bounded
        victims = await _load_victims(session, case_id)
        summary["victim_rows_scanned"] = len(victims)
        if await check_stop():
            return

        stage = "extract"
        facts, warnings = extract_facts(rows)
        summary["facts_extracted"] = len(facts)
        summary["facts_transaction"] = sum(1 for f in facts if f.fact_class == "transaction")
        summary["facts_account_reference"] = (
            len(facts) - summary["facts_transaction"]
        )
        victim_financials = extract_victim_financials(victims)
        if await check_stop():
            return

        stage = "analyze"
        aggregates = aggregate_facts(facts, max_supporting_ids=settings.FLOW_MAX_SUPPORTING_IDS)
        owns_edges = await _load_owns_edges(session, case_id)
        network = build_structure_network(facts, owns_edges, max_edges=settings.FLOW_MAX_EDGES)
        patterns = evaluate_patterns(
            facts,
            victim_financials,
            amount_threshold=Decimal(settings.FLOW_AMOUNT_THRESHOLD),
        )
        summary["currency_buckets"] = len(aggregates["currency_buckets"])
        summary["network_nodes"] = network["nodes_total"]
        summary["network_edges"] = network["edges_total"]
        summary["patterns_firing"] = len(patterns["firing"])
        summary["patterns_not_evaluable"] = len(patterns["not_evaluable"])
        summary["patterns_not_fired"] = len(patterns["not_fired"])
        if await check_stop():
            return

        stage = "record"
        payload = build_payload(
            case_id=case_id,
            facts=facts,
            victim_financials=victim_financials,
            aggregates=aggregates,
            network=network,
            patterns=patterns,
            warnings=warnings,
            scope={
                "records_scanned": summary["records_scanned"],
                "records_bounded": summary["records_bounded"],
                "victim_rows_scanned": summary["victim_rows_scanned"],
                "owns_edges_scanned": len(owns_edges),
                "flow_max_records": settings.FLOW_MAX_RECORDS,
            },
            max_facts=settings.FLOW_MAX_FACTS,
        )
        artifact, created = await record_artifact(
            session,
            case_id=case_id,
            kind=FLOW_ARTIFACT_KIND,
            origin="deterministic",
            payload=payload,
            parser_version=FLOW_RULES_VERSION,
            analysis_job_id=job.id,
            created_by=actor_id,
            status="pending_review",
        )
        summary["artifacts_created" if created else "artifacts_reused"] += 1
        summary["artifact_id"] = str(artifact.id)

        job.result_summary = summary
        jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="flow.analysis_completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata={
                "records_scanned": summary["records_scanned"],
                "facts_extracted": summary["facts_extracted"],
                "patterns_firing": summary["patterns_firing"],
                "patterns_not_evaluable": summary["patterns_not_evaluable"],
            },
        )
        await session.commit()
    except Exception:
        logger.exception("financial flow job crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code="FLOW_FAILED",
            error=f"unexpected error during stage {stage}",
            summary=summary,
            stage=stage,
        )


async def run_financial_flow_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    try:
        async with factory() as session:
            await execute_financial_flow(session, job_id=job_id, settings=settings)
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background financial flow failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code="FLOW_FAILED",
                    error="background financial flow task crashed",
                )


__all__ = [
    "FLOW_ARTIFACT_KIND",
    "FLOW_PATTERN_RULES_VERSION",
    "FLOW_RULES_VERSION",
    "aggregate_facts",
    "build_payload",
    "build_structure_network",
    "classify_status",
    "evaluate_patterns",
    "execute_financial_flow",
    "extract_fact",
    "extract_facts",
    "extract_victim_financials",
    "normalize_ref",
    "parse_amount",
    "run_financial_flow_job",
]

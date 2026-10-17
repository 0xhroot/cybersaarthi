"""On-demand AI explanations for Phase 4 findings (financial + cross-case).

The deterministic services decide; these resolvers only *narrate* already-recorded,
authorized facts - the model is never consulted during the deterministic run and
never sees SQL, the graph or the filesystem. Every explanation is validated
server-side before it can be stored:

- the reply must match a strict schema (unknown keys or type errors reject it);
- every cited identifier must exist on the parent artifact's own provenance
  (financial: the recorded transaction refs / record numbers; cross-case: the
  shared values and provenance ids across both sides);
- for financial findings, every quoted number (2+ digits) must appear verbatim
  in the supplied facts, so an invented amount can never survive.

A reply that fails any check is **dropped** and the failure surfaced to the
caller (``ExplanationOutcome`` with ``status="invalid"`` and the issues) - a
false result is never asserted. On success the explanation is stored as a child
artifact (``origin="llm"``, ``validation_status="flagged"``, flagged
``ai_unverified``, ``parent_artifact_id`` set) exactly like Phase 3's custody
explanations; the parent deterministic artifact is never modified.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    CROSSCASE_EXPLAIN_PROMPT_VERSION,
    FINANCIAL_EXPLAIN_PROMPT_VERSION,
)
from app.models import DerivedArtifact
from app.services import artifacts as artifacts_svc
from app.services.structured_extraction import parse_structured

# Number token: digit runs of 2+ digits (single-digit step counters are skipped).
_NUMBER_RE = re.compile(r"\d{2,}")


class _FinancialExplanationSchema(BaseModel):
    """Strict reply schema: extra keys reject the reply."""

    summary: str = Field(min_length=1, max_length=2000)
    why_patterns_fired: list[str] = Field(default_factory=list)
    cited_transaction_ids: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(min_length=1)


class _CrossCaseExplanationSchema(BaseModel):
    """Strict reply schema: extra keys reject the reply."""

    summary: str = Field(min_length=1, max_length=2000)
    matching_signal: str = Field(min_length=1, max_length=1200)
    cited_identifiers: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    not_established: list[str] = Field(min_length=1)
    verification_steps: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class ExplanationOutcome:
    """Result of one explain attempt (``artifact`` is None unless recorded)."""

    status: str  # "recorded" | "invalid"
    artifact: DerivedArtifact | None = None
    issues: tuple[dict[str, Any], ...] = ()


# -- authorized facts (only what the deterministic result already recorded) -----


def financial_explain_facts(payload: dict[str, Any]) -> dict[str, Any]:
    """Trimmed, authorized facts for the financial explainer.

    Only the deterministic result's own recorded values are sent; nothing is
    recomputed, converted or added.
    """
    return {
        "case_id": payload.get("case_id"),
        "facts": payload.get("facts", []),
        "patterns": payload.get("patterns", {}),
        "aggregates": payload.get("aggregates", {}),
        "limitations": payload.get("limitations", []),
    }


def crosscase_explain_facts(payload: dict[str, Any]) -> dict[str, Any]:
    """Trimmed, authorized facts for the cross-case explainer (both sides)."""
    group = payload.get("group")
    group = group if isinstance(group, dict) else {}
    sides: list[dict[str, Any]] = []
    for side in payload.get("sides", []):
        if not isinstance(side, dict):
            continue
        sides.append(
            {
                "case_id": side.get("case_id"),
                "value_originals": side.get("value_originals", []),
                "source_record_ids": side.get("source_record_ids", []),
                "entity_ids": side.get("entity_ids", []),
            }
        )
    return {
        "indicator_kind": group.get("indicator_kind"),
        "value_normalized": group.get("value_normalized"),
        "classification": payload.get("classification"),
        "score_semantics": payload.get("score_semantics"),
        "sides": sides,
        "conflicting_attributes": payload.get("conflicting_attributes"),
        "limitations": payload.get("limitations", []),
    }


def _financial_allowed_ids(payload: dict[str, Any]) -> set[str]:
    """Every transaction ref / record number present in the deterministic result."""
    allowed: set[str] = set()
    for fact in payload.get("facts", []):
        if not isinstance(fact, dict):
            continue
        for key in ("record_no", "txn_ref_normalized", "txn_ref_original"):
            value = fact.get(key)
            if value is not None and str(value).strip():
                allowed.add(str(value))
    return allowed


def _crosscase_allowed_ids(payload: dict[str, Any]) -> set[str]:
    """Shared value plus every provenance id across both sides of a candidate."""
    allowed: set[str] = set()
    group = payload.get("group")
    group = group if isinstance(group, dict) else {}
    if group.get("value_normalized"):
        allowed.add(str(group["value_normalized"]))
    for side in payload.get("sides", []):
        if not isinstance(side, dict):
            continue
        for key in ("value_originals", "source_record_ids", "entity_ids"):
            for value in side.get(key) or []:
                if value and str(value).strip():
                    allowed.add(str(value))
    return allowed


# -- deterministic validation ---------------------------------------------------


def _missing_citations(cited: list[str], allowed: set[str]) -> list[str]:
    return [c for c in cited if c.strip() and c.strip() not in allowed]


def _fabricated_numbers(texts: list[str], facts_json: str) -> list[str]:
    """Number tokens (2+ digits) that do not appear verbatim in the facts."""
    fabricated: set[str] = set()
    for text in texts:
        for token in _NUMBER_RE.findall(text or ""):
            if token not in facts_json:
                fabricated.add(token)
    return sorted(fabricated)


def _validate_financial(
    explanation: dict[str, Any], payload: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, str]] = []
    allowed = _financial_allowed_ids(payload)
    bad = _missing_citations(list(explanation.get("cited_transaction_ids", [])), allowed)
    if bad:
        issues.append(
            {
                "field": "cited_transaction_ids",
                "code": "citation_not_in_facts",
                "message": f"cited ids are not present in the deterministic result: {bad}",
            }
        )
    facts_json = json.dumps(facts, sort_keys=True, ensure_ascii=False, default=str)
    fabricated = _fabricated_numbers(
        [str(explanation.get("summary", "")), *explanation.get("alternative_explanations", [])],
        facts_json,
    )
    if fabricated:
        issues.append(
            {
                "field": "summary",
                "code": "number_not_in_facts",
                "message": f"quoted numbers are not present verbatim in the facts: {fabricated}",
            }
        )
    return issues


def _validate_crosscase(
    explanation: dict[str, Any], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    allowed = _crosscase_allowed_ids(payload)
    bad = _missing_citations(list(explanation.get("cited_identifiers", [])), allowed)
    if bad:
        return [
            {
                "field": "cited_identifiers",
                "code": "citation_not_in_provenance",
                "message": f"cited identifiers are not on the candidate's provenance: {bad}",
            }
        ]
    return []


# -- storage (child artifact, parent untouched) ---------------------------------


async def _store_explanation(
    session: AsyncSession,
    *,
    parent: DerivedArtifact,
    explanation: dict[str, Any],
    prompt_version: str,
    actor_id: uuid.UUID,
) -> DerivedArtifact:
    artifact, _created = await artifacts_svc.record_artifact(
        session,
        case_id=uuid.UUID(str(parent.case_id)),
        kind=parent.kind,
        origin="llm",
        payload={
            "type": "ai_explanation",
            "explanation": explanation,
            "for_artifact_id": str(parent.id),
        },
        prompt_version=prompt_version,
        model_profile="explain",
        parent_artifact_id=parent.id,
        # Explanations are unverified AI interpretation: amber by design, never
        # a fabricated green "validated" badge, and never queued for approval.
        validation_status="flagged",
        validation_errors=[
            {
                "field": "explanation",
                "code": "ai_unverified",
                "message": (
                    "AI interpretation of recorded facts; deterministic rules and "
                    "human review decide outcomes"
                ),
            }
        ],
        status="recorded",
        created_by=actor_id,
    )
    return artifact


# -- resolvers (call the model, validate, store or drop) ------------------------


async def explain_financial_artifact(
    session: AsyncSession,
    *,
    artifact: DerivedArtifact,
    ai: Any,
    actor_id: uuid.UUID,
) -> ExplanationOutcome:
    """Explain one ``financial_finding`` artifact; validate then store a child."""
    payload = dict(artifact.payload or {})
    facts = financial_explain_facts(payload)
    completion = await ai.explain_financial_flow(summary=facts)
    result = parse_structured(completion.text, _FinancialExplanationSchema)
    if result.data is None:
        return ExplanationOutcome(
            "invalid", issues=tuple(issue.as_dict() for issue in result.issues)
        )
    explanation = result.data
    issues = _validate_financial(explanation, payload, facts)
    if issues:
        return ExplanationOutcome("invalid", issues=tuple(issues))
    child = await _store_explanation(
        session,
        parent=artifact,
        explanation=explanation,
        prompt_version=FINANCIAL_EXPLAIN_PROMPT_VERSION,
        actor_id=actor_id,
    )
    return ExplanationOutcome("recorded", artifact=child)


async def explain_cross_case_artifact(
    session: AsyncSession,
    *,
    artifact: DerivedArtifact,
    ai: Any,
    actor_id: uuid.UUID,
) -> ExplanationOutcome:
    """Explain one ``cross_case_link`` candidate; validate then store a child."""
    payload = dict(artifact.payload or {})
    facts = crosscase_explain_facts(payload)
    completion = await ai.explain_cross_case_candidate(candidate_facts=facts)
    result = parse_structured(completion.text, _CrossCaseExplanationSchema)
    if result.data is None:
        return ExplanationOutcome(
            "invalid", issues=tuple(issue.as_dict() for issue in result.issues)
        )
    explanation = result.data
    issues = _validate_crosscase(explanation, payload)
    if issues:
        return ExplanationOutcome("invalid", issues=tuple(issues))
    child = await _store_explanation(
        session,
        parent=artifact,
        explanation=explanation,
        prompt_version=CROSSCASE_EXPLAIN_PROMPT_VERSION,
        actor_id=actor_id,
    )
    return ExplanationOutcome("recorded", artifact=child)

"""Deterministic AIService stand-ins for phase-2/3 tests (no live LLM).

``FakeAI`` implements the bounded surfaces features 1, 9, A and C consume
(``extract_page`` / ``explain_integrity_finding`` / ``compare_entity_pair`` /
``compare_statements``) so API tests never depend on a llama.cpp runtime.
Replies are scripted per test; anything unconfigured returns an all-empty but
schema-valid extraction reply, a non-match pair verdict, or a non-contradicting
statement verdict.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.ai.client import CompletionResult

EXTRACTION_FIELDS: tuple[str, ...] = (
    "person_names",
    "organization_names",
    "phone_numbers",
    "email_addresses",
    "account_references",
    "transaction_amounts",
    "transaction_dates",
    "urls",
    "domains",
    "device_identifiers",
    "statements",
    "events",
)

MULTILINGUAL_FIELDS: tuple[str, ...] = (
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


def extraction_reply(**claims: list[str]) -> str:
    """Schema-valid JSON reply: empty claims by default, overridden per test."""
    payload: dict[str, list[str]] = {key: [] for key in EXTRACTION_FIELDS}
    unknown = set(claims) - set(payload)
    assert not unknown, f"unknown extraction fields in reply: {sorted(unknown)}"
    payload.update(claims)
    return json.dumps(payload)


def multilingual_reply(language: str = "english", **fields: list[str]) -> str:
    """Schema-valid multilingual analysis reply; empty fields by default."""
    payload: dict[str, Any] = {"language": language}
    for key in MULTILINGUAL_FIELDS:
        payload[key] = list(fields.get(key, []))
    unknown = set(fields) - set(MULTILINGUAL_FIELDS)
    assert not unknown, f"unknown multilingual fields: {sorted(unknown)}"
    return json.dumps(payload, ensure_ascii=False)


def triage_reply(
    summary: str = "deterministic fake: observations listed",
    **sections: list[str],
) -> str:
    payload = {
        "summary": summary,
        "explanations": list(sections.get("explanations", [])),
        "not_established": list(sections.get("not_established", [])),
        "verification_steps": list(sections.get("verification_steps", [])),
    }
    return json.dumps(payload, ensure_ascii=False)


def claims_reply(*claims: dict[str, Any]) -> str:
    return json.dumps({"claims": list(claims)})


def support_reply(
    assessment: str = "not_established",
    explanation: str = "the supplied sources do not establish the claim",
    quoted_spans: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "assessment": assessment,
            "explanation": explanation,
            "quoted_spans": list(quoted_spans or []),
        },
        ensure_ascii=False,
    )


class _FakeCompletionMixin:
    """Phase 5A/5B/6 scripted surfaces mixed into FakeAI (below)."""

    multilingual_replies: list[str]
    translate_replies: list[str]
    triage_explain_replies: list[str]
    claim_replies: list[str]
    support_replies: list[str]
    multilingual_calls: list[dict[str, str]]
    translate_calls: list[dict[str, str]]
    triage_explain_calls: list[dict[str, Any]]
    claim_calls: list[dict[str, Any]]
    support_calls: list[dict[str, Any]]
    error: Exception | None
    fail_after: int | None

    def _maybe_fail(self, calls: Sequence[object]) -> None:
        """Honor the shared scripted-error knobs (mirrors extract_page)."""
        if self.error is not None and (self.fail_after is None or len(calls) > self.fail_after):
            raise self.error

    async def analyze_complaint(self, *, label: str, text: str) -> CompletionResult:
        self.multilingual_calls.append({"label": label, "text": text})
        self._maybe_fail(self.multilingual_calls)
        reply = (
            self.multilingual_replies.pop(0)
            if self.multilingual_replies
            else (multilingual_reply())
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def translate_complaint(self, *, label: str, text: str) -> CompletionResult:
        self.translate_calls.append({"label": label, "text": text})
        self._maybe_fail(self.translate_calls)
        reply = (
            self.translate_replies.pop(0)
            if self.translate_replies
            else json.dumps(
                {
                    "translated_text": text,
                    "preserved_values": [],
                    "uncertain_terms": [],
                },
                ensure_ascii=False,
            )
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def explain_triage(self, *, observations: dict[str, Any]) -> CompletionResult:
        self.triage_explain_calls.append(dict(observations))
        self._maybe_fail(self.triage_explain_calls)
        reply = (
            self.triage_explain_replies.pop(0) if self.triage_explain_replies else triage_reply()
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def extract_report_claims(self, *, draft: str, max_claims: int) -> CompletionResult:
        self.claim_calls.append({"draft": draft, "max_claims": max_claims})
        self._maybe_fail(self.claim_calls)
        reply = self.claim_replies.pop(0) if self.claim_replies else claims_reply()
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def assess_claim_support(self, *, claim: str, sources: str) -> CompletionResult:
        self.support_calls.append({"claim": claim, "sources": sources})
        self._maybe_fail(self.support_calls)
        reply = self.support_replies.pop(0) if self.support_replies else support_reply()
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)


class FakeAI(_FakeCompletionMixin):
    """Scripted PageExtractor + integrity-explanation surface.

    - ``replies``: extraction replies consumed in order; when exhausted (or
      never configured) every call receives an empty-but-valid reply.
    - ``error``/``fail_after``: simulate an AI-layer outage after N successes.
    - ``explain_text``: fixed narration returned by the explain endpoint.
    """

    def __init__(
        self,
        replies: list[str] | None = None,
        *,
        error: Exception | None = None,
        fail_after: int | None = None,
        explain_text: str = (
            "Rule custody.unacknowledged_transfer was recorded by the "
            "deterministic rule engine from the listed facts; this model "
            "verified no files and cannot certify the chain of custody."
        ),
    ) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.fail_after = fail_after
        self.explain_text = explain_text
        self.extract_calls: list[dict[str, str]] = []
        self.explain_calls: list[dict[str, Any]] = []
        self.pair_replies: list[str] = []
        self.statement_replies: list[str] = []
        self.pair_calls: list[dict[str, Any]] = []
        self.statement_calls: list[dict[str, Any]] = []
        self.flow_explain_replies: list[str] = []
        self.crosscase_explain_replies: list[str] = []
        self.flow_explain_calls: list[dict[str, Any]] = []
        self.crosscase_explain_calls: list[dict[str, Any]] = []
        self.multilingual_replies: list[str] = []
        self.translate_replies: list[str] = []
        self.triage_explain_replies: list[str] = []
        self.claim_replies: list[str] = []
        self.support_replies: list[str] = []
        self.multilingual_calls: list[dict[str, str]] = []
        self.translate_calls: list[dict[str, str]] = []
        self.triage_explain_calls: list[dict[str, Any]] = []
        self.claim_calls: list[dict[str, Any]] = []
        self.support_calls: list[dict[str, Any]] = []

    async def extract_page(self, *, label: str, text: str) -> CompletionResult:
        self.extract_calls.append({"label": label, "text": text})
        if self.error is not None and (
            self.fail_after is None or len(self.extract_calls) > self.fail_after
        ):
            raise self.error
        reply = self.replies.pop(0) if self.replies else extraction_reply()
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def explain_integrity_finding(self, *, finding: dict[str, Any]) -> str:
        self.explain_calls.append(dict(finding))
        return self.explain_text

    async def compare_entity_pair(
        self, *, entity_a: dict[str, Any], entity_b: dict[str, Any], features: dict[str, Any]
    ) -> CompletionResult:
        """Scripted advisory verdict for one phase-3 A comparison."""
        self.pair_calls.append(
            {"entity_a": dict(entity_a), "entity_b": dict(entity_b), "features": dict(features)}
        )
        reply = (
            self.pair_replies.pop(0)
            if self.pair_replies
            else json.dumps(
                {
                    "verdict": "unclear",
                    "reason": "deterministic fake: no scripted verdict",
                }
            )
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def compare_statements(self, *, first: str, second: str, anchor: str) -> CompletionResult:
        """Scripted advisory verdict for one phase-3 C comparison."""
        self.statement_calls.append({"first": first, "second": second, "anchor": anchor})
        reply = (
            self.statement_replies.pop(0)
            if self.statement_replies
            else json.dumps(
                {
                    "contradicts": False,
                    "explanation": "deterministic fake: no scripted verdict",
                }
            )
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def explain_financial_flow(self, *, summary: dict[str, Any]) -> CompletionResult:
        """Scripted phase-4 A explanation; the default cites a real fact."""
        self.flow_explain_calls.append(dict(summary))
        reply = (
            self.flow_explain_replies.pop(0)
            if self.flow_explain_replies
            else json.dumps(self._default_flow_explanation(summary))
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    async def explain_cross_case_candidate(
        self, *, candidate_facts: dict[str, Any]
    ) -> CompletionResult:
        """Scripted phase-4 B explanation; the default cites a real value."""
        self.crosscase_explain_calls.append(dict(candidate_facts))
        reply = (
            self.crosscase_explain_replies.pop(0)
            if self.crosscase_explain_replies
            else json.dumps(self._default_crosscase_explanation(candidate_facts))
        )
        return CompletionResult(text=reply, prompt_tokens=8, completion_tokens=8, duration_ms=1)

    @staticmethod
    def _default_flow_explanation(summary: dict[str, Any]) -> dict[str, Any]:
        facts = summary.get("facts") or []
        first = facts[0] if facts else {}
        cited = [str(first["record_no"])] if first.get("record_no") is not None else []
        amount = str(first["amount"]) if first.get("amount") is not None else ""
        return {
            "summary": f"observed flow of amount {amount}" if amount else "observed flow",
            "why_patterns_fired": ["deterministic fake: pattern fired on the listed facts"],
            "cited_transaction_ids": cited,
            "alternative_explanations": ["a legitimate business transfer"],
            "missing_information": ["currency"],
            "verification_steps": ["confirm the account holder"],
        }

    @staticmethod
    def _default_crosscase_explanation(candidate_facts: dict[str, Any]) -> dict[str, Any]:
        first_original = ""
        for side in candidate_facts.get("sides") or []:
            originals = side.get("value_originals") or []
            if originals:
                first_original = str(originals[0])
                break
        return {
            "summary": "these cases share an identifier",
            "matching_signal": "a shared identifier, not proof",
            "cited_identifiers": [first_original] if first_original else [],
            "conflicts": [],
            "not_established": ["that the cases are the same incident"],
            "verification_steps": ["verify the account holder"],
        }

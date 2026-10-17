"""Deterministic AIService stand-ins for phase-2 tests (no live LLM).

``FakeAI`` implements the two bounded surfaces features 1 and 9 consume
(``extract_page`` / ``explain_integrity_finding``) so API tests never depend
on a llama.cpp runtime. Replies are scripted per test; anything unconfigured
returns an all-empty but schema-valid extraction reply.
"""

from __future__ import annotations

import json
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


def extraction_reply(**claims: list[str]) -> str:
    """Schema-valid JSON reply: empty claims by default, overridden per test."""
    payload: dict[str, list[str]] = {key: [] for key in EXTRACTION_FIELDS}
    unknown = set(claims) - set(payload)
    assert not unknown, f"unknown extraction fields in reply: {sorted(unknown)}"
    payload.update(claims)
    return json.dumps(payload)


class FakeAI:
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

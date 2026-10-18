"""Parse AI-drafted hypothesis suggestions with fail-honest semantics.

The ``hypothesize`` prompt contract asks the model to emit each candidate as a
fenced ``hypothesis`` block containing strict JSON:

    ```hypothesis
    {"title": "...", "statement": "...", "evidence_ids": ["<uuid>", ...],
     "refutation": "...", "missing": "..."}
    ```

Parsing is deliberately dumb and total: a block that is not valid JSON with a
non-empty title and statement is *counted as an error and skipped* — never
repaired, never approximated. Drafts are proposals for human review only: this
module does not touch the database, and nothing here can create or confirm a
stored hypothesis or finding.
"""

from __future__ import annotations

import json
import re
from typing import Any

DRAFT_FENCE_RE = re.compile(r"```hypothesis\s*\n(.*?)\n\s*```", re.S)
UUID_BODY = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
DRAFT_UUID_RE = re.compile(rf"^{UUID_BODY}$", re.I)

# Hard caps: the prompt asks for up to three; the parser tolerates a few more
# but never lets model output grow without bound.
MAX_DRAFTS = 5
MAX_TITLE_CHARS = 255
MAX_STATEMENT_CHARS = 4_000
MAX_TEXT_FIELD_CHARS = 2_000


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:MAX_TEXT_FIELD_CHARS]
    return None


def parse_hypothesis_drafts(answer: str) -> tuple[list[dict[str, Any]], int]:
    """Extract validated drafts from a model answer.

    Returns ``(drafts, unparseable_blocks)``. Every draft dict carries
    ``title``, ``statement``, ``evidence_ids`` (UUID-shaped only, deduped, in
    order), ``refutation`` and ``missing`` (optional). ``unparseable_blocks``
    counts fenced blocks that failed validation or exceeded ``MAX_DRAFTS`` —
    surfaced to clients so a partial tray is never mistaken for the model's
    full output.
    """
    drafts: list[dict[str, Any]] = []
    unparseable = 0
    for match in DRAFT_FENCE_RE.finditer(answer):
        if len(drafts) >= MAX_DRAFTS:
            unparseable += 1
            continue
        try:
            obj = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            unparseable += 1
            continue
        if not isinstance(obj, dict):
            unparseable += 1
            continue
        title = obj.get("title")
        statement = obj.get("statement")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(statement, str)
            or not statement.strip()
        ):
            unparseable += 1
            continue
        raw_ids = obj.get("evidence_ids")
        evidence_ids: list[str] = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                if isinstance(item, str) and DRAFT_UUID_RE.match(item):
                    lowered = item.lower()
                    if lowered not in evidence_ids:
                        evidence_ids.append(lowered)
        drafts.append(
            {
                "title": title.strip()[:MAX_TITLE_CHARS],
                "statement": statement.strip()[:MAX_STATEMENT_CHARS],
                "evidence_ids": evidence_ids,
                "refutation": _optional_text(obj.get("refutation")),
                "missing": _optional_text(obj.get("missing")),
            }
        )
    return drafts, unparseable


def mark_unverified_ids(drafts: list[dict[str, Any]], known_ids: set[str]) -> None:
    """Flag each draft's evidence ids that were not in the retrieved data.

    ``known_ids`` is the machine-verified set (shown DATA + response sources);
    anything outside it is listed per draft so a reviewer sees exactly which
    citations retrieval could not confirm.
    """
    known = {k.lower() for k in known_ids}
    for draft in drafts:
        draft["unverified_ids"] = [
            eid for eid in draft.get("evidence_ids", []) if eid.lower() not in known
        ]

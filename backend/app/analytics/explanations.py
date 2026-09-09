"""Structured, traceable explanations for findings.

Every finding stores three things alongside its score and title:
  - the deterministic approach that produced it,
  - the raw signals that fired (measurement + description),
  - the supporting evidence (source records / relationships) so an analyst can
    walk from a conclusion straight back to the original material.
"""

from __future__ import annotations

from typing import Any


def build_explanation(
    *,
    approach: str,
    signals: list[dict[str, Any]],
    paths: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble an explainable, JSON-serialisable finding explanation."""
    return {
        "approach": approach,
        "signals": signals,
        "paths": paths or [],
        "evidence": evidence or [],
        "limitations": limitations or [],
    }


def evidence_from_source_records(
    source_record_ids: list[str],
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Map a deduplicated list of source-record ids to evidence entries."""
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for record_id in sorted(source_record_ids):
        if record_id in seen:
            continue
        seen.add(record_id)
        entries.append({"kind": "source_record", "id": record_id})
        if len(entries) >= limit:
            break
    return entries


def signature_limitation(message: str) -> str:
    return message

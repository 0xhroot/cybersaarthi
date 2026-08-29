"""Deterministic relationship extraction from resolved entity mentions.

* Structured records (CSV/JSON): typed field pairs within one record, e.g.
  person+phone -> CALLED, person+vehicle -> OWNS, person+organisation ->
  WORKS_FOR.
* Free-text records (TXT): mentions co-occurring in the same sentence window.

Only relationships whose endpoints resolved to entities are returned; review
candidates simply do not participate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import RelationshipType
from app.services.extraction import Mention, sentence_windows

# (source_type, target_type) -> relationship type. Matching is on the source
# entity first: person+phone yields person->phone :CALLED even if a phone
# appears earlier in the text.
TYPE_PAIR_RULES: dict[tuple[str, str], str] = {
    ("person", "phone"): RelationshipType.CALLED,
    ("phone", "person"): RelationshipType.CALLED,
    ("person", "vehicle"): RelationshipType.OWNS,
    ("vehicle", "person"): RelationshipType.OWNS,
    ("person", "account"): RelationshipType.OWNS,
    ("account", "person"): RelationshipType.OWNS,
    ("person", "organization"): RelationshipType.WORKS_FOR,
    ("organization", "person"): RelationshipType.WORKS_FOR,
    ("person", "person"): RelationshipType.ASSOCIATED_WITH,
    ("person", "location"): RelationshipType.LOCATED_AT,
    ("location", "person"): RelationshipType.LOCATED_AT,
    ("person", "event"): RelationshipType.ASSOCIATED_WITH,
    ("event", "person"): RelationshipType.ASSOCIATED_WITH,
    ("phone", "phone"): RelationshipType.CALLED,
    ("phone", "location"): RelationshipType.VISITED,
    ("location", "phone"): RelationshipType.VISITED,
    ("vehicle", "location"): RelationshipType.VISITED,
    ("location", "vehicle"): RelationshipType.VISITED,
    ("organization", "location"): RelationshipType.LOCATED_AT,
    ("location", "organization"): RelationshipType.LOCATED_AT,
    ("event", "location"): RelationshipType.VISITED,
    ("location", "event"): RelationshipType.VISITED,
    ("account", "account"): RelationshipType.TRANSFERRED_TO,
    ("organization", "organization"): RelationshipType.ASSOCIATED_WITH,
}

MAX_RELATIONSHIPS_PER_RECORD = 15

# Ordered deterministic pair iteration. When both directions are valid, the
# earlier mention in the text wins as source (deterministic ordering).
PAIR_PLAN: tuple[tuple[str, str], ...] = (
    ("person", "phone"),
    ("person", "vehicle"),
    ("person", "account"),
    ("person", "organization"),
    ("person", "location"),
    ("person", "event"),
    ("phone", "phone"),
    ("phone", "location"),
    ("vehicle", "location"),
    ("organization", "location"),
    ("event", "location"),
    ("account", "account"),
    ("organization", "organization"),
)


@dataclass(frozen=True)
class ExtractedRelationship:
    relationship_type: str
    source_key: tuple[str, str]
    target_key: tuple[str, str]
    context: dict[str, Any]
    explanation: str
    evidence_type: str
    snippet: str | None


def _pair_for(
    mention_a: Mention, mention_b: Mention
) -> tuple[tuple[str, str], tuple[str, str], str] | None:
    rule = TYPE_PAIR_RULES.get((mention_a.entity_type, mention_b.entity_type))
    if rule is not None:
        return (
            (mention_a.entity_type, mention_a.canonical),
            (mention_b.entity_type, mention_b.canonical),
            rule,
        )
    rule = TYPE_PAIR_RULES.get((mention_b.entity_type, mention_a.entity_type))
    if rule is not None:
        return (
            (mention_b.entity_type, mention_b.canonical),
            (mention_a.entity_type, mention_a.canonical),
            rule,
        )
    return None


def _canonical_endpoints(
    source_key: tuple[str, str], target_key: tuple[str, str]
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Deterministic logical orientation for an extracted relationship.

    Same-type pairs (person+person, phone+phone, account+account,
    organization+organization) are undirected, so ``(a, b)`` and ``(b, a)``
    are the same logical relationship. Sorting by canonical value collapses
    them no matter how the mentions appear in a record or sentence, which is
    what lets persistence deduplicate across evidence mechanisms. Cross-type
    pairs keep the rule-defined direction (e.g. person -> phone :CALLED).
    """
    if source_key[0] == target_key[0] and source_key > target_key:
        return target_key, source_key
    return source_key, target_key


def extract_relationships(
    mentions: list[Mention],
    resolved: dict[tuple[str, str], Any],
    *,
    is_structured: bool,
    text: str,
) -> list[ExtractedRelationship]:
    """Return relationships between *resolved* mentions only."""

    resolved_mentions = [
        mention for mention in mentions if (mention.entity_type, mention.canonical) in resolved
    ]
    relationships: list[ExtractedRelationship] = []

    if is_structured:
        used: set[tuple[tuple[str, str], tuple[str, str], str]] = set()
        for type_a, type_b in PAIR_PLAN:
            group_a = [m for m in resolved_mentions if m.entity_type == type_a]
            group_b = [m for m in resolved_mentions if m.entity_type == type_b]
            for mention_a in group_a:
                for mention_b in group_b:
                    pair = _pair_for(mention_a, mention_b)
                    if pair is None:
                        continue
                    source_key, target_key, rule = pair
                    if source_key == target_key:
                        continue
                    source_key, target_key = _canonical_endpoints(source_key, target_key)
                    used_key = (source_key, target_key, rule)
                    if used_key in used:
                        continue
                    used.add(used_key)
                    relationships.append(
                        ExtractedRelationship(
                            relationship_type=rule,
                            source_key=source_key,
                            target_key=target_key,
                            context={"evidence": "structured field pair", "count": 1},
                            explanation=f"structured field pair: {type_a} -> {type_b}",
                            evidence_type="field",
                            snippet=None,
                        )
                    )
                    if len(relationships) >= MAX_RELATIONSHIPS_PER_RECORD:
                        return relationships
        return relationships

    for window_start, window_end in sentence_windows(text):
        candidates = [
            m for m in resolved_mentions if window_start <= m.start <= m.end <= window_end
        ]
        if len(candidates) < 2:
            continue
        used_pairs: set[tuple[tuple[str, str], tuple[str, str], str]] = set()
        ordered = sorted(candidates, key=lambda m: (m.start, m.entity_type))
        snippet = text[window_start:window_end][:400]
        for i, mention_a in enumerate(ordered):
            for mention_b in ordered[i + 1 :]:
                pair = _pair_for(mention_a, mention_b)
                if pair is None:
                    continue
                source_key, target_key, rule = pair
                if source_key == target_key:
                    continue
                source_key, target_key = _canonical_endpoints(source_key, target_key)
                pair_key = (source_key, target_key, rule)
                if pair_key in used_pairs:
                    continue
                used_pairs.add(pair_key)
                relationships.append(
                    ExtractedRelationship(
                        relationship_type=rule,
                        source_key=source_key,
                        target_key=target_key,
                        context={
                            "evidence": "co-occurrence",
                            "window": f"{window_start}:{window_end}",
                        },
                        explanation=f"co-occurrence in sentence window {window_start}:{window_end}",
                        evidence_type="co_occurrence",
                        snippet=snippet,
                    )
                )
                if len(relationships) >= MAX_RELATIONSHIPS_PER_RECORD:
                    return relationships
    return relationships

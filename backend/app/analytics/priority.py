"""Investigation priority for a single entity.

Combines the entity's own network DNA (prominence, influence, bridging, reach)
with the analytical findings and missing-link hypotheses raised about it, then
maps to a priority tier.  Pure arithmetic over already-normalized inputs.

    priority = 0.25*prominence + 0.15*influence + 0.20*bridging
             + 0.10*reach + 0.15*pattern + 0.15*hypothesis
"""

from __future__ import annotations

from collections import Counter

PRIORITY_WEIGHTS = {
    "prominence": 0.25,
    "influence": 0.15,
    "bridging": 0.20,
    "reach": 0.10,
    "pattern": 0.15,
    "hypothesis": 0.15,
}

PRIORITY_TIERS = (("CRITICAL", 0.75), ("HIGH", 0.55), ("MEDIUM", 0.35))


def pattern_weight(severities: list[str]) -> float:
    """Findings about the entity boost priority — capped at 1.0."""
    counts = Counter(sev.lower() for sev in severities)
    weight = (
        0.5 * (counts["critical"] + counts["high"]) + 0.25 * counts["medium"] + 0.1 * counts["low"]
    )
    return min(1.0, weight)


def hypothesis_weight(count: int) -> float:
    return min(1.0, count * 0.4)


def compute_priority(
    *,
    prominence: float,
    influence: float,
    bridging: float,
    reach: float,
    finding_severities: list[str] | None = None,
    hypothesis_count: int = 0,
) -> tuple[float, str]:
    """Return (priority_score, tier). All inputs must already be in [0, 1]."""
    finding_severities = finding_severities or []
    score = (
        PRIORITY_WEIGHTS["prominence"] * min(1.0, prominence)
        + PRIORITY_WEIGHTS["influence"] * min(1.0, influence)
        + PRIORITY_WEIGHTS["bridging"] * min(1.0, bridging)
        + PRIORITY_WEIGHTS["reach"] * min(1.0, reach)
        + PRIORITY_WEIGHTS["pattern"] * pattern_weight(finding_severities)
        + PRIORITY_WEIGHTS["hypothesis"] * hypothesis_weight(hypothesis_count)
    )
    score = round(min(1.0, max(0.0, score)), 6)
    for tier, threshold in PRIORITY_TIERS:
        if score >= threshold:
            return score, tier
    return score, "LOW"

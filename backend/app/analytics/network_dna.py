"""Network DNA — eight explainable dimensions describing an entity's role in
the case graph, weighted into a single profile score and tier.

Dimensions (weights sum to 1.0):
    prominence     0.20  how many direct connections the entity has
    influence      0.15  PageRank authority in the directed graph
    bridging       0.20  how often shortest paths pass through the entity
    reach          0.10  closeness to the rest of the case network
    anchorage      0.10  how "rooted" the entity is (in-degree share)
    activity       0.10  how many relationships the entity participates in
    evidence_depth 0.10  how many source records back the entity's links
    community_span 0.05  size of the community it belongs to

Every dimension is normalized by the case's own maximum, so a profile is
relative to the case being investigated — never an absolute judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FEATURE_WEIGHTS: dict[str, float] = {
    "prominence": 0.20,
    "influence": 0.15,
    "bridging": 0.20,
    "reach": 0.10,
    "anchorage": 0.10,
    "activity": 0.10,
    "evidence_depth": 0.10,
    "community_span": 0.05,
}

TIER_THRESHOLDS = (("FOCAL", 0.70), ("SIGNIFICANT", 0.45), ("MONITORED", 0.25))


@dataclass
class NetworkProfileResult:
    overall_score: float = 0.0
    tier: str = "PERIPHERAL"
    features: list[dict[str, Any]] = field(default_factory=list)
    feature_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""


def _clamp01(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 6)


def tier_for(score: float) -> str:
    for tier, threshold in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "PERIPHERAL"


def build_network_profile(
    *,
    entity_id: str,
    entity_type: str,
    raw: dict[str, float],
    case_max: dict[str, float],
) -> NetworkProfileResult:
    """Compute the network DNA profile for a single entity."""
    features: list[dict[str, Any]] = []
    feature_map: dict[str, dict[str, Any]] = {}
    weighted = 0.0
    for name, weight in FEATURE_WEIGHTS.items():
        value = raw.get(name, 0.0)
        denominator = max(1e-9, case_max.get(name, 1.0))
        normalized = _clamp01(value / denominator)
        feature = {
            "name": name,
            "raw": round(value, 6),
            "normalized": normalized,
            "weight": weight,
            "description": _feature_description(name, value, denominator),
        }
        features.append(feature)
        feature_map[name] = feature
        weighted += weight * normalized
    overall = _clamp01(weighted)
    tier = tier_for(overall)
    signals = [
        {
            "name": name,
            "value": feature["normalized"],
            "weight": feature["weight"],
            "description": feature["description"],
        }
        for name, feature in feature_map.items()
        if feature["normalized"] >= 0.5
    ]
    top = sorted(features, key=lambda f: -(float(f["normalized"]) * float(f["weight"]) or 0.0))
    driver_labels = ", ".join(str(f["name"]) for f in top[:3])
    explanation = (
        f"{tier} entity '{entity_id}' ({entity_type}): overall score {overall:.3f}; "
        f"top contributors {driver_labels}."
    )
    return NetworkProfileResult(
        overall_score=overall,
        tier=tier,
        features=features,
        feature_map=feature_map,
        signals=signals,
        explanation=explanation,
    )


def _feature_description(name: str, raw: float, denominator: float) -> str:
    base = {
        "prominence": "direct connections (undirected degree)",
        "influence": "PageRank authority",
        "bridging": "fraction of shortest paths through the entity",
        "reach": "closeness to the rest of the graph",
        "anchorage": "share of connections that point into the entity",
        "activity": "relationship participation (directed edges)",
        "evidence_depth": "distinct source records backing the entity's links",
        "community_span": "size of the detected community it belongs to",
    }
    return f"{base.get(name, name)} ({raw:.3f} of case max {denominator:.3f})"

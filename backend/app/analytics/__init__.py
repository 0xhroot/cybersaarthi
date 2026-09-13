"""Investigation intelligence engine.

Deterministic, explainable analytics over a case's resolved knowledge graph
(see README "Graph Analytics" and docs/adr/006-entity-resolution.md for the
methodology; thresholds live in the engine modules below).
"""

from __future__ import annotations

from app.analytics.centrality import (
    compute_bridge_score,
    compute_centrality,
)
from app.analytics.communities import (
    detect_communities,
    summarise_communities,
)
from app.analytics.explanations import build_explanation
from app.analytics.graph import Graph, build_graph
from app.analytics.hypotheses import generate_hypotheses
from app.analytics.network_dna import build_network_profile, tier_for
from app.analytics.patterns import detect_patterns
from app.analytics.priority import compute_priority
from app.analytics.strength import (
    EvidenceStats,
    StrengthSignals,
    compute_strength_signals,
)

__all__ = [
    "EvidenceStats",
    "Graph",
    "StrengthSignals",
    "build_explanation",
    "build_graph",
    "build_network_profile",
    "compute_bridge_score",
    "compute_centrality",
    "compute_priority",
    "compute_strength_signals",
    "detect_communities",
    "detect_patterns",
    "generate_hypotheses",
    "summarise_communities",
    "tier_for",
]

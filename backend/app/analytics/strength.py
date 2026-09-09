"""Relationship strength — a deterministic, evidence-derived strength score.

Strength is computed ONLY from real, present data:
  - how many evidence rows support the relationship (coverage),
  - how many different evidence types (field / co_occurrence) are present,
  - how many distinct source records and evidence files back it,
  - the entity resolution confidence of both endpoints.

No fabricated source reliability is involved. Each sub-signal is normalised by
the case's own maximum so scores are comparable within a case.

    strength = 0.30*coverage + 0.15*type_diversity + 0.20*record_coverage
             + 0.20*file_independence + 0.15*resolution_confidence
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

KNOWN_EVIDENCE_TYPES = ("field", "co_occurrence")

WEIGHTS = {
    "coverage": 0.30,
    "type_diversity": 0.15,
    "record_coverage": 0.20,
    "file_independence": 0.20,
    "resolution_confidence": 0.15,
}


@dataclass(frozen=True)
class EvidenceStats:
    count: int = 0
    types: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()
    evidence_file_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrengthSignals:
    strength: float = 0.0
    coverage: float = 0.0
    type_diversity: float = 0.0
    record_coverage: float = 0.0
    file_independence: float = 0.0
    resolution_confidence: float = 1.0
    evidence_count: int = 0
    distinct_sources: int = 0
    independent_files: int = 0
    signals: list[dict[str, object]] = field(default_factory=list)


def _norm(value: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, value / denominator)


def compute_strength_signals(
    *,
    evidence: EvidenceStats,
    entity_confidences: tuple[float | None, float | None],
    case_max_evidence: int,
    case_distinct_sources: int,
    case_independent_files: int,
) -> StrengthSignals:
    """Compute the strength of one relationship from its evidence.

    All normalisation denominators come from the case (passed in by the
    caller) so scores stay within [0, 1] and are comparable between
    relationships in the same case.
    """
    coverage = _norm(math.log1p(evidence.count), math.log1p(max(1, case_max_evidence)))
    type_diversity = _norm(len(evidence.types), len(KNOWN_EVIDENCE_TYPES))
    record_coverage = _norm(len(evidence.source_record_ids), max(1, case_distinct_sources))
    file_independence = _norm(len(evidence.evidence_file_ids), max(1, case_independent_files))
    resolved = [c for c in entity_confidences if c is not None]
    resolution = float(sum(resolved) / len(resolved)) if resolved else 1.0

    strength = (
        WEIGHTS["coverage"] * coverage
        + WEIGHTS["type_diversity"] * type_diversity
        + WEIGHTS["record_coverage"] * record_coverage
        + WEIGHTS["file_independence"] * file_independence
        + WEIGHTS["resolution_confidence"] * resolution
    )
    strength = round(min(1.0, max(0.0, strength)), 6)

    signals = [
        {
            "name": "coverage",
            "value": round(coverage, 6),
            "weight": WEIGHTS["coverage"],
            "description": f"evidence count {evidence.count}; coverage = "
            f"log1p(count) / log1p(case max {case_max_evidence})",
        },
        {
            "name": "type_diversity",
            "value": round(type_diversity, 6),
            "weight": WEIGHTS["type_diversity"],
            "description": f"evidence types {sorted(evidence.types)} over "
            f"known {len(KNOWN_EVIDENCE_TYPES)}",
        },
        {
            "name": "record_coverage",
            "value": round(record_coverage, 6),
            "weight": WEIGHTS["record_coverage"],
            "description": f"distinct source records {len(evidence.source_record_ids)} "
            f"over case total {case_distinct_sources}",
        },
        {
            "name": "file_independence",
            "value": round(file_independence, 6),
            "weight": WEIGHTS["file_independence"],
            "description": f"distinct evidence files {len(evidence.evidence_file_ids)} "
            f"over case total {case_independent_files}",
        },
        {
            "name": "resolution_confidence",
            "value": round(resolution, 6),
            "weight": WEIGHTS["resolution_confidence"],
            "description": "mean of the two entities' resolution confidence"
            + (" (missing values default to 1.0)" if not resolved else ""),
        },
    ]
    return StrengthSignals(
        strength=strength,
        coverage=round(coverage, 6),
        type_diversity=round(type_diversity, 6),
        record_coverage=round(record_coverage, 6),
        file_independence=round(file_independence, 6),
        resolution_confidence=round(resolution, 6),
        evidence_count=evidence.count,
        distinct_sources=len(evidence.source_record_ids),
        independent_files=len(evidence.evidence_file_ids),
        signals=signals,
    )

"""Response schemas for the analytics and findings APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
FindingType = Literal[
    "pattern",
    "anomaly",
    "hypothesis",
    "network_insight",
    "relationship_insight",
]
FindingStatus = Literal["NEW", "REVIEWED", "DISMISSED", "CONFIRMED"]
PriorityTier = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ProfileTier = Literal["FOCAL", "SIGNIFICANT", "MONITORED", "PERIPHERAL"]


class CentralityEntry(BaseModel):
    entity_id: UUID
    metric: str
    metric_title: str
    raw: float
    normalized: float
    rank: int | None
    exact: bool


class CommunityOut(BaseModel):
    community_id: str
    member_count: int
    density: float
    internal_edges: int
    external_edges: int
    dominant_entity_types: list[str] = []
    dominant_relationship_types: list[str] = []
    member_entity_ids: list[UUID] = []
    score: float | None
    explanation: str | None


class StrengthSignal(BaseModel):
    name: str
    value: float
    weight: float
    description: str


class RelationshipStrengthOut(BaseModel):
    relationship_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    strength: float
    coverage: float
    type_diversity: float
    record_coverage: float
    file_independence: float
    resolution_confidence: float
    evidence_count: int
    distinct_sources: int
    independent_files: int
    signals: list[StrengthSignal] = []


class NetworkProfileFeature(BaseModel):
    name: str
    raw: float
    normalized: float
    weight: float
    description: str


class NetworkProfileOut(BaseModel):
    entity_id: UUID
    entity_type: str
    display_value: str
    overall_score: float
    tier: ProfileTier
    features: dict[str, NetworkProfileFeature]
    signals: list[dict[str, Any]] = []
    explanation: str | None


class PriorityOut(BaseModel):
    entity_id: UUID
    entity_type: str
    display_value: str
    prominence: float
    influence: float
    bridging: float
    reach: float
    pattern: float
    hypothesis: float
    priority_score: float
    tier: PriorityTier


class GraphPath(BaseModel):
    hops: int
    node_ids: list[UUID]
    relationship_ids: list[UUID]
    relationship_types: list[str] = []


class EgoPathsResponse(BaseModel):
    entity_id: UUID
    max_hops: int
    paths_count: int
    paths: list[GraphPath]


class PairPathsResponse(BaseModel):
    source_id: UUID
    target_id: UUID
    max_hops: int
    paths_count: int
    paths: list[GraphPath]


class PatternOut(BaseModel):
    finding_type: FindingType = "pattern"
    title: str
    summary: str
    severity: Severity
    score: float
    confidence: float | None
    affected_entities: list[UUID] = []
    affected_relationships: list[UUID] = []
    evidence_ids: list[UUID] = []
    signals: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class HypothesisOut(PatternOut):
    finding_type: FindingType = "hypothesis"
    candidate_relation_type: str | None = None


class AnalyticsSummary(BaseModel):
    case_id: UUID
    entity_count: int
    relationship_count: int
    community_count: int
    max_evidence_per_relationship: int
    average_network_score: float
    profile_tiers: dict[str, int] = {}
    priority_tiers: dict[str, int] = {}
    findings_by_severity: dict[str, int] = {}
    findings_by_type: dict[str, int] = {}
    finding_count: int
    generated_at: datetime


class AnalyticsEntityOut(BaseModel):
    entity_id: UUID
    entity_type: str
    display_value: str
    confidence: float | None
    centrality: dict[str, float] = {}
    bridge_score: float = 0.0
    community_id: str | None = None
    profile: NetworkProfileOut | None = None
    pattern: float = 0.0
    hypothesis: float = 0.0
    priority_score: float
    priority_tier: PriorityTier


class AnalyticsRunOut(BaseModel):
    id: UUID
    case_id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    stage: str
    error: str | None
    summary: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AnalyticsRunListResponse(BaseModel):
    items: list[AnalyticsRunOut]
    total: int


class FindingOut(BaseModel):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    finding_type: FindingType
    title: str
    summary: str
    severity: Severity
    score: float
    confidence: float | None
    status: FindingStatus
    affected_entities: list[UUID] = []
    affected_relationships: list[UUID] = []
    evidence_ids: list[UUID] = []
    explanation: dict[str, Any]
    details: dict[str, Any] | None
    created_at: datetime


class FindingListResponse(BaseModel):
    items: list[FindingOut]
    total: int
    limit: int
    offset: int


class FindingStatusOut(BaseModel):
    id: UUID
    status: FindingStatus


class FindingStatsOut(BaseModel):
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}

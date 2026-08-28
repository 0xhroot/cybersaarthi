"""Response schemas for knowledge-graph queries (PostgreSQL-backed projections)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: UUID
    entity_type: str
    canonical_value: str
    display_value: str
    status: str
    confidence: float | None
    aliases: list[str] = []


class GraphEdge(BaseModel):
    id: UUID
    source: UUID
    target: UUID
    relationship_type: str
    confidence: float | None
    context: dict[str, Any] | None


class GraphResponse(BaseModel):
    case_id: UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphStats(BaseModel):
    case_id: UUID
    node_count: int
    edge_count: int
    entity_type_counts: dict[str, int]
    relationship_type_counts: dict[str, int]
    generated_at: datetime
    synced: bool


class EntityEgoGraph(GraphResponse):
    centre: UUID

"""Routes: knowledge-graph queries (PostgreSQL projection + sync status)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, get_entity_query_service
from app.db.postgres import get_db_session
from app.schemas.graph import (
    EntityEgoGraph,
    GraphEdge,
    GraphNode,
    GraphResponse,
    GraphStats,
)
from app.services.entity_service import EntityQueryService

router = APIRouter(prefix="/cases", tags=["graph"])


def _to_graph_response(payload: dict[str, Any], case_id: uuid.UUID) -> GraphResponse:
    return GraphResponse(
        case_id=case_id,
        nodes=[GraphNode(**node) for node in payload["nodes"]],
        edges=[GraphEdge(**edge) for edge in payload["edges"]],
    )


@router.get("/{case_id}/graph", response_model=GraphResponse)
async def get_case_graph(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> GraphResponse:
    """The full projected knowledge graph for a case (PostgreSQL source of truth)."""
    await get_case_or_404(case_id, request, session)
    payload = await service.build_graph(case_id)
    return _to_graph_response(payload, case_id)


@router.get("/{case_id}/graph/entity/{entity_id}", response_model=EntityEgoGraph)
async def get_entity_ego_graph(
    case_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> EntityEgoGraph:
    """One-hop neighbourhood around a single entity."""
    await get_case_or_404(case_id, request, session)
    entity, _ = await service.get_entity_detail(entity_id)
    if entity is None or str(entity.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"entity {entity_id} not found")

    payload = await service.build_graph(case_id)
    node_map = {node["id"]: node for node in payload["nodes"]}
    if str(entity_id) not in node_map:
        raise HTTPException(status_code=404, detail=f"entity {entity_id} not in graph")

    neighbour_ids = {str(entity_id)}
    edges: list[dict[str, Any]] = []
    for edge in payload["edges"]:
        if edge["source"] == str(entity_id) or edge["target"] == str(entity_id):
            edges.append(edge)
            neighbour_ids.add(edge["source"])
            neighbour_ids.add(edge["target"])

    return EntityEgoGraph(
        case_id=case_id,
        nodes=[node for node in payload["nodes"] if node["id"] in neighbour_ids],
        edges=[edge for edge in edges],
        centre=entity_id,
    )


@router.get("/{case_id}/graph/stats", response_model=GraphStats)
async def get_graph_stats(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> GraphStats:
    """Aggregate metrics about a case's entity graph."""
    await get_case_or_404(case_id, request, session)
    payload = await service.build_graph(case_id)
    nodes: list[dict[str, Any]] = payload["nodes"]
    edges: list[dict[str, Any]] = payload["edges"]
    node_type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}
    for node in nodes:
        node_type_counts[node["entity_type"]] = node_type_counts.get(node["entity_type"], 0) + 1
    for edge in edges:
        edge_type_counts[edge["relationship_type"]] = (
            edge_type_counts.get(edge["relationship_type"], 0) + 1
        )
    return GraphStats(
        case_id=case_id,
        node_count=len(nodes),
        edge_count=len(edges),
        entity_type_counts=node_type_counts,
        relationship_type_counts=edge_type_counts,
        generated_at=datetime.now(UTC),
        synced=await service.graph_synced(case_id),
    )

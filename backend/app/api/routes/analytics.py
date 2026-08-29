"""Routes: investigation-intelligence analytics (Phase 3).

Every read endpoint recomputes the deterministic analytics pipeline from
PostgreSQL on demand; ``POST /analytics/run`` persists an AnalyticsRun with the
same numbers for auditability. Results are therefore always current and never
stale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import compute_priority
from app.analytics.findings import AnalyticsService
from app.analytics.priority import hypothesis_weight, pattern_weight
from app.api.dependencies import get_analytics_service, get_case_or_404
from app.db.postgres import get_db_session
from app.schemas.analytics import (
    AnalyticsEntityOut,
    AnalyticsRunListResponse,
    AnalyticsRunOut,
    AnalyticsSummary,
    CentralityEntry,
    CommunityOut,
    EgoPathsResponse,
    GraphPath,
    HypothesisOut,
    NetworkProfileOut,
    PairPathsResponse,
    PatternOut,
    PriorityOut,
    RelationshipStrengthOut,
)

router = APIRouter(prefix="/cases", tags=["analytics"])

MAX_HOPS_LIMIT = 8


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


def _to_community(community: dict[str, Any]) -> CommunityOut:
    return CommunityOut(
        community_id=str(community["community_id"]),
        member_count=int(community["member_count"]),
        density=float(community["density"]),
        internal_edges=int(community["internal_edges"]),
        external_edges=int(community["external_edges"]),
        dominant_entity_types=[str(t) for t in community.get("dominant_entity_types") or []],
        dominant_relationship_types=[
            str(t) for t in community.get("dominant_relationship_types") or []
        ],
        member_entity_ids=_uuids([str(m) for m in community.get("member_entity_ids") or []]),
        score=float(community["score"]) if community.get("score") is not None else None,
        explanation=community.get("explanation"),
    )


def _to_strength(rel: dict[str, Any], signals: Any) -> RelationshipStrengthOut:
    return RelationshipStrengthOut(
        relationship_id=uuid.UUID(str(rel["id"])),
        source_entity_id=uuid.UUID(str(rel["source_entity_id"])),
        target_entity_id=uuid.UUID(str(rel["target_entity_id"])),
        relationship_type=str(rel["relationship_type"]),
        strength=signals.strength,
        coverage=signals.coverage,
        type_diversity=signals.type_diversity,
        record_coverage=signals.record_coverage,
        file_independence=signals.file_independence,
        resolution_confidence=signals.resolution_confidence,
        evidence_count=signals.evidence_count,
        distinct_sources=signals.distinct_sources,
        independent_files=signals.independent_files,
        signals=[s for s in signals.signals],
    )


def _legacy_profile_meta(context: Any, entity_id: str) -> tuple[str, str]:
    meta = context.entities.get(entity_id)
    return meta.entity_type, meta.display_value


async def _priority_rows(context: Any) -> list[dict[str, Any]]:
    """Recompute per-entity priority inputs + tier from the context."""
    sev_by_entity: dict[str, list[str]] = {}
    hyp_counts: dict[str, int] = {}
    for draft in context.patterns:
        for affected in draft.affected_entities:
            sev_by_entity.setdefault(affected, []).append(draft.severity)
    for hypothesis in context.hypotheses:
        for affected in hypothesis["affected_entities"]:
            hyp_counts[affected] = hyp_counts.get(affected, 0) + 1
            sev_by_entity.setdefault(affected, []).append(hypothesis["severity"])

    rows: list[dict[str, Any]] = []
    for entity_id in context.entity_ids:
        profile = context.profiles.get(entity_id)
        if profile is None:
            continue
        feature_map = profile.feature_map
        prominence = float(feature_map.get("prominence", {}).get("normalized", 0.0))
        influence = float(feature_map.get("influence", {}).get("normalized", 0.0))
        bridging = float(feature_map.get("bridging", {}).get("normalized", 0.0))
        reach = float(feature_map.get("reach", {}).get("normalized", 0.0))
        p_weight = pattern_weight(sev_by_entity.get(entity_id, []))
        h_weight = hypothesis_weight(hyp_counts.get(entity_id, 0))
        score, tier = compute_priority(
            prominence=prominence,
            influence=influence,
            bridging=bridging,
            reach=reach,
            finding_severities=sev_by_entity.get(entity_id, []),
            hypothesis_count=hyp_counts.get(entity_id, 0),
        )
        entity_type, display = _legacy_profile_meta(context, entity_id)
        rows.append(
            {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "display_value": display,
                "prominence": prominence,
                "influence": influence,
                "bridging": bridging,
                "reach": reach,
                "pattern": p_weight,
                "hypothesis": h_weight,
                "priority_score": score,
                "tier": tier,
            }
        )
    return rows


@router.get("/{case_id}/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummary:
    """Case-level analytics summary (deterministic, computed on demand)."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    summary = context.summary
    return AnalyticsSummary(
        case_id=case_id,
        entity_count=int(summary["entity_count"]),
        relationship_count=int(summary["relationship_count"]),
        community_count=int(summary["community_count"]),
        max_evidence_per_relationship=int(summary["max_evidence_per_relationship"]),
        average_network_score=float(summary["average_network_score"]),
        profile_tiers={str(k): int(v) for k, v in summary["profile_tiers"].items()},
        priority_tiers={str(k): int(v) for k, v in summary["priority_tiers"].items()},
        findings_by_severity={str(k): int(v) for k, v in summary["findings_by_severity"].items()},
        findings_by_type={str(k): int(v) for k, v in summary["findings_by_type"].items()},
        finding_count=int(summary["finding_count"]),
        exact_graph=bool(summary.get("exact_graph", context.exact_graph)),
        approximation_notice=summary.get("approximation_notice"),
        generated_at=datetime.now(UTC),
    )


@router.get("/{case_id}/analytics/centrality", response_model=list[CentralityEntry])
async def get_centrality(
    case_id: uuid.UUID,
    metric: str = Query(
        "degree", description="degree|in_degree|out_degree|betweenness|closeness|pagerank"
    ),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[CentralityEntry]:
    """Exact centrality metric values for every entity (or the top N by rank)."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    entries = [
        CentralityEntry(
            entity_id=uuid.UUID(str(row["entity_id"])),
            metric=str(row["metric"]),
            metric_title=str(row["metric_title"]),
            raw=float(row["raw"]),
            normalized=float(row["normalized"]),
            rank=int(row["rank"]) if row["rank"] is not None else None,
            exact=bool(row["exact"]),
        )
        for row in context.centrality_records
        if str(row["metric"]) == metric
    ]
    entries.sort(key=lambda e: (e.rank is not None, e.rank or 0))
    return entries[:limit]


@router.get("/{case_id}/analytics/communities", response_model=list[CommunityOut])
async def get_communities(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[CommunityOut]:
    """Detected communities and their statistics."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    return [_to_community(community) for community in context.communities]


@router.get(
    "/{case_id}/analytics/entities/{entity_id}/analytics", response_model=AnalyticsEntityOut
)
async def get_entity_analytics(
    case_id: uuid.UUID,
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsEntityOut:
    """Network DNA profile + centrality + priority for one entity."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    entity_str = str(entity_id)
    meta = context.entities.get(entity_str)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"entity {entity_id} not found")

    profile = context.profiles.get(entity_str)
    profile_out = None
    if profile is not None:
        profile_out = NetworkProfileOut(
            entity_id=entity_id,
            entity_type=meta.entity_type,
            display_value=meta.display_value,
            overall_score=float(profile.overall_score),
            tier=str(profile.tier),
            features={
                str(feature["name"]): {
                    "name": str(feature["name"]),
                    "raw": float(feature["raw"]),
                    "normalized": float(feature["normalized"]),
                    "weight": float(feature["weight"]),
                    "description": str(feature["description"]),
                }
                for feature in profile.features
            },
            signals=profile.signals,
            explanation=profile.explanation,
        )

    centrality: dict[str, float] = {}
    for metric, values in context.metric_maps.items():
        if entity_str in values:
            centrality[str(metric)] = float(values[entity_str])

    priority = context.priorities.get(entity_str)
    score, tier = priority if priority else (0.0, "LOW")
    rows = await _priority_rows(context)
    row = next((r for r in rows if r["entity_id"] == entity_str), None)

    return AnalyticsEntityOut(
        entity_id=entity_id,
        entity_type=meta.entity_type,
        display_value=meta.display_value,
        confidence=meta.confidence,
        centrality=centrality,
        bridge_score=float(context.bridge_scores.get(entity_str, 0.0)),
        community_id=context.community_membership_map.get(entity_str),
        profile=profile_out,
        pattern=float(row["pattern"]) if row else 0.0,
        hypothesis=float(row["hypothesis"]) if row else 0.0,
        priority_score=float(score),
        priority_tier=str(tier),
    )


@router.get("/{case_id}/analytics/network-dna", response_model=list[NetworkProfileOut])
async def get_network_dna(
    case_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[NetworkProfileOut]:
    """Network DNA profiles for every entity, highest score first."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    profiles = []
    for entity_id, profile in context.profiles.items():
        meta = context.entities.get(entity_id)
        entity_type = meta.entity_type if meta else "unknown"
        display = meta.display_value if meta else entity_id
        profiles.append(
            NetworkProfileOut(
                entity_id=uuid.UUID(entity_id),
                entity_type=entity_type,
                display_value=display,
                overall_score=float(profile.overall_score),
                tier=str(profile.tier),
                features={
                    str(feature["name"]): {
                        "name": str(feature["name"]),
                        "raw": float(feature["raw"]),
                        "normalized": float(feature["normalized"]),
                        "weight": float(feature["weight"]),
                        "description": str(feature["description"]),
                    }
                    for feature in profile.features
                },
                signals=profile.signals,
                explanation=profile.explanation,
            )
        )
    profiles.sort(key=lambda p: (-p.overall_score, str(p.entity_id)))
    return profiles[:limit]


@router.get("/{case_id}/analytics/priorities", response_model=list[PriorityOut])
async def get_priorities(
    case_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[PriorityOut]:
    """Investigation priority for every entity (CRITICAL first)."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    rows = await _priority_rows(context)
    rows.sort(key=lambda r: (-r["priority_score"], r["entity_id"]))
    return [
        PriorityOut(
            entity_id=uuid.UUID(str(row["entity_id"])),
            entity_type=str(row["entity_type"]),
            display_value=str(row["display_value"]),
            prominence=float(row["prominence"]),
            influence=float(row["influence"]),
            bridging=float(row["bridging"]),
            reach=float(row["reach"]),
            pattern=float(row["pattern"]),
            hypothesis=float(row["hypothesis"]),
            priority_score=float(row["priority_score"]),
            tier=str(row["tier"]),
        )
        for row in rows[:limit]
    ]


@router.get("/{case_id}/analytics/strength", response_model=list[RelationshipStrengthOut])
async def get_relationship_strength(
    case_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[RelationshipStrengthOut]:
    """Relationship strength for every relationship in the case, strongest first."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    rows = [
        _to_strength(
            context.relationship_by_id.get(rel_id, {}),
            context.strengths[rel_id],
        )
        for rel_id in context.strengths
        if rel_id in context.relationship_by_id
    ]
    rows.sort(key=lambda r: (-r.strength, str(r.relationship_id)))
    return rows[:limit]


@router.get("/{case_id}/analytics/paths/entity/{entity_id}", response_model=EgoPathsResponse)
async def get_entity_paths(
    case_id: uuid.UUID,
    entity_id: uuid.UUID,
    max_hops: int = Query(3, ge=1, le=MAX_HOPS_LIMIT),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> EgoPathsResponse:
    """Bounded multi-hop traversals (Neo4j) originating from one entity."""
    await get_case_or_404(case_id, session)
    from app.analytics.paths import bounded_ego_paths

    paths: list[dict[str, Any]] = await bounded_ego_paths(
        service.graph_store,
        str(case_id),
        str(entity_id),
        max_hops,
        limit,
    )
    return EgoPathsResponse(
        entity_id=entity_id,
        max_hops=max_hops,
        paths_count=len(paths),
        paths=[
            GraphPath(
                hops=int(path["hops"]),
                node_ids=_uuids([str(n) for n in path["node_ids"]]),
                relationship_ids=_uuids([str(r) for r in path["relationship_ids"]]),
                relationship_types=[str(t) for t in path["relationship_types"]],
            )
            for path in paths
        ],
    )


@router.get("/{case_id}/analytics/paths", response_model=PairPathsResponse)
async def get_pair_paths(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    max_hops: int = Query(4, ge=2, le=MAX_HOPS_LIMIT),
    limit: int = Query(5, ge=1, le=25),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> PairPathsResponse:
    """Non-trivial paths (2 .. max_hops) between two entities (Neo4j)."""
    await get_case_or_404(case_id, session)
    if source_id == target_id:
        raise HTTPException(status_code=422, detail="source_id and target_id must differ")
    from app.analytics.paths import bounded_pair_paths

    paths: list[dict[str, Any]] = await bounded_pair_paths(
        service.graph_store,
        str(case_id),
        str(source_id),
        str(target_id),
        max_hops,
        limit,
    )
    return PairPathsResponse(
        source_id=source_id,
        target_id=target_id,
        max_hops=max_hops,
        paths_count=len(paths),
        paths=[
            GraphPath(
                hops=int(path["hops"]),
                node_ids=_uuids([str(n) for n in path["node_ids"]]),
                relationship_ids=_uuids([str(r) for r in path["relationship_ids"]]),
                relationship_types=[str(t) for t in path["relationship_types"]],
            )
            for path in paths
        ],
    )


@router.get("/{case_id}/analytics/patterns", response_model=list[PatternOut])
async def get_patterns(
    case_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[PatternOut]:
    """Detected suspicious patterns with their signals and evidence."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    return [
        PatternOut(
            title=p.title,
            summary=p.summary,
            severity=str(p.severity),
            score=float(p.score),
            confidence=p.confidence,
            affected_entities=_uuids(p.affected_entities),
            affected_relationships=_uuids(p.affected_relationships),
            evidence_ids=_uuids(service.affected_evidence(context, p.affected_relationships)),
            signals=p.signals,
            metadata=p.metadata,
        )
        for p in context.patterns[:limit]
    ]


@router.get("/{case_id}/analytics/hypotheses", response_model=list[HypothesisOut])
async def get_hypotheses(
    case_id: uuid.UUID,
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[HypothesisOut]:
    """Missing-link hypotheses (candidate edges — never written to the graph)."""
    await get_case_or_404(case_id, session)
    context = await service.compute(case_id)
    return [
        HypothesisOut(
            title=h["title"],
            summary=h["summary"],
            severity=str(h["severity"]),
            score=float(h["score"]),
            confidence=h["confidence"],
            affected_entities=_uuids(h["affected_entities"]),
            affected_relationships=_uuids(h["affected_relationships"]),
            evidence_ids=_uuids(service.affected_evidence(context, h["affected_relationships"])),
            signals=h["signals"],
            metadata=h["metadata"],
            candidate_relation_type=h.get("candidate_relation_type"),
        )
        for h in context.hypotheses[:limit]
    ]


@router.post("/{case_id}/analytics/run", response_model=AnalyticsRunOut, status_code=201)
async def run_analytics(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsRunOut:
    """Persist a complete analytics run: metrics, communities, profiles, findings."""
    await get_case_or_404(case_id, session)
    run = await service.run_analytics(case_id)
    return AnalyticsRunOut(
        id=run.id,
        case_id=case_id,
        status=run.status,
        stage=run.stage,
        error=run.error,
        summary=run.summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


@router.get("/{case_id}/analytics/runs", response_model=AnalyticsRunListResponse)
async def list_analytics_runs(
    case_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsRunListResponse:
    """History of persisted analytics runs for a case."""
    await get_case_or_404(case_id, session)
    runs = await service.list_runs(case_id)
    runs = runs[:limit]
    return AnalyticsRunListResponse(
        items=[
            AnalyticsRunOut(
                id=run.id,
                case_id=case_id,
                status=run.status,
                stage=run.stage,
                error=run.error,
                summary=run.summary,
                started_at=run.started_at,
                completed_at=run.completed_at,
                created_at=run.created_at,
            )
            for run in runs
        ],
        total=len(runs),
    )

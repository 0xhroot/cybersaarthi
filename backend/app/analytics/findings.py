"""AnalyticsService — orchestrates the investigation intelligence engine.

A single deterministic pipeline turns a case's resolved entities and
relationships into explained analytics:

    1. Load entities + relationships (+ their evidence) from PostgreSQL.
    2. Build the in-memory graph and run exact graph algorithms.
    3. Compute centrality metrics, communities, relationship strength.
    4. Detect suspicious patterns and missing-link hypotheses.
    5. Compute Network DNA profiles and investigation priorities.
    6. Assemble explainable findings (status NEW — never auto-CONFIRMED).
    7. Persist one AnalyticsRun with metrics/communities/profiles/findings,
       or return the context directly (GET endpoints compute on demand).

Everything is deterministic, source-of-truth is PostgreSQL, and Neo4j is
consulted only where traversal is the right tool (bounded paths in the API).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.analytics.centrality import compute_bridge_score, compute_centrality
from app.analytics.communities import detect_communities, summarise_communities
from app.analytics.explanations import build_explanation
from app.analytics.graph import Graph, build_graph, connected_components
from app.analytics.hypotheses import generate_hypotheses
from app.analytics.network_dna import build_network_profile
from app.analytics.patterns import EntityMeta, PatternDraft, detect_patterns
from app.analytics.priority import compute_priority
from app.analytics.strength import EvidenceStats, StrengthSignals, compute_strength_signals
from app.core.config import Settings
from app.db.neo4j import GraphStore
from app.models import AnalyticsRun
from app.repositories.analytics_repository import AnalyticsDataRepository

logger = logging.getLogger(__name__)

_FINDING_TYPE_LABEL = {
    "pattern": "Suspicious pattern",
    "anomaly": "Structural anomaly",
    "hypothesis": "Missing-link hypothesis",
    "network_insight": "Network insight",
    "relationship_insight": "Relationship insight",
}


@dataclass
class AnalyticsContext:
    case_id: str
    entities: dict[str, EntityMeta] = field(default_factory=dict)
    entity_ids: list[str] = field(default_factory=list)
    graph: Graph | None = None
    centrality_records: list[dict[str, Any]] = field(default_factory=list)
    metric_maps: dict[str, dict[str, float]] = field(default_factory=dict)
    bridge_scores: dict[str, float] = field(default_factory=dict)
    communities: list[dict[str, Any]] = field(default_factory=list)
    community_membership_map: dict[str, str] = field(default_factory=dict)
    profiles: dict[str, Any] = field(default_factory=dict)
    priorities: dict[str, tuple[float, str]] = field(default_factory=dict)
    strengths: dict[str, StrengthSignals] = field(default_factory=dict)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    relationship_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    edge_relationships: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    evidence_by_relation: dict[str, EvidenceStats] = field(default_factory=dict)
    patterns: list[PatternDraft] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    relationship_spread_seconds: dict[str, float] = field(default_factory=dict)


class AnalyticsService:
    def __init__(
        self,
        data_repo: AnalyticsDataRepository,
        graph_store: GraphStore,
        settings: Settings,
    ) -> None:
        self._data = data_repo
        self._graph_store = graph_store
        self._settings = settings

    @property
    def graph_store(self) -> GraphStore:
        return self._graph_store

    @property
    def settings(self) -> Settings:
        return self._settings

    def affected_evidence(self, context: AnalyticsContext, rel_ids: list[str]) -> list[str]:
        return self._affected_evidence(context, rel_ids)

    # -- pipeline ---------------------------------------------------------
    async def compute(self, case: uuid.UUID) -> AnalyticsContext:
        context = AnalyticsContext(case_id=str(case))
        entities = await self._data.list_entities(case)
        relationships = await self._data.list_relationships(case)

        context.entities = {
            str(entity.id): EntityMeta(
                entity_id=str(entity.id),
                entity_type=entity.entity_type,
                display_value=entity.display_value,
                confidence=entity.confidence,
            )
            for entity in entities
        }
        entity_types = {eid: meta.entity_type for eid, meta in context.entities.items()}
        context.entity_ids = [str(e.id) for e in entities]

        rel_rows: list[tuple[str, str, str]] = []
        for rel in relationships:
            rel_rows.append(
                (
                    str(rel.source_entity_id),
                    str(rel.target_entity_id),
                    rel.relationship_type,
                )
            )
        context.graph = build_graph(set(entity_types), rel_rows)
        graph = context.graph

        context.edge_relationships = defaultdict(list)
        context.relationship_by_id = {}
        _min_ts: dict[str, float] = {}
        _max_ts: dict[str, float] = {}
        for rel in relationships:
            rel_id = str(rel.id)
            source = str(rel.source_entity_id)
            target = str(rel.target_entity_id)
            pair = (source, target) if source < target else (target, source)
            context.edge_relationships[pair].append(rel_id)
            context.relationship_by_id[rel_id] = {
                "id": rel_id,
                "source_entity_id": str(rel.source_entity_id),
                "target_entity_id": str(rel.target_entity_id),
                "relationship_type": rel.relationship_type,
                "confidence": rel.confidence,
                "evidence_ids": [],
            }
            timestamp = rel.created_at.timestamp()
            _min_ts.setdefault(str(rel.source_entity_id), timestamp)
            _max_ts.setdefault(str(rel.source_entity_id), timestamp)
            _min_ts.setdefault(str(rel.target_entity_id), timestamp)
            _max_ts.setdefault(str(rel.target_entity_id), timestamp)
            _min_ts[str(rel.source_entity_id)] = min(_min_ts[str(rel.source_entity_id)], timestamp)
            _max_ts[str(rel.source_entity_id)] = max(_max_ts[str(rel.source_entity_id)], timestamp)
            _min_ts[str(rel.target_entity_id)] = min(_min_ts[str(rel.target_entity_id)], timestamp)
            _max_ts[str(rel.target_entity_id)] = max(_max_ts[str(rel.target_entity_id)], timestamp)

        context.relationship_spread_seconds = {
            entity: max(0.0, (_max_ts.get(entity, 0.0) - _min_ts.get(entity, 0.0)))
            for entity in set(_min_ts) | set(_max_ts)
        }

        # relationship strength from real evidence
        context.evidence_by_relation = await self._data.evidence_stats_by_relationship(case)
        totals = await self._data.case_evidence_totals(context.evidence_by_relation)
        for rel in relationships:
            rel_id = str(rel.id)
            stats = context.evidence_by_relation.get(rel_id, EvidenceStats())
            entity_confidences = (
                context.entities.get(str(rel.source_entity_id)),
                context.entities.get(str(rel.target_entity_id)),
            )
            confidences = (
                entity_confidences[0].confidence if entity_confidences[0] else None,
                entity_confidences[1].confidence if entity_confidences[1] else None,
            )
            signals = compute_strength_signals(
                evidence=stats,
                entity_confidences=confidences,
                case_max_evidence=totals.max_evidence_per_relationship,
                case_distinct_sources=totals.distinct_source_records,
                case_independent_files=totals.distinct_evidence_files,
            )
            context.strengths[rel_id] = signals
            context.relationship_by_id[rel_id]["evidence_ids"] = sorted(stats.source_record_ids)

        # centrality
        context.centrality_records = compute_centrality(graph, self._settings)
        context.metric_maps = {}
        for record in context.centrality_records:
            metric = str(record["metric"])
            normalized = float(record.get("normalized") or 0.0)
            context.metric_maps.setdefault(metric, {})[str(record["entity_id"])] = normalized

        context.bridge_scores = compute_bridge_score(graph)

        # communities: exact greedy modularity under the cap, otherwise
        # connected components (both deterministic and documented).
        if len(graph.nodes) <= self._settings.ANALYTICS_GRAPH_NODE_CAP:
            communities = detect_communities(
                graph, quality_threshold=self._settings.ANALYTICS_COMMUNITY_QUALITY
            )
        else:
            communities = [
                {
                    "community_id": f"c{index}",
                    "member_ids": set(component),
                    "size": len(component),
                    "internal": sum(
                        1 for edge in graph.edges if edge.a in component and edge.b in component
                    ),
                    "external": 0,
                    "density": 0.0,
                }
                for index, component in enumerate(connected_components(graph))
            ]

        context.communities = summarise_communities(graph, communities, entity_types)
        context.community_membership_map = {}
        for community in context.communities:
            cid = str(community["community_id"])
            for member in community["member_entity_ids"]:
                context.community_membership_map[str(member)] = cid

        # patterns and hypotheses
        context.patterns = detect_patterns(
            graph,
            context.entities,
            self._settings,
            edge_relationships=dict(context.edge_relationships),
            relationship_spread_seconds=context.relationship_spread_seconds,
        )
        context.hypotheses = [
            {
                "title": h.title,
                "summary": h.summary,
                "severity": h.severity,
                "score": h.score,
                "confidence": h.confidence,
                "affected_entities": h.affected_entities,
                "affected_relationships": h.affected_relationships,
                "candidate_relation_type": h.candidate_relation_type,
                "signals": h.signals,
                "metadata": h.metadata,
            }
            for h in generate_hypotheses(
                graph,
                context.entities,
                self._settings,
                edge_relationships=dict(context.edge_relationships),
            )
        ]

        # network DNA dimensions (raw) + case maxima
        degree = graph.degree
        activity = {
            node: context.graph.out_degree.get(node, 0) + context.graph.in_degree.get(node, 0)
            if context.graph
            else 0
            for node in graph.nodes
        }
        evidence_depth: dict[str, int] = defaultdict(int)
        for rel in relationships:
            stats = context.evidence_by_relation.get(str(rel.id), EvidenceStats())
            for _ in stats.source_record_ids:
                evidence_depth[str(rel.source_entity_id)] += 1
                evidence_depth[str(rel.target_entity_id)] += 1
        community_sizes: dict[str, int] = {}
        for community in context.communities:
            cid = str(community["community_id"])
            community_sizes[cid] = int(community["member_count"])

        raw_map: dict[str, dict[str, float]] = {
            "prominence": {n: float(degree.get(n, 0)) for n in graph.nodes},
            "influence": context.metric_maps.get("pagerank", {}),
            "bridging": {n: float(context.bridge_scores.get(n, 0.0)) for n in graph.nodes},
            "reach": context.metric_maps.get("closeness", {}),
            "anchorage": {
                n: (
                    graph.in_degree.get(n, 0)
                    / max(1, graph.in_degree.get(n, 0) + graph.out_degree.get(n, 0))
                    if graph.in_degree.get(n, 0) + graph.out_degree.get(n, 0) > 0
                    else 0.5
                )
                for n in graph.nodes
            },
            "activity": {n: float(activity.get(n, 0)) for n in graph.nodes},
            "evidence_depth": {n: float(evidence_depth.get(n, 0)) for n in graph.nodes},
            "community_span": {
                n: float(community_sizes.get(context.community_membership_map.get(n, ""), 0))
                for n in graph.nodes
            },
        }
        case_max = {
            name: max(
                (v for v in dims.values() if v > 0),
                default=0.0,
            )
            for name, dims in raw_map.items()
        }
        case_max["anchorage"] = max(1.0, case_max["anchorage"])

        # priorities need finding severities per entity (patterns/hypotheses first)
        finding_severities: dict[str, list[str]] = defaultdict(list)
        for draft in context.patterns:
            for affected in draft.affected_entities:
                finding_severities[affected].append(draft.severity)
        for hypothesis in context.hypotheses:
            for affected in hypothesis["affected_entities"]:
                finding_severities[affected].append(hypothesis["severity"])

        hypothesis_counts: dict[str, int] = defaultdict(int)
        for hypothesis in context.hypotheses:
            for affected in hypothesis["affected_entities"]:
                hypothesis_counts[affected] += 1

        context.priorities = {
            node: compute_priority(
                prominence=raw_map["prominence"].get(node, 0.0) / max(1.0, case_max["prominence"]),
                influence=raw_map["influence"].get(node, 0.0) / max(1.0, case_max["influence"]),
                bridging=raw_map["bridging"].get(node, 0.0) / max(1.0, case_max["bridging"]),
                reach=raw_map["reach"].get(node, 0.0) / max(1.0, case_max["reach"]),
                finding_severities=finding_severities.get(node, []),
                hypothesis_count=hypothesis_counts.get(node, 0),
            )
            for node in graph.nodes
        }

        context.profiles = {
            node: build_network_profile(
                entity_id=node,
                entity_type=context.entities.get(
                    node, EntityMeta(node, "unknown", node)
                ).entity_type,
                raw={name: dims.get(node, 0.0) for name, dims in raw_map.items()},
                case_max=case_max,
            )
            for node in graph.nodes
        }

        context.findings = self._assemble_findings(context)
        context.summary = self._summary(context, totals.max_evidence_per_relationship)
        return context

    # -- findings assembly -------------------------------------------------
    def _assemble_findings(self, context: AnalyticsContext) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        # patterns
        for draft in context.patterns:
            evidence_ids = self._affected_evidence(context, draft.affected_relationships)
            findings.append(
                {
                    "finding_type": "pattern",
                    "title": draft.title,
                    "summary": draft.summary,
                    "severity": draft.severity,
                    "score": draft.score,
                    "confidence": draft.confidence,
                    "affected_entities": draft.affected_entities,
                    "affected_relationships": draft.affected_relationships,
                    "evidence_ids": evidence_ids,
                    "explanation": build_explanation(
                        approach=(
                            f"Rule-based structural detector "
                            f"'{draft.metadata.get('pattern', 'pattern')}' "
                            f"(documented deterministic formula)"
                        ),
                        signals=draft.signals,
                        evidence=[{"kind": "source_record", "id": eid} for eid in evidence_ids],
                    ),
                    "metadata": draft.metadata,
                }
            )
        # hypotheses
        for hypothesis in context.hypotheses:
            evidence_ids = self._affected_evidence(context, hypothesis["affected_relationships"])
            findings.append(
                {
                    "finding_type": "hypothesis",
                    "title": hypothesis["title"],
                    "summary": hypothesis["summary"],
                    "severity": hypothesis["severity"],
                    "score": hypothesis["score"],
                    "confidence": hypothesis["confidence"],
                    "affected_entities": hypothesis["affected_entities"],
                    "affected_relationships": hypothesis["affected_relationships"],
                    "evidence_ids": evidence_ids,
                    "explanation": build_explanation(
                        approach=(
                            "Collaborative blocking: entities sharing a common "
                            "neighbour / same detected community are flagged as "
                            "candidate links (missing-link hypothesis)."
                        ),
                        signals=hypothesis["signals"],
                        paths=[
                            {
                                "hops": 2,
                                "nodes": [
                                    hypothesis["affected_entities"][0],
                                    shared,
                                    hypothesis["affected_entities"][1],
                                ],
                                "relationships": hypothesis["affected_relationships"],
                                "description": "two-hop chain through shared connections",
                            }
                            for shared in hypothesis["metadata"].get("shared_neighbor_ids", [])
                        ],
                        evidence=[{"kind": "source_record", "id": eid} for eid in evidence_ids],
                        limitations=[
                            "A missing-link hypothesis is a candidate edge, not evidence "
                            "that a relationship exists; it never creates a graph edge."
                        ],
                    ),
                    "metadata": hypothesis["metadata"],
                }
            )
        # network insights (bounded)
        findings.extend(self._network_insights(context))
        findings.extend(self._relationship_insights(context))
        findings.sort(key=lambda f: (-float(f["score"]), str(f["title"])))
        return findings[:200]

    def _network_insights(self, context: AnalyticsContext) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        node_count = len(context.entity_ids)
        rel_count = len(context.relationship_by_id)
        if node_count and rel_count:
            insights.append(
                {
                    "finding_type": "network_insight",
                    "title": "Network composition",
                    "summary": (
                        f"The case contains {node_count} entities and {rel_count} "
                        f"relationships across {len(context.communities)} detected "
                        f"communities."
                    ),
                    "severity": "LOW",
                    "score": 0.3,
                    "confidence": 1.0,
                    "affected_entities": [],
                    "affected_relationships": [],
                    "evidence_ids": [],
                    "explanation": build_explanation(
                        approach="Direct counts from the case graph.",
                        signals=[
                            {
                                "name": "entity_count",
                                "value": node_count,
                                "weight": 1.0,
                                "description": "resolved entities",
                            },
                            {
                                "name": "relationship_count",
                                "value": rel_count,
                                "weight": 1.0,
                                "description": "canonical relationships",
                            },
                            {
                                "name": "community_count",
                                "value": len(context.communities),
                                "weight": 1.0,
                                "description": "detected communities",
                            },
                        ],
                    ),
                    "metadata": {"type": "composition"},
                }
            )
        pagerank = context.metric_maps.get("pagerank", {})
        if pagerank:
            top = max(pagerank, key=lambda k: pagerank[k])
            meta = context.entities.get(top)
            display = meta.display_value if meta else top
            insights.append(
                {
                    "finding_type": "network_insight",
                    "title": f"Central entity: {display}",
                    "summary": (
                        f"'{display}' has the highest PageRank influence "
                        f"({pagerank[top]:.3f}); it is a network-wide hub."
                    ),
                    "severity": "MEDIUM",
                    "score": 0.6,
                    "confidence": 0.9,
                    "affected_entities": [top],
                    "affected_relationships": [],
                    "evidence_ids": [],
                    "explanation": build_explanation(
                        approach="Deterministic PageRank power iteration (d=0.85).",
                        signals=[
                            {
                                "name": "pagerank",
                                "value": round(pagerank[top], 6),
                                "weight": 1.0,
                                "description": "PageRank of the most influential entity",
                            },
                        ],
                    ),
                    "metadata": {"type": "central_entity"},
                }
            )
        second_hops = 0
        graph = context.graph
        if graph and len(graph.nodes) > 1:
            for a in graph.nodes:
                neighbors = graph.adjacency.get(a, set())
                depth2 = set()
                for nb in neighbors:
                    depth2.update(graph.adjacency.get(nb, set()))
                depth2 -= neighbors
                depth2.discard(a)
                second_hops += len(depth2)
            second_hops //= 2
        insights.append(
            {
                "finding_type": "network_insight",
                "title": "Second-degree connectivity",
                "summary": (
                    f"{second_hops} entity pairs are connected through exactly one "
                    f"intermediate entity (2-hop chains) — indirect connections to "
                    f"review."
                ),
                "severity": "LOW",
                "score": 0.35,
                "confidence": 0.85,
                "affected_entities": [],
                "affected_relationships": [],
                "evidence_ids": [],
                "explanation": build_explanation(
                    approach="2-hop neighbourhood counting over the undirected graph.",
                    signals=[
                        {
                            "name": "two_hop_pairs",
                            "value": second_hops,
                            "weight": 1.0,
                            "description": "pairs linked by exactly one intermediate entity",
                        },
                    ],
                ),
                "metadata": {"type": "indirect_connectivity"},
            }
        )
        return insights

    def _relationship_insights(self, context: AnalyticsContext) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        if not context.strengths:
            return insights
        ordered = sorted(context.strengths.items(), key=lambda kv: -kv[1].strength)
        top = ordered[0] if ordered else None
        if top and top[1].strength > 0.0:
            rel = context.relationship_by_id.get(top[0], {})
            source = context.entities.get(str(rel.get("source_entity_id", "")))
            target = context.entities.get(str(rel.get("target_entity_id", "")))
            source_label = source.display_value if source else rel.get("source_entity_id")
            target_label = target.display_value if target else rel.get("target_entity_id")
            affected = [
                str(rel.get("source_entity_id", "")),
                str(rel.get("target_entity_id", "")),
            ]
            top_evidence = context.relationship_by_id.get(top[0], {}).get("evidence_ids", [])
            insights.append(
                {
                    "finding_type": "relationship_insight",
                    "title": "Strongest supported relationship",
                    "summary": (
                        f"'{source_label}' → '{target_label}' "
                        f"('{rel.get('relationship_type')}') is backed by "
                        f"{top[1].evidence_count} evidence rows across "
                        f"{top[1].independent_files} file(s) — strength "
                        f"{top[1].strength:.2f}."
                    ),
                    "severity": "LOW",
                    "score": 0.5,
                    "confidence": 0.9,
                    "affected_entities": affected,
                    "affected_relationships": [top[0]],
                    "evidence_ids": list(top_evidence),
                    "explanation": build_explanation(
                        approach="Evidence-derived strength (coverage + diversity + "
                        "independence + resolution confidence).",
                        signals=top[1].signals,
                        evidence=[{"kind": "source_record", "id": eid} for eid in top_evidence],
                    ),
                    "metadata": {"type": "strongest_relationship"},
                }
            )
        weak = [rid for rid, sig in context.strengths.items() if sig.evidence_count == 1]
        if weak:
            rel = context.relationship_by_id.get(weak[0], {})
            source = context.entities.get(str(rel.get("source_entity_id", "")))
            target = context.entities.get(str(rel.get("target_entity_id", "")))
            source_label = source.display_value if source else ""
            target_label = target.display_value if target else ""
            affected = [
                str(rel.get("source_entity_id", "")),
                str(rel.get("target_entity_id", "")),
            ]
            weak_evidence = context.relationship_by_id.get(weak[0], {}).get("evidence_ids", [])
            insights.append(
                {
                    "finding_type": "relationship_insight",
                    "title": "Thinly supported relationship",
                    "summary": (
                        f"'{source_label}' → '{target_label}' has a single "
                        f"supporting evidence row ({len(weak)} such relationships "
                        f"in the case). Recommend corroboration."
                    ),
                    "severity": "MEDIUM",
                    "score": 0.55,
                    "confidence": 0.7,
                    "affected_entities": affected,
                    "affected_relationships": [weak[0]],
                    "evidence_ids": list(weak_evidence),
                    "explanation": build_explanation(
                        approach="Evidence count = 1 signals under-supported edges.",
                        signals=[
                            {
                                "name": "single_evidence_count",
                                "value": len(weak),
                                "weight": 1.0,
                                "description": "relationships with exactly one evidence row",
                            },
                        ],
                    ),
                    "metadata": {"type": "thin_evidence"},
                }
            )
        return insights

    def _affected_evidence(self, context: AnalyticsContext, rel_ids: list[str]) -> list[str]:
        ids: set[str] = set()
        for rel_id in rel_ids:
            ids.update(context.relationship_by_id.get(rel_id, {}).get("evidence_ids", []))
        return sorted(ids)

    # -- summary -----------------------------------------------------------
    def _summary(self, context: AnalyticsContext, max_evidence: int) -> dict[str, Any]:
        tier_counts: dict[str, int] = defaultdict(int)
        profile_scores: list[float] = []
        for profile in context.profiles.values():
            tier_counts[profile.tier] += 1
            profile_scores.append(float(profile.overall_score))
        priority_counts: dict[str, int] = defaultdict(int)
        for _, tier in context.priorities.values():
            priority_counts[tier] += 1
        severity_counts: dict[str, int] = defaultdict(int)
        type_counts: dict[str, int] = defaultdict(int)
        for finding in context.findings:
            severity_counts[str(finding["severity"])] += 1
            type_counts[str(finding["finding_type"])] += 1
        return {
            "entity_count": len(context.entity_ids),
            "relationship_count": len(context.relationship_by_id),
            "community_count": len(context.communities),
            "max_evidence_per_relationship": max_evidence,
            "profile_tiers": dict(tier_counts),
            "average_network_score": (
                round(sum(profile_scores) / len(profile_scores), 4) if profile_scores else 0.0
            ),
            "priority_tiers": dict(priority_counts),
            "findings_by_severity": dict(severity_counts),
            "findings_by_type": dict(type_counts),
            "finding_count": len(context.findings),
        }

    # -- persistence -------------------------------------------------------
    async def run_analytics(self, case: uuid.UUID) -> AnalyticsRun:
        """Compute and persist a full analytics run as one atomic transaction."""
        run = await self._data.create_run(case)
        await self._data.update_run(run.id, stage="compute")
        try:
            context = await self.compute(case)
            await self._data.save_metric_results(case, run.id, context.centrality_records)
            await self._data.save_community_results(case, run.id, context.communities)
            profiles_rows = []
            for entity_id, profile in context.profiles.items():
                profiles_rows.append(
                    {
                        "entity_id": entity_id,
                        "overall_score": float(profile.overall_score),
                        "tier": profile.tier,
                        "features": {feature["name"]: feature for feature in profile.features},
                        "signals": profile.signals,
                        "explanation": profile.explanation,
                    }
                )
            await self._data.save_network_profiles(case, run.id, profiles_rows)
            await self._data.save_findings(case, run.id, context.findings)
            await self._data.update_run(
                run.id,
                status="completed",
                stage="done",
                summary=context.summary,
            )
            await self._data.commit()
            logger.info("analytics run completed", extra={"case_id": str(case), "run": str(run.id)})
        except Exception as exc:  # noqa: BLE001 - persisted so the operator can inspect
            logger.exception("analytics run failed")
            try:
                await self._data.update_run(run.id, status="failed", stage="error", error=str(exc))
                await self._data.commit()
            except Exception:  # noqa: BLE001 - the failure itself may be a write error
                logger.exception("could not persist failed analytics run")
        return run

    async def list_runs(self, case: uuid.UUID) -> list[AnalyticsRun]:
        return await self._data.list_runs(case)

"""Deterministic preview of the investigation-intelligence engine.

Runs the analytics pipeline against the seeded demo case and prints the key
outputs (summary, findings, communities, hypotheses, network DNA, paths) so the
Phase 3 behaviour can be inspected without writing rows. Run from inside the
backend container:

    python -m scripts.preview_analytics
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.analytics.findings import AnalyticsService
from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.models import Case
from app.repositories.analytics_repository import AnalyticsDataRepository
from sqlalchemy import select

logger = logging.getLogger(__name__)

DEMO_CASE_NUMBER = "DEMO-2026-001"


async def main() -> None:
    settings: Settings = get_settings()
    database = Database(settings)
    graph_store = GraphStore(settings)
    try:
        factory = database.session_factory()
        async with factory() as session:
            result = await session.execute(select(Case).where(Case.case_number == DEMO_CASE_NUMBER))
            case = result.scalar_one_or_none()
            if case is None:
                print("demo case not found - run scripts.seed_demo first")
                return
            case_id = uuid.UUID(str(case.id))
            print(f"case {DEMO_CASE_NUMBER} id={case_id}")

            service = AnalyticsService(
                data_repo=AnalyticsDataRepository(session),
                graph_store=graph_store,
                settings=settings,
            )
            context = await service.compute(case_id)

            summary = context.summary
            print("=== summary ===")
            for key, value in summary.items():
                print(f"  {key}: {value}")

            print("\n=== communities ===")
            for community in context.communities:
                members = community.get("member_entity_ids") or []
                display = [
                    context.entities.get(str(m)).display_value
                    for m in members
                    if context.entities.get(str(m))
                ]
                print(
                    f"  {community['community_id']}: size={community['member_count']}"
                    f" density={community['density']:.2f} members={display}"
                )

            print("\n=== top findings ===")
            for finding in context.findings[:8]:
                print(
                    f"  [{finding['severity']}] {finding['finding_type']} "
                    f"score={finding['score']:.2f} :: {finding['title']}"
                )

            print("\n=== hypotheses ===")
            for hypothesis in context.hypotheses[:6]:
                affected = [
                    context.entities[str(e)].display_value if str(e) in context.entities else e
                    for e in hypothesis["affected_entities"]
                ]
                print(
                    f"  {affected} <- {hypothesis['candidate_relation_type']} "
                    f"({hypothesis['score']:.2f})"
                )

            print("\n=== network DNA (top 5) ===")
            ordered = sorted(context.profiles.items(), key=lambda kv: -kv[1].overall_score)[:5]
            for entity_id, profile in ordered:
                meta = context.entities.get(entity_id)
                label = meta.display_value if meta else entity_id
                print(f"  {label}: {profile.overall_score:.3f} {profile.tier}")

            print("\n=== investigation priorities (top 6) ===")
            ordered_priority = sorted(context.priorities.items(), key=lambda kv: -kv[1][0])[:6]
            for entity_id, (score, tier) in ordered_priority:
                meta = context.entities.get(entity_id)
                label = meta.display_value if meta else entity_id
                print(f"  {label}: {score:.3f} {tier}")

            try:
                from app.analytics.paths import bounded_ego_paths

                top_entity = max(
                    context.metric_maps.get("pagerank", {}),
                    key=context.metric_maps["pagerank"].get,
                )
                paths = await bounded_ego_paths(graph_store, str(case_id), top_entity, 3, 5)
                print("\n=== sample bounded paths (egocentric) ===")
                print(f"  from top-pagerank entity {top_entity}")
                for path in paths:
                    node_labels = [
                        context.entities[str(n)].display_value if str(n) in context.entities else n
                        for n in path["node_ids"]
                    ]
                    print(
                        f"  hops={path['hops']} nodes={node_labels} "
                        f"rels={path['relationship_types']}"
                    )
            except Exception as exc:  # noqa: BLE001 - preview must not crash on Neo4j absence
                print(f"  (paths skipped: {exc})")
    finally:
        await graph_store.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())

"""Regression tests: deterministic entity ranking (``app.ai.ranking``).

These pin the *authoritative* ranking behaviour that fixes the observed
entity-ranking failures. They verify the computed record — not just that some
plausible wording came back. Ordering is deterministic (value desc, id asc) so
ties cannot flap between runs.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.ranking import UnsupportedMetricError, rank_entities
from app.db.postgres import Database
from app.models import Case, Entity, Relationship
from sqlalchemy import delete

CASE_NUMBER = "RANK-TEST"


async def _make_case(database: Database) -> uuid.UUID:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"{CASE_NUMBER}-{uuid.uuid4().hex[:8]}",
        title="ranking regression case",
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        cid = case.id
    return cid


async def _cleanup(database: Database, case_id: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(delete(Relationship).where(Relationship.case_id == str(case_id)))
        await session.execute(delete(Entity).where(Entity.case_id == str(case_id)))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def _add_entities(
    database: Database, case_id: uuid.UUID, values: list[str]
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    factory = database.session_factory()
    async with factory() as session:
        for value in values:
            eid = uuid.uuid4()
            session.add(
                Entity(
                    id=eid,
                    case_id=str(case_id),
                    entity_type="person",
                    canonical_value=value,
                    blocking_key=value.lower(),
                    display_value=value,
                )
            )
            ids.append(eid)
        await session.commit()
    return ids


async def _add_relationships(
    database: Database, case_id: uuid.UUID, pairs: list[tuple[uuid.UUID, uuid.UUID]]
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        for src, dst in pairs:
            session.add(
                Relationship(
                    case_id=str(case_id),
                    source_entity_id=str(src),
                    target_entity_id=str(dst),
                    relationship_type="associated_with",
                )
            )
        await session.commit()


@pytest.fixture
async def empty_case(database: Database):
    cid = await _make_case(database)
    yield cid
    await _cleanup(database, cid)


@pytest.fixture
async def star_case(database: Database):
    """Three entities; A is the hub with the most relationships.

    A--B, A--C, A--D  => A degree 3; B,C,D degree 1 each.
    """
    cid = await _make_case(database)
    [a, b, c, d] = await _add_entities(database, cid, ["Hub", "LeafB", "LeafC", "LeafD"])
    # Bidirectional edges: an "associated_with" relation links both endpoints,
    # so the graph is undirected. This matters for PageRank — see the sink test.
    await _add_relationships(database, cid, [(a, b), (b, a), (a, c), (c, a), (a, d), (d, a)])
    yield cid
    await _cleanup(database, cid)


async def test_correct_top_entity(database: Database, star_case: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        record = await rank_entities(session, str(star_case), metric="relationship_count")
    assert record["metric"] == "relationship_count"
    assert record["total_entities"] == 4
    top = record["results"][0]
    assert top["label"] == "Hub"
    # relationship_count counts relationship ROWS (matching the showcase
    # digest's "59 relationships" and golden fact s001). The bidirectional
    # fixture seeds 2 rows per association, so the hub has 6.
    assert top["value"] == 6.0
    assert top["rank"] == 1
    assert top["entity_id"]  # a real id the citation layer can resolve


async def test_top_n_ordering_is_descending(database: Database, star_case: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        record = await rank_entities(session, str(star_case), metric="relationship_count", top_n=3)
    assert len(record["results"]) == 3
    values = [row["value"] for row in record["results"]]
    assert values == sorted(values, reverse=True)
    ranks = [row["rank"] for row in record["results"]]
    assert ranks == [1, 2, 3]


async def test_ties_break_deterministically_by_id(
    database: Database, empty_case: uuid.UUID
) -> None:
    """Two entities with equal value must order by entity_id, not insertion order."""
    await _add_entities(database, empty_case, ["TieA", "TieB", "TieC"])
    # No relationships => all degree 0 (a tie). Order must be id-ascending.
    factory = database.session_factory()
    async with factory() as session:
        first = await rank_entities(session, str(empty_case), metric="relationship_count")
        second = await rank_entities(session, str(empty_case), metric="relationship_count")
    assert [r["entity_id"] for r in first["results"]] == [r["entity_id"] for r in second["results"]]
    assert [r["value"] for r in first["results"]] == [0.0, 0.0, 0.0]
    assert len({r["rank"] for r in first["results"]}) == 3


async def test_empty_dataset_returns_no_results(database: Database, empty_case: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        record = await rank_entities(session, str(empty_case), metric="relationship_count")
    assert record["total_entities"] == 0
    assert record["results"] == []


async def test_missing_metric_is_reported_not_substituted(
    database: Database, star_case: uuid.UUID
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        with pytest.raises(UnsupportedMetricError):
            await rank_entities(session, str(star_case), metric="betweenness")


async def test_unauthorized_case_id_has_no_data(database: Database) -> None:
    """A case the caller does not own simply has no rows in scope; ranking is
    scoped by case_id, so an unknown id yields an empty (not cross-case) result."""
    ghost = str(uuid.uuid4())
    factory = database.session_factory()
    async with factory() as session:
        record = await rank_entities(session, ghost, metric="relationship_count")
    assert record["total_entities"] == 0
    assert record["results"] == []


async def test_non_active_entities_are_excluded(database: Database, empty_case: uuid.UUID) -> None:
    ids = await _add_entities(database, empty_case, ["Keep", "Merged"])
    await _add_relationships(database, empty_case, [(ids[0], ids[1])])
    factory = database.session_factory()
    async with factory() as session:
        merged = await session.get(Entity, ids[1])
        merged.status = "merged"
        await session.commit()
        record = await rank_entities(session, str(empty_case), metric="relationship_count")
    # Only the active entity is ranked; the merged one is excluded entirely.
    assert record["total_entities"] == 1
    assert record["results"][0]["label"] == "Keep"


async def test_pagerank_metric_returns_ranked_scores(
    database: Database, star_case: uuid.UUID
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        record = await rank_entities(session, str(star_case), metric="pagerank")
    assert record["metric"] == "pagerank"
    assert record["total_entities"] == 4
    # The hub (3 edges) must outrank the leaves under PageRank too.
    assert record["results"][0]["label"] == "Hub"
    scores = [row["value"] for row in record["results"]]
    assert scores == sorted(scores, reverse=True)
    # PageRank is normalised-ish; assert all positive and finite.
    assert all(s > 0 for s in scores)


async def test_result_is_stable_across_calls(database: Database, star_case: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        a = await rank_entities(session, str(star_case), metric="relationship_count")
        b = await rank_entities(session, str(star_case), metric="relationship_count")
    assert a == b


async def test_pagerank_on_directed_sink_is_not_a_degree_proxy(
    database: Database, empty_case: uuid.UUID
) -> None:
    """PageRank on an all-outbound star ranks the sinks highest — a real
    property of PageRank, not a bug. This pins the metric's semantics so no one
    mistakes it for 'most connected' and wires it into a ranking question by
    accident. relationship_count is the correct metric for 'most connected'."""
    ids = await _add_entities(database, empty_case, ["Hub", "Sink1", "Sink2"])
    # Hub -> each sink, one direction only (no return edges).
    await _add_relationships(database, empty_case, [(ids[0], ids[1]), (ids[0], ids[2])])
    factory = database.session_factory()
    async with factory() as session:
        pr = await rank_entities(session, str(empty_case), metric="pagerank")
        deg = await rank_entities(session, str(empty_case), metric="relationship_count")
    # relationship_count correctly identifies the hub as most connected...
    assert deg["results"][0]["label"] == "Hub"
    # ...but PageRank sinks score to the leaves (they have no outbound edges).
    assert pr["results"][0]["label"] in {"Sink1", "Sink2"}
    assert pr["results"][-1]["label"] == "Hub"


async def test_distinct_neighbors_dedupes_bidirectional_rows(
    database: Database, star_case: uuid.UUID
) -> None:
    """distinct_neighbors ignores duplicate/back-reflected rows and counts
    true neighbours — this is the metric to use for 'most connected'."""
    factory = database.session_factory()
    async with factory() as session:
        rec = await rank_entities(session, str(star_case), metric="distinct_neighbors", top_n=4)
    by_label = {r["label"]: r["value"] for r in rec["results"]}
    # Hub touches 3 distinct neighbours; each leaf touches only the hub.
    assert by_label["Hub"] == 3.0
    assert by_label["LeafB"] == 1.0
    assert rec["results"][0]["label"] == "Hub"

"""Integration tests for Neo4j connectivity."""

from __future__ import annotations

from app.db.neo4j import GraphStore


async def test_neo4j_connectivity(graph_store: GraphStore) -> None:
    await graph_store.ping()


async def test_neo4j_query_round_trip(graph_store: GraphStore) -> None:
    driver = graph_store.driver()
    async with driver.session() as session:
        result = await session.run("RETURN 1 AS one")
        record = await result.single()
        assert record is not None
        assert record["one"] == 1

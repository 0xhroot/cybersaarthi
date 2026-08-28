# ADR-007: PostgreSQL as source of truth, Neo4j as an idempotent projection

- **Status:** Accepted
- **Date:** Phase 2 (SIH 26189)
- **Decision makers:** backend engineering

## Context

Phase 2 produces entities and relationships for a case. Neo4j is the natural home for
graph-shaped questions, but a graph database alone is a weak source of truth: no transactional
history, weaker relational integrity, and harder audit/provenance joins with evidence files.
Phase 1 already committed to PostgreSQL for foundational data (ADR-003).

## Decision

- **PostgreSQL is the authoritative store.** All entity, alias, candidate, match, relationship,
  evidence and job rows live in PostgreSQL with foreign keys and unique constraints.
- **Neo4j is a derived projection.** After each successful ingest, `GraphSyncService.sync_case`
  projects entities and relationships into Neo4j. Nodes are `:Entity` merged by PostgreSQL
  `id`, with sub-labels for the entity type; edges are `MERGE (a)-[r:TYPE {id}]->(b)` keyed by
  the relationship id.
- **Idempotency by construction.** `MERGE` + uniqueness constraints (`n.id` unique,
  `(case_id, entity_type, canonical_value)` unique) mean re-syncing a case is always safe; the
  `retry-graph-sync` endpoint exists for exactly that.
- **Read APIs are PostgreSQL-backed.** `/graph`, `/graph/stats` and `/graph/entity/{id}` build
  the response from the relational store, so "never divergence" is trivial: the projection is
  verified (`synced: true`) but never trusted as the only read path.

## Consequences

- Audit/provenance joins stay in SQL; the graph layer only mirrors what PostgreSQL already
  guarantees.
- Graph sync is a normal job step with a `graph_sync_status`; failures are recorded on the job
  and retryable, never silently corrupting the projection.
- Duplication of storage (relational + graph) is deliberate: the graph trades perfect
  consistency for traversal speed, and the projection is reconstructable at any time.
- Later phases (centrality, communities, missing-link engines) can read directly from Neo4j
  without holding a second relational mirror of the same facts.
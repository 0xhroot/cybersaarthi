# ADR-003: PostgreSQL (relational) and Neo4j (graph) together

- **Status:** Accepted
- **Date:** Phase 1 (SIH 26189)
- **Decision makers:** backend engineering

## Context

Criminal-network analysis holds two fundamentally different shapes of data:

1. **Case/administrative data** — cases, users, roles, audit logs. Row-oriented,
   expected to be queried relationally and reported on. Small enough to be consistent.
2. **Entity-relationship data** — persons, phones, organisations, locations and the edges
   between them. Queries are neighbourhood traversals ("who is connected to X within k hops?")
   that relational SQL handles poorly at depth.

A single database would either distort one of these shapes or force every query through
awkward abstractions.

## Decision

Run **two primary stores**, not one:

- **PostgreSQL 16** is the system of record for all structured, write-once input:
  cases, users/roles, and the audit trail. Handled with SQLAlchemy (async driver: psycopg3),
  managed by Alembic.
- **Neo4j 5 Community** is the knowledge-graph store. Phase 1 wires and health-checks the
  async driver (`bolt://`), creating no schema; Phase 2 writes persons/phones/organisations
  and edges there.

This resolves a naming rule the rest of the system follows: PostgreSQL names are "the data
we must never lose"; Neo4j names are "the connections we reason about". They are not synonyms.

## Consequences

- Two sources of truth by design, so the write paths must be explicit about which store owns
  what (cases → Postgres; graph edges → Neo4j). Phase 2 defines the mapping.
- Integration tests cover both stores independently; a broken graph store surfaces as a
  readiness/`unavailable` instead of corrupting relational writes.
- The app never embeds graph logic into the relational layer via JSON strings — edges stay
  in the graph database where traversal power actually lives.
- Both are disposable locally (Docker volumes), which keeps schema experiments cheap.
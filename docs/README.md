# CyberSaarthi Documentation

This directory holds the project's technical documentation. The root
[`README.md`](../README.md) is the primary entry point and gives a high-level
overview; use this index to jump straight to the deep material.

## Architecture

- [Android ↔ Backend connectivity](architecture/android-connectivity.md) — LAN discovery, QR pairing trust, liveness heartbeat, offline field capture

## Architecture decision records (ADRs)

- [001 — Modular monolith](adr/001-modular-monolith.md)
- [002 — Docker-first development](adr/002-docker-first-development.md)
- [003 — PostgreSQL and Neo4j](adr/003-postgresql-and-neo4j.md)
- [004 — Local object storage](adr/004-local-object-storage.md)
- [005 — Evidence ingestion & provenance](adr/005-evidence-ingestion-provenance.md)
- [006 — Entity resolution](adr/006-entity-resolution.md)
- [007 — Postgres source of truth, Neo4j projection](adr/007-postgres-source-of-truth-neo4j-projection.md)

## Frontend & API

- [API / frontend contract](../backend/docs/frontend-contract.md) (in `backend/docs/`)
- [Frontend design system](../frontend/docs/design-system.md) (in `frontend/docs/`)
- [Frontend final report](../frontend/docs/frontend-final-report.md) (in `frontend/docs/`)

## Screenshots

- [`screenshots/`](screenshots/) — application screenshots (also embedded in the root README)

## Tooling

- [`scripts/rehearse_sih_demo.mjs`](scripts/rehearse_sih_demo.mjs) — automated SIH demo rehearsal checks
- [`scripts/run_sih_seed.py`](scripts/run_sih_seed.py) — deterministic SIH demo seed script

## Contributing & security

- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Code of conduct](../CODE_OF_CONDUCT.md)

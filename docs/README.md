# CyberSaarthi Documentation

This directory holds the project's technical documentation. The root
[`README.md`](../README.md) gives a high-level overview; use this index to jump
straight to the deep material.

## Architecture

| Document | Covers |
| --- | --- |
| [Phase 1](../README.md) | Foundation: API, configuration, storage primitives |
| [Phase 2](architecture/phase-2.md) | Evidence pipeline: validation, parsing, extraction, normalization |
| [Phase 3](architecture/phase-3.md) | Investigation engine: entity resolution, analytics, findings |
| [Phase 4](architecture/phase-4.md) | Productization: auth, RBAC, audit, token revocation, frontend |
| [Phase 4 — Final report](architecture/phase-4-final-report.md) | Consolidated delivery report |
| [Phase 4 — Security checklist](architecture/phase-4-security-checklist.md) | Security controls and verification checklist |

## Architecture decision records (ADRs)

- [001 — Modular monolith](adr/001-modular-monolith.md)
- [002 — Docker-first development](adr/002-docker-first-development.md)
- [003 — PostgreSQL and Neo4j](adr/003-postgresql-and-neo4j.md)
- [004 — Local object storage](adr/004-local-object-storage.md)
- [005 — Evidence ingestion & provenance](adr/005-evidence-ingestion-provenance.md)
- [006 — Entity resolution](adr/006-entity-resolution.md)
- [007 — Postgres source of truth, Neo4j projection](adr/007-postgres-source-of-truth-neo4j-projection.md)

## Audit & security

- [Executive summary](audit/PROJECT_AUDIT_EXECUTIVE_SUMMARY.md)
- [Full audit report](audit/PROJECT_AUDIT.md)
- [Audit metrics](audit/PROJECT_AUDIT_METRICS.md)
- [Audit test results](audit/PROJECT_AUDIT_TEST_RESULTS.txt)
- Machine-readable: [`PROJECT_AUDIT.json`](audit/PROJECT_AUDIT.json)

## Frontend & API

- [API / frontend contract](backend/docs/frontend-contract.md) (in `backend/docs/`)
- [Frontend design system](frontend/docs/design-system.md) (in `frontend/docs/`)
- [Frontend final report](frontend/docs/frontend-final-report.md) (in `frontend/docs/`)

## Contributing & security

- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Code of conduct](../CODE_OF_CONDUCT.md)

> Note: `docs/development/` is reserved for developer notes and is currently
> empty by design.

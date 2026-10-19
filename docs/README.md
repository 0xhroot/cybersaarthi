# CyberSaarthi Documentation

This directory holds the project's technical documentation. The root
[`README.md`](../README.md) is the primary entry point and gives a high-level
overview; use this index to jump straight to the deep material.

## Architecture diagrams (Mermaid, render on GitHub)

- [Diagram index](architecture/README.md) — start here; lists all eight diagrams
  and the invariants they encode
- [System architecture](architecture/system-architecture.md)
- [AI request lifecycle](architecture/ai-request-lifecycle.md)
- [Evidence ingestion & custody](architecture/evidence-ingestion-custody.md)
- [Entity resolution & timeline](architecture/entity-resolution-timeline.md)
- [Financial flow & cross-case](architecture/financial-flow-cross-case.md)
- [Multilingual & forensics triage](architecture/multilingual-forensics.md)
- [Report audit](architecture/report-audit.md)
- [Deployment & local model setup](architecture/deployment-setup.md)
- [Android ↔ Backend connectivity](architecture/android-connectivity.md) — LAN discovery, QR pairing trust, liveness heartbeat, offline field capture

## AI features (the ten capabilities)

- [AI feature status matrix](ai/FEATURE_STATUS.md) — every capability with its
  exact boundary, routes, panels, tests and measured limits
- [AI architecture](ai/ARCHITECTURE.md) · [AI API reference](ai/API.md)
- [Local model setup](ai/LOCAL_MODEL_SETUP.md) — obtain & verify the model,
  run llama.cpp, configuration reference, verification ladder
- [Evaluation](ai/EVALUATION.md) — gates, benchmarks, how to re-run them
- [Troubleshooting (AI)](ai/TROUBLESHOOTING.md)
- [Security & isolation](ai/SECURITY_AND_ISOLATION.md) · [performance benchmarks](ai/PERFORMANCE_BENCHMARKS.md)
- Design/audit history: [PHASE_3_DESIGN](ai/PHASE_3_DESIGN.md) ·
  [PHASE_4_DESIGN](ai/PHASE_4_DESIGN.md) · [PHASE_5_6_7_PLAN](ai/PHASE_5_6_7_PLAN.md) ·
  [IMPLEMENTATION_PROGRESS](ai/IMPLEMENTATION_PROGRESS.md) · [DELIVERY_REPORT](ai/DELIVERY_REPORT.md) ·
  [audits](ai/IMPLEMENTATION_AUDIT.md) (also AI_EXPANSION_AUDIT, EVIDENCE_INTELLIGENCE_AUDIT,
  RECOVERY_AUDIT, CASE_RETRIEVAL_DIAGNOSIS, ACCURACY_PERFORMANCE_PLAN, TRAINING_PIPELINE)

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

Repository scripts (all safe to re-run; none overwrite `.env`, delete data,
or reset databases):

- [`scripts/check_prereqs.sh`](../scripts/check_prereqs.sh) — verify Docker/Node/Python/GPU/disk before you start
- [`scripts/healthcheck.sh`](../scripts/healthcheck.sh) — verify a running stack (compose, backend, readiness, AI runtime, frontend)
- [`scripts/ai/setup_model.sh`](../scripts/ai/setup_model.sh) — fetch the model from its official source and verify SHA-256 (the only model download step)
- [`scripts/ai/setup_runtime.sh`](../scripts/ai/setup_runtime.sh) · [`scripts/ai/verify_model.sh`](../scripts/ai/verify_model.sh) — llama.cpp binaries & end-to-end runtime proof
- [`scripts/rehearse_sih_demo.mjs`](scripts/rehearse_sih_demo.mjs) — automated SIH demo rehearsal checks
- [`scripts/capture_ai_screenshots.mjs`](scripts/capture_ai_screenshots.mjs) — regenerate the README AI screenshot gallery from the real UI
- [`scripts/run_sih_seed.py`](scripts/run_sih_seed.py) — deterministic SIH demo seed script

## Contributing & security

- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Code of conduct](../CODE_OF_CONDUCT.md)

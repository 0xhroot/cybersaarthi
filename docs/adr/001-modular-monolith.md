# ADR-001: Modular Monolith Backend

- **Status:** Accepted
- **Date:** Phase 1 (SIH 26189)
- **Decision makers:** backend engineering

## Context

CyberSaarthi must grow from a foundation into an analysis-heavy system: ingestion,
knowledge-graph building, network analytics, and a frontend. For a small team building to a
hackathon/short-cycle deadline, we must avoid two failure modes:

1. A distributed system that cannot be run or tested by one person on one machine.
2. A monolith that becomes a tangle of imports with no boundaries, where later phases
   require rewrites.

We also face hard constraints: no repository secrets, everything reproducible via Docker,
and a validation procedure that must pass on a clean clone.

## Decision

Build a **modular monolith**:

- One FastAPI application process, organised by vertical slice:
  `api → services → repositories → db/models`, with `core` as the shared foundation.
- Inter-module communication is plain Python calls (no RPC, no queues).
- Horizontal seams for the future are real but un-looked: `repositories/` isolate data access;
  `services/` isolate use cases; each database client is a standalone wrapper class.
- The app is constructed by `create_app()` and reassembled per-process (startup, tests, scripts)
  from the same code path.

## Consequences

- One image, one `uvicorn` process — trivial to run, debug, and smoke-test.
- Phases 2+ extend modules in place; if a future split (e.g., a worker service for
  analytics) becomes justified, the seams are already at the client/service boundaries.
- Risk of coupling growth — mitigated by enforcing import direction in reviews and keeping
  `db/` clients, `repositories/`, and `services/` free of framework imports.
- Testing stays cheap: unit tests need no infrastructure; only the integration suite does.
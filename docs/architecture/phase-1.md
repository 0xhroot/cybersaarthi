# Phase 1 — Foundation

This is the architecture reference for Phase 1 of CyberSaarthi. It is a *system snapshot*:
accurate for the code as it exists on `main`. Motivations and trade-offs behind each choice
live in the ADRs (`docs/adr/`).

## Goals

- A backend a single engineer can run and test locally with zero host prerequisites.
- Everything reproducible from a clean clone via Docker (`make up`).
- Long-lived modules that later phases grow in place (no rewrites, no premature splits).

## Non-goals (explicitly out of scope for Phase 1)

- NLP, network analytics, "AI" runtime behaviour, model serving.
- Any frontend beyond the API's own `/docs`.
- Blockchain/ledger features.
- Authentication endpoints and RBAC enforcement (the data model is ready, endpoints are Phase 3).

## Topology

```
                    ┌─────────────────────────────────────────┐
   developer        │  docker compose                         │
   browser  ──8000──▶ backend  (FastAPI, uvicorn, appuser uid)│
   (curl/docs)      │   │                                      │
                    │   │ (S3 API)       (async drivers)      │
                    │   ▼                  │                  │
                    │ minio ←─9000 ─ minio-init (bucket)      │
                    │           postgres :5432                │
                    │           neo4j    :7687/7474           │
                    │           redis    :6379                │
                    └─────────────────────────────────────────┘
```

All inter-service traffic uses the Compose network. Host ports are only for the developer:
`8000` (API), plus `5432/7687/7474/6379/9000/9001` (debugging via local tools).

## Backend module map

```
app/
├── api/
│   ├── routes/health.py   GET /health, GET /ready
│   ├── router.py          /api/v1 prefix; future routers mount under it
│   ├── errors.py          { "error": {code, message} } envelope
│   └── middleware.py      security response headers
├── core/
│   ├── config.py          pydantic-settings; fails fast in production
│   ├── logging.py         structured (JSON) logging
│   └── security.py        bcrypt hash/verify
├── db/
│   ├── postgres.py        async SQLAlchemy engine + session factory
│   ├── neo4j.py           lazy async driver (GraphStore)
│   ├── redis.py           lazy async client (Cache)
│   └── storage.py         lazy S3 client (Storage)
├── models/                SQLAlchemy ORM (UUID PKs, audit-safe timestamps)
├── repositories/          narrow data-access slices
├── schemas/               Pydantic request/response models
├── services/              use-case logic (readiness, users)
└── main.py                create_app(), lifespan, exception handlers
```

Dependency direction: `api → services → repositories → db/models`, `core` shared everywhere.
Phase 1 keeps the monolith: business modules communicate via in-process Python calls.

## Data model

PostgreSQL (relational — fits rows-first case/activity data):

- `cases` — investigation containers (unique case number, status check: open/in_progress/closed/archived)
- `users`, `roles`, `user_roles` — identity & authorization-ready (no endpoints yet)
- `audit_logs` — append-only action trail with JSONB `metadata`

Neo4j is started and connected but holds no Phase 1 schema; the graph (persons, phones,
organisations, relationships) is Phase 2.

## Configuration

Single source of truth: `app/core/config.py` (`Settings`). Every value maps to an environment
variable; Compose injects them by name. Loaded once per process via `get_settings()` (lru_cache).

Production guard: if `APP_ENV=production` and any secret is empty or a known placeholder,
the process refuses to start. Deliberate: better a crash than silent weak credentials.

## Readiness model

- `/health` — no checks; proves the process responds.
- `/ready` — 4 probes run concurrently by `ReadinessService`; result is a 200 with per-service
  statuses, or 503 with each dependency marked `ok`/`unavailable`. Endpoints are the only
  consumers; startup only *logs* dependency state (see `main.py::lifespan`).

## Migration flow

- Files: `backend/migrations/versions/` (autogenerate with `make migration MSG=...`).
- Apply: automatically at container start (`entrypoint.sh` → `alembic upgrade head`), and
  manually via `make migrate`. Down-path is tested: every revision ships `downgrade()`.

## Testing strategy

| Suite | Location | Requires infra | Runs on clean dev host |
|---|---|---|---|
| unit | `tests/unit/` | no | yes (`make test-unit`) |
| api | `tests/api/` | no (fakes + fixtures) | yes |
| integration | `tests/integration/` | `make up` | auto-skipped with a hint when infra is down (`make test`) |

pytest-asyncio runs one event loop per session. Why: the Neo4j/Redis drivers pool connections;
per-test loops make pooled connections unsafe to reuse ("Future attached to a different loop").
A single session loop mirrors uvicorn's runtime.

## Validation performed (Phase 1 exit criteria)

From a clean clone, with no host tooling beyond Docker:

1. `docker compose build --no-cache` — succeeds (all deps pinned, no build-time DNS failure).
2. `docker compose up -d` — all five services healthy.
3. Entrypoint auto-applied the initial migration (`alembic_version` at `e308a313166d`).
4. `GET /api/v1/health` → `{"status":"ok","service":"cybersaarthi","version":"0.1.0"}`.
5. `GET /api/v1/ready` → 200, all of `postgres/neo4j/redis/object_storage` = `ok`.
6. `GET /docs` → 200 (OpenAPI describes `/api/v1/{health,ready}`).
7. `make test` → 31 passed (unit + api + live integration).
8. `make lint` / `make format-check` / `make typecheck` → clean (ruff, mypy: 30 files).

## Known limitations

- Credentials match dev defaults across non-API services (documented in `.env.example`).
  Swap all secrets before any shared/prod-like deployment.
- The object-storage and Redis clients manage their own connection pools; both are closed on
  shutdown via the lifespan.
- Host-specific tooling (rootless Docker workarounds) is intentionally outside the repo.
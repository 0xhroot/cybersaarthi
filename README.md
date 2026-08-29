# CyberSaarthi

Deterministic criminal-network analysis for investigators — evidence ingestion, entity
resolution, a knowledge graph, and an explainable analytics engine (patterns, hypotheses,
findings, Network DNA, priorities, paths).

PostgreSQL is the source of truth; Neo4j is an idempotent graph projection used only for
bounded path traversal. Every analytical score is a deterministic function of real ingested
evidence — there is no fake AI, no random scoring, and no fabricated confidence.

- **System:** criminal network analysis (SIH 26189 / team DASH)
- **Phase 1:** API foundation + local Docker infrastructure
- **Phase 2:** evidence pipeline (upload → validation → parsing → extraction → resolution →
  relationships → graph projection → graph query APIs)
- **Phase 3:** investigation intelligence (deterministic analytics, hypotheses, findings,
  Network DNA, priorities, relationship strength, paths)

## Repository layout

```
backend/
  app/
    api/            routers, errors, security middleware, dependencies
    analytics/      deterministic analytics engine (graph, communities, centrality,
                    patterns, hypotheses, strength, network_dna, priority, paths,
                    explanations, findings)
    core/           settings, logging, security
    db/             PostgreSQL, Neo4j, Redis, MinIO clients
    models/         SQLAlchemy models
    repositories/   data-access layer
    schemas/        Pydantic schemas
    services/       validation, parsing, extraction, nlp, normalization, resolution,
                    relationships, graph_sync, ingestion, entity_service, readiness
  migrations/       Alembic migrations (async)
  scripts/          seed_demo.py (deterministic demo case), preview_analytics.py
  tests/            unit, api, integration suites
docs/               architecture docs + decision records (adr/001..007)
frontend/           placeholder — no implementation yet (future)
ml/                 placeholder — no implementation yet (future)
infra/              placeholder — no implementation yet (future deployment manifests)
data/               placeholder — no sample data shipped
```

## Stack

| Component | Purpose | Technology |
|---|---|---|
| backend | Application server (modular monolith) | FastAPI + Python 3.12 |
| postgres | Source of truth (cases, evidence, entities, relationships, findings, runs) | PostgreSQL 16 |
| neo4j | Knowledge-graph projection (idempotent sync, bounded path traversal) | Neo4j 5 Community |
| redis | Cache | Redis 7 |
| minio | S3-compatible object storage (evidence) | MinIO |
| migrations | Schema management | Alembic (async) |

## Quick start

Prerequisites: Docker with the Compose plugin.

```sh
cp .env.example .env       # dev-safe defaults; never commit .env
docker compose up -d       # build + start postgres, neo4j, redis, minio, backend
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
make seed                  # deterministic demo case (DEMO-2026-001)
```

On cold start the backend entrypoint runs `alembic upgrade head` automatically, so
migrations apply before the API accepts traffic.

### Trying the analytics engine

With the demo case seeded, open the Swagger UI at `http://localhost:8000/docs` or run:

```sh
# Live, deterministic analytics over the demo case:
curl 'http://localhost:8000/api/v1/cases/$(<case-id>)/analytics/summary'
# Persist an auditable analytics run (metrics + communities + profiles + findings):
curl -X POST 'http://localhost:8000/api/v1/cases/$(<case-id>)/analytics/run'
# Inspect persisted findings:
curl 'http://localhost:8000/api/v1/cases/$(<case-id>)/findings'
```

`make seed` prints the case id; `backend/scripts/preview_analytics.py` prints a headless
summary of the pipeline for the seeded case.

### Local development outside Docker (optional)

All `make` targets run inside the backend container and need no host Python. If you prefer
a host-side virtual environment:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e "backend/.[dev]"
```

## Make targets

```sh
make help          # list targets
make up            # build + start the full stack
make down          # stop (keeps volumes)
make down-v        # stop and delete volumes (destructive)
make ps            # service status
make logs          # follow all logs
make seed          # seed the deterministic demo case
make test          # full suite incl. integration (needs `make up`)
make test-unit     # unit + api only
make lint          # ruff check
make format        # ruff format
make format-check  # verify formatting
make typecheck     # mypy
make migrate       # apply pending migrations
make migration MSG="add persons table"   # autogenerate a migration
make shell         # shell in the backend container
```

## API surface

All routes are versioned under `/api/v1`.

**Health & readiness**

- `GET /api/v1/health` — liveness.
- `GET /api/v1/ready` — readiness probes for PostgreSQL, Neo4j, Redis and MinIO
  (`200` all healthy, else `503`).

**Evidence ingestion (Phase 2)**

- `POST /cases/{id}/evidence` — upload a CSV/JSON/TXT evidence file (size cap, SHA-256
  fingerprinting, format/encoding sniff; `409` on duplicate content).
- `GET /cases/{id}/evidence` — list evidence files.
- `POST /cases/{id}/ingest` — run the ingestion pipeline for one evidence file.
- `GET /cases/{id}/ingest-jobs` — list ingestion jobs and their graph-sync status.
- `POST /cases/{id}/ingest/{job_id}/retry-graph-sync` — re-project a case to Neo4j.

**Entities & graph (Phase 2)**

- `GET /cases/{id}/entities` · `GET /cases/{id}/entities/{entity_id}` · `GET /cases/{id}/relationships`
  · `GET /cases/{id}/resolution/review`
- `GET /cases/{id}/graph` · `GET /cases/{id}/graph/stats` · `GET /cases/{id}/graph/entity/{entity_id}`

**Analytics (Phase 3)** — live read endpoints recompute the deterministic pipeline on demand;

- `GET /cases/{id}/analytics/summary` · `centrality` · `communities` · `network-dna` ·
  `priorities` · `strength` · `patterns` · `hypotheses`
- `GET /cases/{id}/analytics/entities/{entity_id}/analytics` — per-entity profile
- `GET /cases/{id}/analytics/paths` · `/paths/entity/{entity_id}` — bounded Neo4j paths
- `POST /cases/{id}/analytics/run` — persist an auditable analytics run
- `GET /cases/{id}/analytics/runs` — run history

**Findings (Phase 3)**

- `GET /cases/{id}/findings` — persisted findings, newest first, with `run_id` snapshots
  per analytics run; filter by `type`, `status`, `severity`, `run_id`.
- `GET /cases/{id}/findings/stats` · `GET /cases/{id}/findings/{finding_id}`
- `PATCH /cases/{id}/findings/{finding_id}/status` — analyst review
  (`NEW`/`REVIEWED`/`DISMISSED`/`CONFIRMED`; never auto-assigned).

Errors use a single envelope: `{"error": {"code": "NOT_FOUND", "message": "..."}}`.

## Security posture

- Containers run as a non-root user (`USER appuser` in the API image).
- `.env` is git-ignored; the production profile refuses to start with placeholder secrets
  in `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `S3_SECRET_KEY` or `SECRET_KEY`.
- Password hashing helpers exist for the (deferred) auth phase; nothing is hashed today.
- Responses carry security headers (X-Content-Type-Options, X-Frame-Options,
  Referrer-Policy).
- Uploads are capped, size-checked while streaming, and stored under server-generated
  object keys (user filenames are sanitized).
- SQL/Cypher access is parameterized; relationship types are constrained to a canonical
  allowlist.
- There is no authentication layer yet (deferred — see below). Every endpoint is
  currently unauthenticated.

## Deferred work (not part of Phase 3)

- **Authentication / RBAC** — `User`, `Role`, `UserRole`, bcrypt helpers and
  `UserService`/`UserRepository` are scaffolding only; no auth endpoints exist yet.
- **Frontend** — `frontend/` is an empty placeholder (Vite UI planned for investigators).
- **Background ingestion** — `POST /ingest` runs synchronously in the request today
  (single-worker local mode); background execution is a later-phase concern.
- **Analytics approximation** — exact graph algorithms run below
  `ANALYTICS_GRAPH_NODE_CAP` (default 2000 nodes); larger cases fall back to sampled
  approximations, which the API reports explicitly in `approximation_notice` and per-row
  `exact` flags.

Design decisions are captured in `docs/architecture/phase-*.md` and the ADRs under
`docs/adr/` (001–007).
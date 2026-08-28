# CyberSaarthi

AI-powered criminal network analysis for law enforcement — Phases 1 + 2.

CyberSaarthi is a platform to ingest investigation data (persons, phones, organisations,
locations, events), build a knowledge graph, and surface criminal networks. Phase 1 shipped a
clean, testable foundation. Phase 2 ships the evidence-ingestion pipeline: upload → validation →
parsing → entity/relationship extraction → entity resolution → PostgreSQL source of truth →
idempotent Neo4j projection → graph query APIs. No frontend, no analytics scoring, no blockchain.

- **System:** criminal network analysis (SIH 26189 / team DASH)
- **Phase 1 scope:** backend foundation + local infrastructure, validated end-to-end in Docker
- **Phase 2 scope:** data intelligence pipeline (see `docs/architecture/phase-2.md`)

## Repository layout

```
backend/            FastAPI modular monolith (Phases 1 + 2)
  app/
    api/            routers, errors, middleware, phase-2 dependencies
    core/           settings, logging, security
    db/             PostgreSQL, Neo4j, Redis, MinIO clients
    models/         SQLAlchemy models
    repositories/   data-access layer
    schemas/        Pydantic schemas
    services/       phase 1 (readiness, users, security)
                    phase 2 (validation, parsing, extraction, nlp,
                             normalization, resolution, relationships,
                             graph_sync, ingestion, entity_service)
  migrations/       Alembic migrations
  scripts/          seed_demo.py (deterministic demo case)
  tests/            unit, api, integration suites
frontend/           placeholder (Phase 3+)
ml/                 placeholder (analytical models, Phase 3)
infra/              placeholder (deployment manifests, Phase 4)
data/               placeholder (sample data)
docs/               architecture docs + decision records
tests/              repository-level test vectors (future)
```

## Stack

| Component | Purpose | Technology |
|---|---|---|
| backend | Application server (modular monolith) | FastAPI + Python 3.12 |
| postgres | Source of truth (cases, evidence, entities, relationships, jobs) | PostgreSQL 16 |
| neo4j | Knowledge-graph projection (idempotent sync) | Neo4j 5 Community |
| redis | Cache + background job coordination (later phases) | Redis 7 |
| minio | S3-compatible object storage (evidence/artefacts) | MinIO |
| migrations | Schema management | Alembic (async) |

## Quick start

Prerequisites: Docker with the Compose plugin.

```sh
cp .env.example .env       # dev-safe defaults; never commit .env
docker compose up -d --build
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
docker compose exec backend python -m scripts.seed_demo   # deterministic demo case
```

Everything you need is also one `make` target away:

```sh
make help          # list targets
make up            # build + start the full stack
make down          # stop (keeps volumes)
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

On cold start the backend entrypoint runs `alembic upgrade head`, so migrations apply
automatically before the API accepts traffic.

## Services on this machine

| Service | Address |
|---|---|
| API | http://localhost:8000 (OpenAPI at `/docs`) |
| PostgreSQL | localhost:5432 |
| Neo4j | localhost:7474 (browser) / bolt://localhost:7687 |
| Redis | localhost:6379 |
| MinIO | http://localhost:9000 (console :9001) |

All configuration comes from environment variables (`.env` in development). Service-to-service
traffic uses the Compose network only — no container ever connects to the host loopback.

## API

All routes are versioned under `/api/v1`.

Phase 1 (foundation):

- `GET /api/v1/health` — liveness: process is up.
- `GET /api/v1/ready` — readiness: probes PostgreSQL, Neo4j, Redis and MinIO; returns
  `200 {"status":"ready",...}` when all are healthy and `503 {"status":"not_ready",...}`
  otherwise, with a per-service status map.

Phase 2 (ingestion + graph):

- `POST /cases/{id}/evidence` — upload a CSV/JSON/TXT evidence file (validated, SHA-256
  fingerprinted, stored in MinIO; `409` on duplicate content).
- `GET /cases/{id}/evidence` — list evidence files.
- `POST /cases/{id}/ingest` — run the ingestion pipeline for one evidence file (`{"evidence_id": ...}`);
  returns the ingestion job (status/stage/errors/`graph_sync_status`).
- `GET /cases/{id}/ingest-jobs` — list jobs.
- `POST /cases/{id}/ingest/{job_id}/retry-graph-sync` — re-project the case to Neo4j.
- `GET /cases/{id}/entities` — paginated entity list (filter by `entity_type`, `status`, `search`).
- `GET /cases/{id}/entities/{entity_id}` — entity detail with aliases and context.
- `GET /cases/{id}/relationships` — relationships for the case.
- `GET /cases/{id}/resolution/review` — candidates awaiting analyst review.
- `GET /cases/{id}/graph` — full case graph: `{"case_id", "nodes", "edges"}`.
- `GET /cases/{id}/graph/stats` — node/edge counts + type breakdowns + `synced` flag.
- `GET /cases/{id}/graph/entity/{entity_id}` — ego-graph centred on one entity.

Errors are single-structured envelopes:

```json
{"error": {"code": "NOT_FOUND", "message": "Not Found"}}
```

## Security posture

- Containers run as a non-root user; the API image sets `USER appuser`.
- `.env` is git-ignored; production refuses to start with placeholder secrets (`change-me`,
  `password`, ...) in `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `S3_SECRET_KEY` or `SECRET_KEY`.
- Passwords are stored only as bcrypt hashes (`app/core/security.py`).
- Responses carry basic security headers (HSTS, X-Content-Type-Options, frame/GUIDE policies).
- Secrets are never logged.

## Next phases

1. Analytical models (NLP, network algorithms: centrality, communities, suspicious patterns,
   Network DNA, missing-link engines) behind worker processes fed by Redis.
2. Frontend (Vite) for investigators; evidence upload to MinIO.
3. Auth tokens, RBAC on the User/Role model, audit trail via `audit_logs`.

Design decisions are captured in `docs/` and the ADRs under `docs/adr/` (001–007).
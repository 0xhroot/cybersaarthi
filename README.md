# CyberSaarthi

AI-powered criminal network analysis for law enforcement — Phase 1: foundation.

CyberSaarthi is a platform to ingest investigation data (persons, phones, organisations,
locations, events), build a knowledge graph, and surface criminal networks. Phase 1 ships a
clean, testable foundation only: no analytical/NLP features, no frontend, no blockchain.

- **System:** criminal network analysis (SIH 26189 / team DASH)
- **Phase 1 scope:** backend foundation + local infrastructure, validated end-to-end in Docker

## Repository layout

```
backend/            FastAPI modular monolith (Phase 1)
  app/
    api/            routers, errors, middleware
    core/           settings, logging, security
    db/             PostgreSQL, Neo4j, Redis, MinIO clients
    models/         SQLAlchemy models
    repositories/   data-access layer
    schemas/        Pydantic schemas
    services/       business logic (readiness, users)
  migrations/       Alembic migrations
  tests/            unit, api, integration suites
frontend/           placeholder (Phase 3+)
ml/                 placeholder (Phase 2 pipelines)
infra/              placeholder (deployment manifests, Phase 4)
data/               placeholder (sample data)
docs/               architecture decision records
tests/              repository-level test vectors (future)
```

## Stack

| Component | Purpose | Technology |
|---|---|---|
| backend | Application server (modular monolith) | FastAPI + Python 3.12 |
| postgres | Relational store (cases, users, roles, audit) | PostgreSQL 16 |
| neo4j | Knowledge graph (Phase 2+) | Neo4j 5 Community |
| redis | Cache + background job coordination (Phase 2+) | Redis 7 |
| minio | S3-compatible object storage (evidence/artefacts) | MinIO |
| migrations | Schema management | Alembic (async) |

## Quick start

Prerequisites: Docker with the Compose plugin.

```sh
cp .env.example .env       # dev-safe defaults; never commit .env
docker compose up -d --build
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
```

Everything you need is also one `make` target away:

```sh
make help          # list targets
make up            # build + start the full stack
make down          # stop (keeps volumes)
make ps            # service status
make logs          # follow all logs
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

## API (Phase 1)

All routes are versioned under `/api/v1`.

- `GET /api/v1/health` — liveness: process is up.
- `GET /api/v1/ready` — readiness: probes PostgreSQL, Neo4j, Redis and MinIO; returns
  `200 {"status":"ready",...}` when all are healthy and `503 {"status":"not_ready",...}`
  otherwise, with a per-service status map.

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

## Phase 2+ direction

1. Data ingestion + entity models, knowledge-graph writes (Neo4j), relationship extraction.
2. Analytical models (NLP, network algorithms) behind worker processes fed by Redis.
3. Frontend (Vite) for investigators; evidence upload to MinIO.
4. Auth tokens, RBAC on the User/Role model, audit trail via `audit_logs`.

Design decisions behind Phase 1 are captured in `docs/` and the ADRs under `docs/adr/`.
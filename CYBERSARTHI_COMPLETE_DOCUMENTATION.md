# CYBERSAARTHI — Complete Project Documentation

> **Cyber Fraud Recovery & Evidence Intelligence Platform** — Smart India Hackathon submission.
> **Motto:** *Connect the evidence. Understand the network. Recover the truth.*
> **Pipeline:** `Evidence → Entity Resolution → Knowledge Graph → Analytics → Decisions`

This document is a single, self-contained reference that explains **the whole system** — every component,
every file, every screen, and how everything connects — so that any engineer or AI agent can understand the
project end-to-end without reading the codebase first.

---

## 1. What CyberSaarthi Is

CyberSaarthi is a **self-hosted, investigator-centric cyber-fraud investigation and evidence-management
platform**. It helps law-enforcement investigators turn fragmented digital evidence (call records, bank
statements, victim statements, device data, transactions) into **connected, explainable intelligence**.

Concretely it provides:

| Capability | What it does |
|---|---|
| Case management | Lifecycle, severity, status, archiving, membership, per-case visibility |
| Victim intelligence | First-class victim records (profile, incident, financial impact, recovery) |
| Person / suspect intelligence | Resolved persons, phones, vehicles, organizations, accounts, locations, documents, events |
| Evidence ingestion | Multipart upload, SHA-256 integrity, duplicate detection, MinIO object storage, provenance |
| Entity resolution | Deterministic normalization, blocking keys, fuzzy scoring → canonical entities |
| Knowledge graph | Case-scoped Neo4j projection synced idempotently from PostgreSQL |
| Analytics | Centrality, communities, network DNA, priorities, strength, paths, patterns, hypotheses |
| Findings | Explainable, human-reviewed output from the analytics engine |
| IoT subsystem | Field-device + telemetry-event backend foundation |
| Field app (Android) | Offline-first evidence capture, hashing, signing, packaging, transfer |
| Security | JWT, bcrypt, RBAC, token revocation, throttling, audit trail, IDOR guards |

**Core architecture decision:** *PostgreSQL is the source of truth; Neo4j is an idempotent graph projection.*
Victim and IoT data are first-class PostgreSQL subsystems that deliberately live **outside** the Neo4j projection.

---

## 2. System Architecture & How Components Connect

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PRESENTATION LAYERS                              │
│                                                                             │
│  React 19 / Vite / TS        Android Field Agent Kotlin/Compose            │
│  (investigator web UI)       (offline-first evidence capture)              │
│        │  Bearer JWT over HTTP                     │                        │
└────────┼───────────────────────────────┬───────────┼────────────────────────┘
         │ HTTPS /api/v1                 │  HTTPS (multipart packages)
         ▼                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    BACKEND API LAYER — FastAPI (app/main.py)                │
│   19 routers under /api/v1 · async SQLAlchemy · Pydantic v2 validation      │
│   Middleware: observability · security headers · CORS                       │
└──────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER (business rules)                            │
│  ingestion · extraction · normalization · resolution · relationships ·       │
│  graph_sync · analytics engine · findings · hypotheses · reporting ·         │
│  package_verification · provenance · throttling · token · users · audit      │
└──────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│   REPOSITORY LAYER (ORMs)            │   ANALYTICS LAYER (deterministic)     │
│  entity · evidence · relationship ·  │  graph, centrality, communities,      │
│  user · victim · audit · analytics   │  network_dna, strengths, priorities,  │
└──────────────────────────────────────┼───────────────────────────────────────┘
                                       ▼
┌──────────────┬──────────────┬───────────────┬────────────────────────────────┐
│  PostgreSQL   │   Neo4j      │    MinIO      │      Redis                     │
│  source of    │  graph       │  evidence     │  token revocation · throttle   │
│  truth        │  projection  │  objects      │  · cache                       │
└──────────────┴──────────────┴───────────────┴────────────────────────────────┘
```

### Data flow of an evidence file (the heart of the system)

```
1. Investigator uploads call-records CSV  ──►  POST /cases/{id}/evidence
2. Backend sniffs format, SHA-256 fingerprint, size cap, stores bytes in MinIO
   (cases/<case_id>/<evidence_id>/<filename>), inserts EvidenceFile row.
      ├─ duplicate (same sha256 in case)  ──► HTTP 409 rejected
3. POST evidence/{id}/ingest  →  IngestionJob (pending→running)
4. IngestionService: download bytes → parse (CSV/JSON/TXT) → per record:
      a. create idempotent SourceRecord
      b. extract mentions (field rules + regex rules + spaCy NER)
      c. normalize values (phones, vehicles, accounts, persons, orgs, ...)
      d. resolve to canonical Entity   (blocking key → fuzzy+context score)
            ├─ score ≥ 92  → auto_match link to existing entity
            ├─ score ≥ 78  → link candidate into REVIEW queue
            └─ otherwise   → create NEW entity
      e. extract typed relationships (called, owns, works_for, ...)
      f. persist Relationship + RelationshipEvidence (provenance links)
5. GraphSyncService: idempotently MERGE nodes/edges into Neo4j case sub-graph
6. Job → completed; evidence marked parsed
7. Readiness of projections at: GET /cases/{id}/graph/stats  (graph_synced)
8. Analytics engine computes explainable metrics/findings from PG (source of truth)
```

---

## 3. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend language | TypeScript | 5.7 |
| Frontend framework | Vite + React | 19 / 6 |
| UI stack | React Router 7 · TanStack Query 5 · Zustand 5 · Tailwind CSS 4 · Radix UI · Cytoscape 3.31 · Framer Motion · zod | — |
| Backend language | Python | 3.12 |
| API framework | FastAPI + Uvicorn | 0.141 / 0.52 |
| ORM + migrations | SQLAlchemy 2 (async) + Alembic | 2.0 / 1.19 |
| Relational DB | PostgreSQL | 16 |
| Graph DB | Neo4j | 5 (community) |
| Cache / state | Redis | 7 (AOF) |
| Object storage | MinIO (S3 API) + boto3 | — |
| NLP / extraction | spaCy 3.8 `en_core_web_sm` + RapidFuzz + charset-normalizer | — |
| Serialization | Pydantic | 2.13 |
| Hashing / crypto | `cryptography`, bcrypt, HMAC (custom JWT), Java Keystore (Android) | — |
| PDF generation | fpdf2 | 2.8.8 |
| Android app | Kotlin 2.1.0 · AGP 8.7.3 · Compose Material3 · CameraX · OkHttp 4.12 · zxing · security-crypto | SDK 35 / min 26 |
| Containers | Docker Compose | postgres, neo4j, redis, minio, minio-init, backend, backend-dev |
| Tests | pytest (+ pytest-asyncio) · Vitest · JUnit | — |
| Tooling | Ruff · mypy · ESLint 9 · Prettier | — |

---

## 4. Repository Layout (top level)

```
CyberSaarthi/
├── backend/                # FastAPI modular-monolith (Python 3.12)
│   ├── app/
│   │   ├── api/            # 19 routers under /api/v1 + dependencies + errors
│   │   ├── analytics/      # deterministic analytics engine (11 modules)
│   │   ├── core/           # config, security, auth(JWT), rbac, enums, codes, logging
│   │   ├── db/             # postgres, neo4j, redis, storage clients
│   │   ├── models/         # SQLAlchemy models (29 tables)
│   │   ├── repositories/   # ORM data-access layer
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # business logic (26 modules)
│   │   ├── main.py         # FastAPI app factory + lifespan + middleware
│   │   └── middleware.py   # observability + security headers
│   ├── migrations/         # Alembic chain (12 revisions, single head)
│   ├── scripts/            # create_admin · seed_demo · seed_users · sih_demo · preview_analytics
│   ├── tests/              # unit · api · integration · e2e (379 passing)
│   ├── Dockerfile          # multi-stage base→dev→runtime
│   ├── entrypoint.sh       # alembic upgrade head, then exec command
│   ├── pyproject.toml      # pinned deps, ruff, mypy, pytest config
│   └── uv.lock             # deterministic lockfile (uv)
├── frontend/               # React 19 + Vite + TS web UI
│   ├── src/
│   │   ├── app/            # App, providers, router, pages (26), layouts
│   │   ├── api/            # contract.ts + real adapter + mock adapter + session/client
│   │   ├── components/     # ui primitives, layout, graph (Cytoscape), command palette
│   │   ├── hooks/          # TanStack Query hooks + ui hooks
│   │   ├── stores/         # Zustand auth/ui/case-nav stores
│   │   ├── lib/            # utils, permissions, motion, requestId
│   │   ├── types/          # api.ts + domain.ts (backend contract mirror)
│   │   ├── config/         # env.ts
│   │   └── styles/         # Tailwind v4 globals.css tokens
├── mobile/                 # Android Field Agent (Kotlin, 5 Gradle modules)
│   ├── app/                # Compose app + data/domain/di/ui layers
│   ├── hashing-lib/        # SHA-256 utilities (pure Kotlin)
│   ├── manifest-lib/       # canonical package manifest + signing
│   ├── signature-lib/      # RSA Keystore signing envelope
│   └── state-machine-lib/  # collection lifecycle state machine
├── desktop-importer/       # stdlib-only CLI to package/sign/submit evidence (openssl)
├── docker-compose.yml      # full stack
├── Makefile               # dev workflow aliases
├── .env / .env.example     # configuration
├── docs/                   # ADRs, architecture reports, audit, project viewer
├── screenshots/            # UI previews
├── README.md               # main project readme
└── PROJECT_COMPLETE_AUDIT.* # verification audit
```

---

## 5. Deployment & Infrastructure

### 5.1 docker-compose.yml — services

| Service | Image / build | Ports | Healthcheck | Role |
|---|---|---|---|---|
| `backend` | `backend/Dockerfile` (runtime stage) | 8000 | `GET /api/v1/health` | FastAPI server, `restart: unless-stopped`, mounts `./backend:/app` |
| `backend-dev` | `Dockerfile` target `dev` | — | — | profile `dev`; contains pytest/ruff/mypy for `make test\|lint\|typecheck` |
| `postgres` | `postgres:16-alpine` | 5432 | `pg_isready` | authoritative store; volume `postgres_data` |
| `neo4j` | `neo4j:5-community` | 7474, 7687 | `cypher-shell RETURN 1` | graph projection; volume `neo4j_data` |
| `redis` | `redis:7-alpine` (`--appendonly yes`) | 6379 | `redis-cli ping` | revocation + throttling + cache; volume `redis_data` |
| `minio` | `minio/minio` | 9000, 9001 | `curl /minio/health/live` | evidence object store; volume `minio_data` |
| `minio-init` | `minio/mc` | — | — | one-shot: `mc mb --ignore-existing local/cybersaarthi` |

- Shared environment uses the YAML anchor `x-backend-env` so runtime and dev backends see identical
  infrastructure addresses (Postgres/Neo4j/Redis/MinIO by compose service name).
- Resource limits and `ulimits` (nofile 65536) are set per service; Neo4j gets 2 CPU / 4 GB.
- **Never run `docker compose down -v`** unless destroying data is intended — all investigation data lives
  in the four named volumes.

### 5.2 Backend Dockerfile — multi-stage

- **`base`**: `python:3.12-slim`, copies `pyproject.toml`, `alembic.ini`, `app`, `migrations`, `entrypoint.sh`.
- **`dev`**: installs `uv`, `uv sync --frozen --all-extras` into `/opt/venv` (outside `/src` bind mount);
  keeps pytest/ruff/mypy for the verification workflow; `CMD tail -f /dev/null`.
- **`runtime`** (final stage): `pip install --no-cache-dir -e .` with **only** `--only main` runtime deps;
  `ENTRYPOINT ["/entrypoint.sh"]`, default `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.
  `entrypoint.sh` runs `alembic upgrade head` **before** starting the server, so migrations always apply first.

### 5.3 Makefile targets

`up` (build+start), `down`, `down-v` (destructive), `build`, `logs`, `ps`, `seed` (`python -m scripts.seed_demo`),
`admin` (`python -m scripts.create_admin`), `test` (`backend-dev pytest`), `test-unit` (`-m "not integration"`),
`lint` (`ruff check .`), `format`, `format-check`, `typecheck` (`mypy app`), `migrate`, `migration MSG=...`, `shell`.

### 5.4 Configuration — `backend/app/core/config.py`

`Settings(BaseSettings)` reads env / `.env` (Pydantic v2). Key groups:

- App: `APP_NAME`, `APP_ENV` (default `development`), `API_V1_PREFIX="/api/v1"`, `LOG_LEVEL`.
- Postgres: `POSTGRES_HOST/PORT/DB/USER/PASSWORD`; `postgres_dsn` property builds the async DSN.
- Neo4j: `NEO4J_URI` (`bolt://…`), `NEO4J_USER`, `NEO4J_PASSWORD`.
- Redis: `REDIS_URL`.
- Object storage: canonical `STORAGE_*` with backward-compat `S3_*` aliases (`AliasChoices`).
- Ingestion: `EVIDENCE_MAX_SIZE_BYTES=5MiB`, `SPA_MODEL="en_core_web_sm"`, `GRAPH_CHUNK_SIZE=250`.
- Resolution: `RESOLUTION_AUTO_THRESHOLD=92.0`, `RESOLUTION_REVIEW_THRESHOLD=78.0`, `MAX_CANDIDATE_TARGETS_PER_KEY=25`.
- Analytics thresholds (centralized): node cap 2000, path max hops 4, path result limit 10, community quality 0.0,
  max hypotheses 25, pattern thresholds (shared identifier ≥3, concentration ≥5, bridge ≥2 communities,
  anomaly tail 0.95, rapid-spread 3600s).
- Security: `CORS_ORIGINS`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`, login throttling
  (`LOGIN_MAX_ATTEMPTS=5`, `LOGIN_IP_MAX_ATTEMPTS=20`, lockout 300s→max 3600s, fail-closed),
  `TOKEN_REVOCATION_ENABLED=True`.
- **A05 guard:** `validate_secrets_outside_dev` refuses to start in any non-dev/test environment with
  placeholder secrets (Postgres/Neo4j/S3/SECRET_KEY/Redis creds) or a `*`/empty CORS allowlist.
- `get_settings()` is `@lru_cache`d singleton.

### 5.5 Frontend config

- `frontend/.env` → `VITE_USE_MOCK_API=false` (live backend) and `VITE_API_URL=http://localhost:8000`.
- `src/config/env.ts`: anything other than literal `"false"` ⇒ mock mode; `$false` ⇒ real adapter.
- `vite.config.ts`: React + Tailwind v4 plugin, `@` alias to `/src`. `vitest.config.ts` force-enables mock API.
- `frontend/package.json` scripts: `dev`, `build` (`tsc -b && vite build`), `preview`, `test`, `lint`, `format`, `typecheck`.

### 5.6 Mobile build config

- `mobile/settings.gradle.kts`: five modules (`:app`, `:hashing-lib`, `:manifest-lib`, `:signature-lib`, `:state-machine-lib`),
  strict repositories (`google()` + `mavenCentral()`, `FAIL_ON_PROJECT_REPOS`).
- `:app` — namespace `io.cybersaarthi.fieldagent`, compileSdk 35 / min 26 / target 35, Java 17, Compose enabled,
  `BuildConfig.DEFAULT_SERVER_URL` from `defaultServerUrl` Gradle property.
  - `debug`: applicationId suffix `.debug`, `DEFAULT_SERVER_URL = "http://10.0.2.2:8000/api/v1"` (emulator loopback).
  - `release`: `DEFAULT_SERVER_URL = ""` (QR/manual pairing required), minify + shrinkResources, Keystore kept by proguard.
  - Dependencies: Compose BOM 2024.12.01, navigation-compose, lifecycle, coroutines (+play-services),
    OkHttp 4.12.0, CameraX 1.4.1, zxing 3.5.3, security-crypto 1.1.0-alpha06, documentfile; the four libs.
  - **No Gradle wrapper** — requires a local Gradle 8.x install (`gradle assemble` / `gradle test`).
- Library modules are small pure-Kotlin/Android libraries described in Section 10.

---

## 6. Backend — Application Shell & Cross-Cutting

### 6.1 `app/main.py` — app factory & lifecycle

- `lifespan()` constructs `Database`, `GraphStore`, `Cache`, `Storage` and stores them on `app.state.*`;
  probes each dependency at startup (failures logged, not fatal); closes all clients on shutdown.
- `create_app()`: `FastAPI(title="CyberSaarthi API", version=0.1.0, lifespan=lifespan)`; adds
  `RequestObservabilityMiddleware`, `SecurityHeadersMiddleware` (strict in production), CORS middleware
  (allowlist from settings, credentials allowed); includes `api_router`.
- Exception handlers convert every error into the **envelope** `{"error": {"code", "message"}}`:
  - `RequestValidationError` → 422 `VALIDATION_ERROR`.
  - `StarletteHTTPException` → mapped by status (400 BAD_REQUEST, 401 UNAUTHORIZED, 403 FORBIDDEN,
    404 NOT_FOUND, 405 METHOD_NOT_ALLOWED, 409 CONFLICT, 422 VALIDATION_ERROR, 429 TOO_MANY_REQUESTS,
    503 SERVICE_UNAVAILABLE).
  - `ApiHTTPException` → structured domain-code envelope (account lifecycle, permissions, case access).
  - `Exception` → 500 `INTERNAL_ERROR`.

### 6.2 `app/middleware.py`

- `SecurityHeadersMiddleware`: base set = `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `X-XSS-Protection`, `Cross-Origin-Opener-Policy: same-origin`,
  restrictive `Permissions-Policy`. Production strict set adds HSTS (max-age 31536000, includeSubDomains)
  and CSP `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`.
- `RequestObservabilityMiddleware`: honors client `X-Request-Id`/`X-Correlation-Id` or generates one;
  stores `request.state.correlation_id`; echoes `x-request-id`; logs every request (method, path, status,
  duration_ms, acting user id).

### 6.3 `app/api/errors.py`

- `ApiError(code, message)` + `ApiErrorResponse(error)` — the singleton error envelope.
- `ApiHTTPException(status_code, code, message, headers=None)` — Starlette subclass carrying a domain code.
- `error_response(...)` builds the `JSONResponse`.

### 6.4 `app/api/router.py`

Aggregates all routers under `/api/v1`: health, auth, cases, audit, users, evidence, entities, graph,
analytics, findings, victims, iot, collections, devices, timeline, hypotheses, reports, search, import_packages.

### 6.5 `app/api/dependencies.py` — the security chokepoint

- `_bearer_token(request)` parses the `Authorization: Bearer` header.
- `get_current_user`: validates token (and **revocation** via Redis `jti` denylist — fails closed), loads the
  `User` row, rejects non-`ACTIVE` accounts; caches on `request.state`.
- `get_current_roles`: loads role names via `user_roles` join.
- `require_permission(permission)`: factory → 403 `CODE_INSUFFICIENT_PERMISSION` if roles lack it.
- `require_role(*roles)`: plain 403 for role mismatch.
- `assert_case_access`: admin passes ⇒ owner passes ⇒ active `CaseMember` passes ⇒ else 403 **IDOR guard**.
- `get_case_or_404`: fetch → 404 → access check.
- `assert_case_mutable(case, allowed_statuses)`: `closed`/`archived` are read-only (`CASE_READ_ONLY` 409).
- Repository/service factories: `get_evidence_repository`, `get_entity_repository`, `get_relationship_repository`,
  `get_user_service`, `get_ingestion_service`, `get_analytics_service`, `get_analytics_data_repository`,
  `get_entity_query_service`.

### 6.6 `app/core/` modules

- **`auth.py`** — custom **HMAC-SHA256 signed tokens** (not library JWT): compact JSON payload
  `{uid, iat, exp, jti}` (jti = `secrets.token_hex(16)`), base64url body + `.` + hex HMAC signature.
  `create_access_token`, `decode_access_token` (returns UUID or None; constant-time compare), `decode_access_token_claims`.
- **`security.py`** — `hash_password` / `verify_password` with **bcrypt**.
- **`rbac.py`** — Roles ADMIN / INVESTIGATOR / ANALYST / VIEWER; permission constants
  (`case.*`, `evidence.*`, `ingestion.run`, `analytics.run`, `findings.{read,review,confirm,dismiss}`,
  `users.manage`, `audit.read`, `entity.merge`, ...); `ROLE_PERMISSIONS` mapping and `has_permission`.
- **`enums.py`** — `StrEnum` vocabularies (see Section 7.2).
- **`codes.py`** — domain error-code constants (`CODE_ACCOUNT_PENDING`, `CODE_CASE_ACCESS_DENIED`,
  `CODE_DUPLICATE_DEVICE_SERIAL`, `CODE_HASH_MISMATCH`, `CODE_REPLAY`, ...) + `MESSAGES`.
- **`logging.py`** — structured formatter, quiet noisy libs (uvicorn.access, boto3, urllib3).

### 6.7 `app/db/` clients

- **`postgres.py`** — `Database`: async engine from `settings.postgres_dsn`, `session_factory()` (async_sessionmaker),
  `ping()` (`SELECT 1`), `get_db_session` FastAPI dependency.
- **`neo4j.py`** — `GraphStore`: lazy async driver, `ping()` (`RETURN 1`).
- **`redis.py`** — `Cache`: lazy `redis.asyncio`, `ping()`, `close()`.
- **`storage.py`** — `Storage`: boto3 S3 client; `ensure_bucket()`, `ping()`, `exists`, `upload`, `download`,
  `delete`, `move`, `list_keys`, `delete_objects` (1000/batch), `delete_case_objects(case_id)` (A03 teardown).

---

## 7. Backend — Data Model (SQLAlchemy, 29 tables)

### 7.1 `app/models/base.py`

- `Base(DeclarativeBase)`; `UUIDPrimaryKeyMixin` (ULID-style `uuid.uuid4().hex` string PK);
  `TimestampMixin` (`created_at`, `updated_at` with `onupdate`).

### 7.2 Table inventory and enums

| Table | Purpose | Key columns / unique constraints |
|---|---|---|
| `users` | System accounts | username, email (unique), password_hash, status, last_login_at |
| `roles` | Role definitions | name (ADMIN/INVESTIGATOR/ANALYST/VIEWER) |
| `user_roles` | M2M users↔roles | user_id+role_id |
| `cases` | Investigation case | case_number, title, description, status (open/in_progress/closed/archived), severity, owner_id |
| `case_members` | Case access grants | case_id+user_id+role, `uq_case_members_case_user` |
| `victims` | Victim records | case_id FK, name, age, dob, gender, classification, phone, email, incident fields, financial impact, recovery_status, digital footprint, notes |
| `collections` | Evidence collections | case_id, name, status (draft/sealed), sealed_at |
| `field_devices` | Registered field devices | case_id+serial `uq_field_devices_case_serial`, platform, model, public_key, fingerprint, status (pending/approved/revoked), approved_by |
| `iot_devices` | IoT hardware | case_id+serial_number `uq_iot_devices_case_id`, device_type, status, registered_by, last_seen_at |
| `iot_events` | IoT telemetry | case_id, device_id, event_type, event_time, lat/lon, payload, confidence |
| `evidence_files` | Uploaded evidence | case_id+sha256 `uq_evidence_files_case_sha256`, filename, storage key, size, detected format, status, collection_id FK, deleted_at |
| `ingestion_jobs` | Ingestion runs | case_id+evidence_file_id `uq_ingestion_jobs_case_evidence`, status, progress |
| `data_sources` | Source names (e.g. "CDR") | name unique |
| `source_records` | Rows/records of a file | evidence_file_id+record_no `uq_source_records_file_record`, normalized_data JSONB, mentions, status |
| `entities` | Canonical resolved entity | case_id+entity_type+canonical_value `uq_entities_case_type_value`, display_value, status, context JSONB, features |
| `entity_aliases` | Alias surface forms | entity_id+alias_value `uq_entity_aliases_entity_value` |
| `entity_candidates` | Extraction candidates | case_id+record_id+entity_type+value `uq_entity_candidates_record_type_value`, resolution_status, confidence, entity_id |
| `entity_matches` | Resolution review matches | candidate_id+target_entity_id+score `uq_entity_matches_candidate_target`, status review/active/rejected, decision |
| `relationships` | Canonical graph edges | case_id+source+target+type `uq_relationships_case_src_dst_type`, strength, status |
| `relationship_evidence` | Provenance for edges | relationship_id+source_record_id+record_type `uq_relationship_evidence_rel_record_type` |
| `network_profiles` | Per-entity network DNA | entity_id+run_id `uq_network_profile_entity_run`, feature scores, tier |
| `findings` | Explainable findings | case_id, finding_type, title, severity, score, status, summary, signals, affected ids, run_id |
| `hypotheses` | Investigation hypotheses | case_id, relationship_hypothesis, supporting/contradicting evidence, evidence_weight, status |
| `reports` | Generated reports | case_id, report_type, format, status, minio_key, byte_size, failure_reason |
| `timeline_events` | Case timeline | case_id, kind, title, occurred_at, device/entity/evidence refs, actor |
| `audit_logs` | Append-only audit | actor_id, action, resource_type, resource_id, case_id, metadata JSONB |
| `analytics_runs` | Analytics job runs | case_id, status, actor_id, config, summary JSONB |
| `community_results` | Community memberships | case_id+run_id+community_id `uq_community_run_id`, members JSONB, density, score |
| `metric_results` | Per-entity metric values | case_id, run_id, entity_id, metric_name (centrality etc.) |
| `analytics_metrics` (aggregate) | — | — |

**Enums (controlled vocabularies):** `EntityType` (person/phone/vehicle/organization/account/location/document/event),
`EntityStatus` (active/merged/review/rejected), `RelationshipType` (called/owns/works_for/associated_with/located_at/visited/transferred_to),
`JobStatus` (pending/running/completed/failed/partial), `ResolutionDecision` (auto_match/review/no_match),
`EvidenceFormat` (csv/json/txt), `GraphSyncStatus`, `ExtractionSource` (field/ner/rule),
`EvidenceFileStatus` (stored/parsed/processing/failed), `AccountStatus` (PENDING/ACTIVE/SUSPENDED/REJECTED).

### 7.3 Model files (`app/models/`)

`base.py`, `user.py`, `role.py`, `user_role.py`, `case.py`, `case_member.py`, `victim.py`, `collection.py`,
`field_device.py`, `iot.py` (IoTDevice + IoTEvent), `evidence_file.py`, `ingestion_job.py`, `data_source.py`,
`source_record.py`, `entity.py`, `entity_alias.py`, `entity_candidate.py`, `entity_match.py`,
`relationship.py`, `relationship_evidence.py`, `network_profile.py`, `finding.py`, `hypothesis.py`,
`report.py`, `timeline_event.py`, `audit_log.py`, `analytics_run.py`, `community_result.py`, `metric_result.py`.
Each uses `UUIDPrimaryKeyMixin`/`TimestampMixin`, named unique constraints that back the idempotent
`on_conflict_do_nothing` inserts, and indexes on `(case_id, …)` for case-scoped queries.
---

## 8. Backend — API Routers (the full endpoint surface)

All under `/api/v1`. Each router lives in `app/api/routes/`.

### 8.1 `health.py`
- `GET /health` → `{status:"ok", service, version}` (public).
- `GET /ready` → probes all four stores via `ReadinessService`; 200 ready / 503 not-ready with per-component booleans.

### 8.2 `auth.py`
- `POST /auth/register` — creates a **PENDING** account (client role ignored); 409 on duplicate email/username.
- `POST /auth/login` — login throttling (Redis), success/failure audit events, issues HMAC token with fresh `jti`.
- `GET /auth/me` — current account (revocation-checked).
- `POST /auth/logout` — revokes the token's `jti`.
- Pending/suspended/rejected accounts are refused authentication everywhere.

### 8.3 `users.py` (admin surface, prefix `/admin/users`)
- Requires `PERM_USERS_MANAGE`. List/get users; `approve` (PENDING→ACTIVE, grants exactly one role),
  `reject`, `suspend`, `activate` (SUSPENDED only), `change role`.
- **Last-admin protection**: the final active ADMIN cannot be demoted/suspended/rejected; admins cannot act on themselves.

### 8.4 `cases.py`
- `POST /cases` (case_number derived deterministically from id), `GET /cases` (paginated),
  `GET /cases/{id}` (detail), `PATCH /cases/{id}` (guarded by `_CASE_TRANSITIONS`), `POST /cases/{id}/archive` (terminal).
- `GET/POST/DELETE /cases/{id}/members` — case membership (owner/admin control), audit-logged.
- Read-only cases (`closed`/`archived`) block all investigation mutations with 409.

### 8.5 `evidence.py` (largest router, 665 lines)
- `POST /cases/{id}/evidence` — multipart upload: format sniffing, SHA-256 fingerprint, 5 MiB cap,
  MinIO store `cases/<case>/<ev>/<filename>`, insert row (collection_id optional); duplicate → 409.
- `GET .../evidence` (list, non-deleted), `GET .../evidence/{eid}` (detail),
  `GET .../evidence/{eid}/provenance` (via `ProvenanceService`).
- `POST .../evidence/{eid}/ingest` — queues `IngestionJob` (idempotent: existing terminal job = no-op).
- `GET .../evidence/jobs`, `POST .../recycle` (soft delete), `POST .../restore`,
  download endpoints streaming from object storage.
- All file names sanitized via `_safe_stem` (path-trick protection).

### 8.6 `entities.py`
- `GET .../entities` (filters: entity_type, status, query), `GET .../entities/{eid}` (detail + aliases + context).
- `GET .../entities/review` — resolution review queue.
- `POST .../entities/review/{match_id}/accept|reject` — human resolution decisions.
- `POST .../entities/merge` — merge entities (requires `PERM_ENTITY_MERGE`).

### 8.7 `graph.py`
- `GET .../graph` (full case graph), `GET .../graph/entity/{eid}` (ego subgraph),
  `GET .../graph/stats` (node/edge counts + `graph_synced` from latest job).

### 8.8 `analytics.py`
- Read endpoints: `summary`, `centrality`, `communities`, `ego-paths`, `pair-paths`, `patterns`, `priority`
  (recomputed deterministically from PostgreSQL).
- `POST .../analytics/run` — persists an `AnalyticsRun` (pending→running→completed/failed) writing
  metric/community/profile/finding results.

### 8.9 `findings.py`
- `GET .../findings` (filters), `GET .../findings/{id}`,
  `POST .../findings/{id}/status` — drives `FindingsService` transitions
  (NEW→REVIEWED→DISMISSED/CONFIRMED), permission-gated by target, admin-overridable, audit + timeline recorded.

### 8.10 `victims.py`
- Full CRUD: `GET/POST /cases/{id}/victims`, `GET/PUT/DELETE /cases/{id}/victims/{vid}`, status+name filters.
- Guarded by case access + investigation-mutability; every mutation audit-logged.

### 8.11 `iot.py`
- `GET/POST .../iot/devices` (register unique serial per case; 409 `CODE_DUPLICATE_DEVICE_SERIAL`),
  `GET/PATCH/DELETE .../iot/devices/{did}` (status→inactive clears last_seen_at),
  `GET .../iot/devices/{did}/stats` (event_count, by_type Counter, first/last event_at),
  `GET/POST .../iot/events` (telemetry; bumps device last_seen_at).

### 8.12 `collections.py`
- `POST/GET .../collections`, `GET/PATCH .../collections/{id}`, `POST .../collections/{id}/seal`
  (409 if already sealed), `DELETE .../collections/{id}`.

### 8.13 `devices.py` (field devices, used by the Android agent)
- `POST .../devices` — register with public_key → SHA-256 **fingerprint**, status `pending`.
- `GET .../devices`, `POST .../devices/{id}/approve` (`PERM_USERS_MANAGE`), `POST .../devices/{id}/revoke`,
  `POST .../devices/{id}/verify-key` (RSA-SHA256 / Ed25519 signature verification).

### 8.14 `timeline.py`
- `GET/POST .../timeline` — case-scoped chronologically-ordered events with kind/entity/evidence/device filters.

### 8.15 `hypotheses.py`
- Create/list/get/status-transition (state machine, 409 `HYPOTHESIS_INVALID_TRANSITION`),
  link/unlink evidence (weight recompute `supports − contradicts`), delete.

### 8.16 `reports.py`
- `POST/GET .../reports`, `GET .../reports/{id}`, `GET .../reports/{id}/download`
  (JSON/CSV/PDF; 409 unless `ready`).

### 8.17 `search.py`
- `GET .../search?q=` — budgeted search across entities → aliases → evidence filenames → findings.

### 8.18 `import_packages.py`
- `POST .../import/packages` — multipart manifest+signature+files; delegates to `PackageVerificationService`.

### 8.19 `audit.py`
- `GET /audit-logs` — filters case_id/actor/action/resource_type; `PERM_AUDIT_READ`;
  scoping: ADMIN sees all; others see accessible-case events + their own global events.

---

## 9. Backend — Services (business logic)

Each service in `app/services/`:

- **`readiness.py`** — probes all four stores concurrently; returns `ReadinessResponse` + `all_ready`.
- **`audit.py`** — `record_audit(...)` inserts an `AuditLog` row (metadata JSONB) and flushes.
- **`token.py`** — `revoke_token(cache, jti, ttl)` writes `auth:jti:revoked:{jti}` (fail-open write);
  `is_revoked` reads fail-**closed**; `token_jti(token, secret)` extracts jti from claims.
- **`throttle.py`** — Redis keys `auth:login:attempts:{ip}:{username}` + `auth:login:ip:{ip}`;
  exponential backoff `LOCKOUT * 2^(count-1)` capped at max; `is_throttled`, `record_failed_attempt`,
  `clear_attempts`. `LOGIN_MAX_ATTEMPTS<=0` disables.
- **`validation.py`** — 1 MiB streaming cap reader, format detection (name + content sniff), encoding detection
  (charset-normalizer), `fingerprint` (SHA-256).
- **`parsing.py`** — `parse(data, fmt, encoding)`: CSV (header row, blank→`""`), JSON
  (list of dicts / `{records|rows|data}` array / single dict / scalar wrap), TXT (`\n\n` paragraphs as `{text}`).
- **`nlp.py`** — spaCy wrapper (`@lru_cache(16)`), maps NER labels to entity types (PERSON→person, ORG→organization,
  GPE/LOC→location, EVENT→event); graceful `None` if model unavailable.
- **`normalization.py`** — canonicalizers: `normalize_phone` (adds `91` to 10-digit, 7–15 digit valid),
  `normalize_vehicle` (alnum-uppercase 4–12), `normalize_account` (6–30 alnum), `normalize_document` (10–16 digits
  or 6–30 alnum), `normalize_person`, `normalize_organization`, `normalize_location/event`; `blocking_key` buckets
  (phones/accounts/vehicles exact; persons `last3_firstletter`; documents first 6; others first 4);
  regexes for phone/vehicle/AADHAAR/account/document labels.
- **`extraction.py`** — `FIELD_ALIASES` header→entity-type map, conservative substring hints,
  `Mention` dataclass; `extract_record_mentions` = field + rule + NER mentions deduped by `(type, canonical)`;
  `sentence_windows` for co-occurrence.
- **`relationships.py`** — `TYPE_PAIR_RULES` (person↔phone `called`, person↔vehicle/account `owns`,
  person↔org `works_for`, person↔person/event `associated_with`, person↔location `located_at`,
  phone↔phone `called`, account↔account `transferred_to`, location variants `visited`);
  `PAIR_PLAN` deterministic ordering; `MAX_RELATIONSHIPS_PER_RECORD=15`; canonical undirected endpoint sorting.
- **`resolution.py`** — scoring weighted `fuzzy(0.85) + context(0.15)`; no targets → create entity;
  ≥92 auto-match, ≥78 review candidate, else new entity; `ResolutionOutcome` carries decision/score/signals.
- **`resolve_review.py`** — `accept_match`/`reject_match`/`merge_entities` (guards on self-merge, missing/out-of-case,
  primary-already-merged, type mismatch; reassigns aliases + relationship endpoints to primary).
- **`entity_service.py`** — `EntityQueryService` (list, detail+aliases, review queue, relationships, `build_graph`,
  `graph_synced`).
- **`ingestion.py`** — the orchestrator: idempotent jobs, per-record source-record → extract → resolve →
  relationships, progress ticks, graph sync, summary, status transitions (partial on partial persist).
- **`graph_sync.py`** — Neo4j projection: `ensure_indexes` (uniqueness on entity id; `(case_id, type, canonical)`;
  case index), chunked UNWIND MERGE for nodes/edges, `prune_duplicate_edges`, `sync_case`, `delete_case`,
  `case_graph` (read back, lowercase types). Cypher labels guarded by an allowlist (A11).
- **`findings_service.py`** — findings status machine + `PERMISSION_BY_TARGET` map; admin override; idempotent no-ops.
- **`hypotheses.py`** — hypothesis state machine; evidence-weight recompute.
- **`package_verification.py`** — verifies manifest schema (1 MiB cap), canonical JSON signature
  (Ed25519/RSA-SHA256), device binding, replay check, per-file hash; **stores files only after all pass**
  (no orphaned objects); writes evidence rows, timeline, audit.
- **`provenance.py`** — traverses evidence→source records→relationships→entities→findings
  (JSONB overlap `evidence_ids ?| ARRAY[record_ids]`).
- **`reporting.py`** — `generate_report` builds JSON/CSV/PDF content, stores in MinIO under
  `reports/<case>/<ts>_<id>.<fmt>`, sets `ready`/`failed`.
- **`collections.py`** — CRUD + `seal_collection` + `link_evidence`/`unlink_evidence`.
- **`devices.py`** — register (fingerprint), approve, revoke, `verify_signature` (RSA/Ed25519), delete.
- **`search.py`** — budgeted multi-source ILIKE search with proper escaping.
- **`timeline.py`** — `record_event` / `list_events` with scope filters.
- **`users.py`** — account lifecycle state machine (PENDING→ACTIVE/REJECTED; ACTIVE→SUSPENDED;
  SUSPENDED→ACTIVE/REJECTED; REJECTED terminal), last-admin protection, role helpers.

---

## 10. Backend — Repositories, Analytics Engine, Migrations, Scripts, Tests

### 10.1 Repositories (`app/repositories/`)

- **`entity_repository.py`** — entities (concurrency-safe `on_conflict_do_nothing` create), aliases, candidates,
  matches; `find_by_blocking_key` honors the candidate cap (`MAX_CANDIDATE_TARGETS_PER_KEY`).
- **`evidence_repository.py`** — data sources, evidence CRUD + soft-delete, `get_by_sha`, source records,
  the **ingestion-job state machine** (`mark_job_running`, `tick_job_progress`, `complete_job`, `fail_job`,
  `mark_job_partial`, `mark_graph_sync`, `latest_job_graph_status`).
- **`relationship_repository.py`** — canonical relationships + per-relationship provenance rows.
- **`user_repository.py`** — users, status transitions, roles, admin counts.
- **`victim_repository.py`** — victim CRUD.
- **`analytics_repository.py`** — `AnalyticsDataRepository`: reads entities/relations/evidence stats;
  writes runs, metric/community/profile results, **immutable findings collapse** (A09);
  reads findings list/detail/stats.
- **`audit_repository.py`** — filtered, scoped audit queries.

### 10.2 Schemas (`app/schemas/`)

Pydantic v2 request/response models across `health`, `error`, `auth`, `cases`, `victim`, `iot`, `evidence`,
`entity`, `graph`, `analytics`, `findings`, `audit`. Highlights: username regex `^[A-Za-z0-9_.-]{3,64}$`,
password ≥ 12 chars, latitude [-90,90] / longitude [-180,180] / confidence [0,1], non-negative amounts,
age 0–200, and strict `Literal` status enums.

### 10.3 Analytics engine (`app/analytics/`) — deterministic network science

All analytics are **case-scoped** and **deterministic**: same input → same output, always.

- **`graph.py`** — pure undirected `Graph`; `build_graph` (from resolved entities + relationships),
  connected components, articulation points, **betweenness**, **closeness**, **PageRank**,
  common neighbors, triangle enumeration.
- **`centrality.py`** — ranks nodes by centrality; `compute_bridge_score` (nodes lying on paths between
  otherwise-disconnected parts), `community_membership`.
- **`communities.py`** — **greedy modularity-optimization** community detection
  (union-find merges; `_modularity_gain`), then `summarise_communities` with density + dominant relationship types.
- **`network_dna.py`** — per-node feature vector (degree, clustering, betweenness, etc.) compressed into a
  `NetworkProfileResult` with an overall score `0..1` and a tier (e.g. `hub`/`bridge`/`core`/`peripheral`).
- **`strength.py`** — relationship strength from evidence depth: coverage, type diversity, record coverage,
  file independence, resolution confidence → composite `StrengthSignals`.
- **`priority.py`** — `compute_priority(entity)`: combines prominence, influence, bridging, reach, adjacency/
  affinity signals, plus `pattern_weight` (severities) and `hypothesis_weight` (counts) → tier + score.
- **`paths.py`** — ego paths (all shortest paths from one node) and pair paths between two nodes,
  bounded by `ANALYTICS_PATH_MAX_HOPS` (4) and `_rel_pattern` hop-pattern labels.
- **`patterns.py`** — six deterministic pattern detectors:
  1. **shared_identifiers** — many entities sharing a phone, account, vehicle, etc. (`MIN=3`)
  2. **bridge_entities** — nodes whose removal splits ≥2 communities (`MIN_COMMUNITIES=2`)
  3. **relationship_concentration** — fan-out concentration (`MIN=5`)
  4. **circular_structures** — cycles in the relation graph
  5. **location_identifier_combination** — suspicious person–location–identifier mixing
  6. **rapid_expansion** — timestamp-spread growth signal (`RAPID_SPREAD_SECONDS=3600`)
  Each emits a `PatternDraft` with severity (based on anomaly percentile `ANOMALY_TAIL=0.95`) and score.
- **`hypotheses.py`** — derives candidate **criminal hypotheses** from the graph
  (e.g., "high-centrality entity X bridges communities A and B") with relation type, weight and clarity.
- **`findings.py`** — `AnalyticsService` orchestrates `_assemble_findings` from the above raw signals
  (network insights + relationship insights), scores by evidence support, attaches
  `affected_evidence` / summaries, and formats human-readable findings with limitation notes.
- **`explanations.py`** — `build_explanation` (human-readable "why"), `evidence_from_source_records`,
  `signature_limitation` (caveat strings so findings never overclaim).

### 10.4 Migrations (`backend/migrations/versions/`) — single linear head

Order (revision → what it added):
1. `e308a313166d` **initial_schema** — users, roles, user_roles, cases, victims? (base), entities,
   evidence_files, source_records, ingestion_jobs, data_sources, relationships, relationship_evidence,
   audit_logs, analytics tables.
2. `081a88d02574` **phase_2_data_intelligence_pipeline** — entity_candidates, entity_matches, entity_aliases,
   network_profiles, metric_results, community_results, findings, hypotheses, timeline_events.
3. `f31fa700fb23` **canonical_relationships** — relationship canonicalization + strength columns.
4. `a4b9c7e16d20` **phase_3_investigation_intelligence_engine** — reports, analytics_runs, extra finding indexes.
5. `cc19f4d2b003` **phase_4_productization_auth_rbac** — user status + account lifecycle plumbing.
6. `210adeaee0c6` **phase_5_token_revocation_and_** — token/revocation support columns.
7. `b7d4f2c9a1e0` **phase_5_user_account_lifecycle_status** — account status enum values.
8. `c1a2b3c4d5e6` **add_case_membership** — case_members table.
9. `d2e3f4a5b6c7` **add_evidence_soft_delete** — `deleted_at` on evidence_files.
10. `v1a2b3c4d5e6` **add_victims_table** — victims.
11. `w2b3c4d5e6f7` **add_iot_tables** — iot_devices, iot_events.
12. `6050ea12acad` **add_collections_field_devices_** — collections + field_devices (head).

`entrypoint.sh` applies `alembic upgrade head` automatically at container start.

### 10.5 Scripts (`backend/scripts/`)

- **`create_admin.py`** — idempotent bootstrap of the first ADMIN (`admin`/`admin-…` from env with
  dev defaults `admin / admin-dev-password`). **Refuses** to mint a second admin if one exists.
- **`seed_users.py`** — idempotently seeds `admin` (ADMIN) and `investigator` (INVESTIGATOR) accounts
  (default passwords `admin-dev-password` / `investigator-dev-password`, overridable via env).
- **`seed_demo.py`** — deterministic demo case **`DEMO-2026-001`**: creates users, the demo case,
  synthetic evidence files (CSV/JSON) that exercise the full pipeline, runs ingestion, and seeds IoT +
  victim records. Idempotent re-run.
- **`sih_demo_network.py`** — builds the SIH demo **criminal network** dataset: persons.csv, transfers.json,
  associations.txt committed under `sih_demo_seed/` with a known entity tally.
- **`preview_analytics.py`** — CLI to run/print analytics results for a case for demos.

### 10.6 Tests (`backend/tests/`) — 379 passing

- **unit/** — analytics algorithms, auth tokens, config, errors, extraction, findings service, graph sync,
  infra hygiene, ingestion job, normalization, parsing, rbac, readiness, relationships, resolution,
  security, throttle, token revocation, validation.
- **api/** — access control, admin users, analytics, audit, auth, case members, case read-only, cases,
  findings, health, observability, phase2, phase3, provenance, readiness.
- **integration/** — bootstrap admin, concurrency/idempotency, entity pipeline, graph-sync lifecycle,
  neo4j, postgres, redis, storage.
- **e2e/** — `test_investigator_workflow.py` — the full 28-step SIH primary-flow scenario.


---

## 11. Frontend — the React web console (`frontend/`)

Investigators interact with the system through this SPA. **Stack**: React 19 + Vite 6 + TypeScript 5.7,
Tailwind CSS 4 (via `@tailwindcss/vite`), React Router 7, TanStack Query 5 (server state),
Zustand (client state), Zod (validation), Cytoscape (graph viz), Framer Motion (animation),
Radix UI primitives + custom `components/ui`. ~3,800 TS LOC, **67 Vitest tests (13 files)**.

### 11.1 Bootstrapping & layout
- `frontend/index.html` → `src/main.tsx` mounts `<App>` inside the router.
- `src/app/router.tsx` — route table + `<AppShell>` layout with a **sidebar + topbar chrome**
  (`components/layout/brand.tsx` logo, `page.tsx` page wrapper).
- `src/app/app.tsx` — providers: QueryClient, browser router, permission gate, Toaster.
- `src/lib/` — `requestId.ts` (per-request correlation id for `X-Request-ID`), `utils.ts` (cn/slug),
  `motion.ts` (shared entrance animations), `permissions.ts` (tiny role→permission resolver, `PERM_*`).

### 11.2 API layer (`src/api/`)
- `contract.ts` — the **single typed contract**: every endpoint, request/response type map shared
  by real and mock adapters (parity is enforced by tests).
- `client/http.ts` — fetch wrapper (base URL from `env.ts`, bearer token injection, JSON + multipart,
  error normalization to `ApiError` {code, message, details, status}).
- `client/session.ts` — token/session persistence and expiry handling.
- `real/index.ts` — real adapter talking to `BACKEND_URL + /api/v1`.
- `mock/index.ts` + `mock/data.ts` — in-memory mock adapter so the UI is fully usable without a backend
  (starts with the DEMO case dataset). `mock/mock-adapter.test.ts` + `parity.test.ts` keep it in sync with the contract.
- `src/api/index.ts` — picker between mock (dev) and real (prod) based on `VITE_USE_MOCK_API`.

### 11.3 Auth & state
- `src/stores/auth.ts` — Zustand store holding `{token, account, permissions}` + login/logout actions
  (localStorage persistence). `auth.test.ts` covers the role-tree logic.
- `src/stores/case-nav.ts` — remembers the active case for navigation breadcrumbs;
  `src/stores/ui.ts` — UI flags (sidebar collapsed, etc.).
- `src/hooks/queries.ts` — every server read as `useQuery` keys + `useMutations`; invalidation strategy
  lives in `queries.ts` (and `f04-invalidation.test.tsx`). `src/hooks/ui.ts` — small UI helpers.
- `src/components/commands/command-palette.tsx` — Cmd+K palette that jumps to entities/findings/cases.

### 11.4 Page catalogue (`src/app/pages/`, 28 screens)
- **auth**: `login.tsx`, `register.tsx`, `pending.tsx` (account awaiting approval), `no-access.tsx`,
  `not-found.tsx`.
- **home**: `dashboard.tsx` — case list + stats + "My cases" cards and recently-active evidence.
- **case mgmt**: `cases.tsx` (all-cases table + create), `case-layout.tsx` (case context shell with
  investigation sidebar), `case-overview.tsx` (summary cards, members, recent activity).
- **investigation**: `evidence.tsx` (evidence table + upload/ingest), `entities.tsx` (entity list +
  filters), `entity-detail.tsx` (aliases, relationships, provenance), `graph.tsx` (Cytoscape interactive
  graph with layout/community coloring/selection), `analytics.tsx` (metrics, communities, centrality,
  patterns), `findings.tsx` / `finding-detail.tsx` (review + status transitions), `hypotheses.tsx`,
  `timeline.tsx`, `reports.tsx` (generate + download), `victims.tsx` / `victim-detail.tsx`,
  `iot-devices.tsx` / `iot-device-detail.tsx`.
- **admin**: `admin-users.tsx` (approve/reject/suspend/roles), `audit.tsx` (audit log explorer),
  `settings.tsx` (appearance, server info).
- Notable tests: `graph.test.tsx` (Cytoscape rendering), `admin-users.test.tsx`.

### 11.5 Feature notes
- Charts/graphs: `components/graph/cyto-graph.tsx` (Cytoscape with dagre/fcose layouts, click→entity detail).
- `components/status.tsx` — status → colored badge mapping reused across tables;
  `components/error-boundary.tsx` — crash containment.
- All forms are Zod-validated; every destructive action is a confirmed dialog.
- The demo case (`DEMO-2026-001`) data plays straight through the mock adapter → identical UI to production.

---

## 12. Mobile — the Android field agent (`mobile/`)

On-device evidence collection for agents in the field. **Stack**: Kotlin + Jetpack Compose (Material 3),
Android Gradle Plugin, Koin (manual DI via `AppContainerLocal.kt`), Retrofit-style fields but a custom
`ApiClient`. Package namespace **`io.cybersaarthi.fieldagent`**; five Gradle modules
(`settings.gradle.kts`: `:app`, `:manifest-lib`, `:hashing-lib`, `:state-machine-lib`, `:signature-lib`).

### 12.1 Modules
- **`:app`** — application, UI, networking, storage (everything below).
- **`:hashing-lib`** — `hashing/EvidenceHasher.kt` — pure SHA-256 hashing of evidence bytes with
  streaming (no memory blow-up on large files); unit-tested.
- **`:manifest-lib`** — `manifest/PackageManifest.kt` — the transfer-manifest model (schema "1.0",
  case/device/evidence list with per-file SHA-256 hashes + timestamps), serialization + validation.
- **`:signature-lib`** — `signature/SignatureEnvelope.kt` — signed envelope `{manifest, signature,
  algorithm, keyFingerprint, timestamp}`; RSA-SHA256 + Ed25519 support.
- **`:state-machine-lib`** — `state/CollectionState.kt` — lawful `CollectionState` transitions
  (`DRAFT → COLLECTED → FROZEN → TRANSFERRED` + sensible rollback edges); `CollectionStateTest` guards it.

### 12.2 App core (`:app`)
- `MainActivity.kt` — single-activity Compose host; `CyberSaarthiApp.kt` — root composable wiring
  the nav graph + theme; `Errors.kt` — `FieldError` sealed hierarchy rendered as toasts/inline errors.
- **Screens** (`ui/screen/`), each with a paired `ViewModel` except the simplest ones:
  - `onboarding/OnboardingScreen.kt` — welcome + permissions.
  - `connection/ConnectionProviderScreen.kt` — choose connection method; `LanDiscoveryScreen.kt`
    (mDNS/LAN broadcast scan); `ManualServerScreen.kt` + `ManualServerViewModel.kt`
    (type a server URL; health-checks it); `QrPairingScreen.kt` + `QrPairingViewModel.kt`
    (scan a backend-issued pairing QR with the expected server fingerprint).
  - `auth/LoginScreen.kt` + `LoginViewModel.kt` (email/password; shows server host badge at top);
    `EnrollScreen.kt` + `EnrollViewModel.kt` (pick case, "Register this device" → uploads the
    device public key → pending approval).
  - `dashboard/DashboardScreen.kt` + `DashboardViewModel.kt` — "My cases" list once enrolled.
  - `case_detail/CaseDetailScreen.kt` + `CaseDetailViewModel.kt` — case info + actions.
  - `collection/CollectionScreen.kt` + `CollectionViewModel.kt` — capture/associate evidence
    (photo/file via activity results), hash, add to the working set.
  - `transfer/TransferScreen.kt` + `TransferViewModel.kt` — build signed manifest package,
    push to backend or offline dropbox.
  - `field/FieldModeScreen.kt` — kiosk-style quick-capture mode.
  - `profile/ProfileScreen.kt` + `ProfileViewModel.kt` — device identity, enrollment status, logout.
- **Components**: `ui/components/Components.kt` (shared buttons/cards/chips),
  `ui/components/ConnectionStatusChip.kt` (online/offline/pairing badge).

### 12.3 Data layer (`data/`)
- `net/ApiClient.kt` — low-level HTTP over OkHttp + ktor content, JSON hand-rolled via kotlinx;
  builds full URLs from `baseUrl()` + path and contains the **`/api/v1` de-duplication fix**
  (`resolveUrl`) noted in §A.4. `net/FieldApi.kt` — typed endpoint calls (login, enroll, cases,
  evidence upload, verify key, transfer submit). `net/Dtos.kt` — API DTOs. `net/ApiException.kt`
  → `FieldError` mapping.
- `auth/SessionManager.kt` — token store + revocation on logout.
- `store/EvidenceStore.kt` — local evidence records (`LocalEvidence.kt`); `store/TransferManager.kt`
  — manifest building + transfer orchestration.
- `offline/OfflineUnlock.kt` — offline dropbox/import handoff.
- `pairing/PairingManager.kt` — QR parsing + server-fingerprint validation (strict: refuses to add a
  server whose fingerprint doesn't match the QR).
- `cache/CaseCache.kt` — small local cache of cases/entity names for offline screens.
- `capture/` — capture helpers (camera/gallery intents).
- **Domain**: `domain/DeviceIdentity.kt` — generates the Ed25519/RSA keypair, exposes
  `serial`, `model` (Build.MODEL), `publicKey`, `fingerprint` (SHA-256 of the key); `domain/SensorRegistry.kt`.
- **Config**: `config` (server defaults; debug builds point at `10.0.2.2:8000/api/v1` — see §A.4),
  `connectivity`, `di/AppContainerLocal.kt` (manual singleton container); debug/field flavors differ
  only in server URL + applicationId (`…fieldagent.debug`).

---

## 13. Desktop importer, Infrastructure & Operation

### 13.1 Desktop importer (`desktop-importer/cybersaarthi_importer.py`, 279 lines, stdlib-only)
Bulk import of pre-collected evidence from a laptop. Commands: `make-manifest` (walks a folder,
builds manifest v1.0 with per-file SHA-256 + `CANONICAL_KEYS` ordering), `sign` (shells out to
**openssl** for RSA-SHA256 or Ed25519), `verify` (self-check), `submit` (POSTs
`/api/v1/import/packages` with manifest + signature + files), `inspect` (dump a manifest).
The backend's `PackageVerificationService` re-verifies everything before storing any file (see §9).

### 13.2 Docker Compose topology (`docker-compose.yml`)
| Service | Image/Role | Port |
|---|---|---|
| postgres | pgvector/pg16 — source-of-truth relational store | 5432 |
| neo4j | neo4j:5 — visual graph projection (projection only) | 7687/7474 |
| redis | redis:7 — token revocation + login throttle caches | 6379 |
| minio | minio + `minio-init` bucket bootstrap — evidence object storage | 9000/9001 |
| backend | builds from `backend/Dockerfile` | 8000 |
| backend-dev | bind-mounted dev variant (uv, hot reload) | 8000 |

Healthchecks wired for db/redis/minio so the backend waits for dependencies.

### 13.3 Backend Dockerfile — three stages
1. `base` — python 3.12-slim, `uv` copy + `uv sync --frozen` for runtime deps.
2. `dev` — inherits base + adds pytest/ruff/mypy; runs `entrypoint.sh` equivalent with reload.
3. `runtime` — copies only runtime site-packages (small image), runs `entrypoint.sh`
   (`alembic upgrade head && uvicorn app.main:app`).

### 13.4 Makefile (`make …`)
- Backend: `make up`/`down` (compose), `backend-shell`, `pytest`, `ruff`, `mypy`, `seed`,
  `create-admin`, `seed-demo`, `alembic-*` (autogenerate/upgrade/downgrade), `logs`.
- Frontend: `frontend-dev`, `frontend-build`, `frontend-test`.
- Mobile: `mobile-build`/`mobile-install` helper wrappers around the Gradle steps.

### 13.5 Configuration & env (`backend/.env.example`, `frontend/src/config/env.ts`)
- `CYBERSAARTHI_*` envs: database/neo4j/redis/minio URLs, JWT secret + expiry, cors origins,
  login throttle knobs (`LOGIN_MAX_ATTEMPTS`, lockouts), analytics knobs (`ANALYTICS_*`),
  storage bucket/region, initial admin credentials. Frontend: `VITE_API_URL`, `VITE_USE_MOCK_API`.

---

## 14. The complete investigation workflow (how components connect)

1. **Onboard** — register (pending) → admin approves in `admin-users.tsx` with a single role;
   approval is audited and the user can log in (`POST /auth/login`, throttled) and see the dashboard.
2. **Upload evidence** — `frontend` `evidence.tsx` or field-agent/desktop-importer uploads files →
   `POST /cases/{id}/evidence` fingerprints (SHA-256), dedupes, stores in **MinIO**, inserts row;
   an `IngestionJob` is queued.
3. **Ingest** — `EvidenceIngestionWorker`: validation → parsing (CSV/JSON/TXT) → extraction
   (explicit fields + heuristic rules + spaCy NER) → normalization (canonical phone/vehicle/account/…) →
   **entity resolution** (blocking-key candidates → fuzzy scoring → auto-match/review/new) →
   canonical **relationships** with provenance → progress ticks → **graph sync** to Neo4j.
4. **Analyze** — analysts run `POST /analytics/run`; the deterministic engine computes centrality,
   communities, paths, patterns, priorities, network DNA, and drafts **findings** (all persisted to PG).
5. **Investigate** — graph explorer, entity detail + provenance, timeline, hypotheses
   (evidence-linked, `supports − contradicts` weighting), findings review (REVIEWED→CONFIRMED/DISMISSED).
6. **Report** — generate JSON/CSV/PDF, stored in MinIO, downloadable; sealed collections +
   victims + IoT telemetry round out the case record.
7. **Field device flow** — the Android agent: connect (manual/LAN/QR) → login → enroll a device
   (public key → fingerprint) → admin approves in backend → agent gets "My cases" → collects
   evidence (hashed) → builds signed **transfer manifest** → submits package (backend re-verifies
   signature/hashes before storing) or hands off offline.

**Security posture (A-item audit findings)**: password min 12, duplicate login throttling, token
revocation via Redis `jti` list, account lifecycles (pending/suspended/rejected), last-admin
guard, case read-only on closed/archived, soft-delete evidence, immutable-findings collapse,
Cypher-label allowlisting, path-trick filename scrubbing, report/package size caps, origin CORS
allowlist, and correlation-id request tracing.

**Verification**: 379 backend tests (`pytest` — unit/api/integration/e2e incl. the 28-step SIH
investigator workflow), 67 frontend tests (`vitest` run, 13 files), 23 mobile unit tests (`@Test`
methods under `mobile/app/src/test`; their execution requires the Android toolchain — not part of
this verification), `ruff` + `mypy` clean, `vue`-free deterministic analytics with a documented confidence floor.

---

*End of CyberSaarthi complete technical documentation.*

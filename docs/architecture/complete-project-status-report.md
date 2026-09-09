# CyberSaarthi — Complete Project Status Report

> **Audit-only report.** No source files were modified, no commits were made, no
> configuration or schema changed, and nothing was deleted during this audit.
> Source code is the authority; documentation is cited but not trusted on its own.

- **Project:** CyberSaarthi — AI-Powered Criminal Network Analysis System
- **SIH Problem Statement:** SIH26189
- **Repository:** `/home/xhroot/Documents/ai/cybersaarthi`
- **Audit commit:** `d53d5ac` — `fix: close functional verification gaps` (HEAD, main)
- **Prior verification commit:** `602d688`

---

## PART 19 — One-Page Executive Summary

**PROJECT:** CyberSaarthi — Investigation Intelligence Platform
**Pipeline:** `Evidence → Entity Resolution → Knowledge Graph → Analytics → Findings`

### WHAT IS WORKING
- ✅ **Full evidence-to-findings pipeline** — upload → MinIO → SHA-256 fingerprint → ingestion (CSV/JSON/TXT) → entity extraction (field aliases + rules + optional spaCy NER) → entity resolution (blocking buckets + RapidFuzz) → relationship extraction → PostgreSQL → Neo4j MERGE projection → deterministic graph analytics → persisted, provenance-attributed findings.
- ✅ **Auth & RBAC** — bcrypt, HMAC-SHA256 bearer tokens, 4 roles / 15 permissions, full account lifecycle (PENDING→ACTIVE↔SUSPENDED→REJECTED), Redis login throttle, **server-side token revocation** (JTI denylist), admin bootstrap.
- ✅ **Case management** — create/list/search/paginate/update/close/archive, members (collaborator/viewer), **case isolation (P0 fixed + regression test)**, closed/archived read-only enforcement (409 CASE_READ_ONLY).
- ✅ **Deterministic analytics engine** — degree/in/out/betweenness/closeness/PageRank, bridge score, greedy-modularity communities, 6 pattern detectors, missing-link hypotheses, 8-dimension Network DNA, priorities, relationship strength — all evidence-attributed and explained.
- ✅ **Neo4j projection** — idempotent MERGE, relationship-type allowlist (Cypher-injection-safe), chunked writes, duplicate-edge pruning.
- ✅ **Audit trail** — append-only, RBAC-scoped, correlation IDs (`X-Request-Id`).
- ✅ **Tests & CI** — backend 43 files / 341 tests passing; frontend 56 tests passing; ruff/mypy/tsc/eslint/alembic-check green; GitHub Actions backend CI.

### WHAT IS BROKEN
- 🔴 **Deep-link / hard-refresh routing:** hard page load on a nested `/app/*` route falls back to the dashboard (only in-SPA navigation renders nested routes). Documented in `docs/PROJECT_VIEW_REPORT.md`, Finding 1.
- 🔴 **Frontend real-mode not regularly exercised:** the real adapter is parity-tested and smoke-tested, but daily UI use is in mock mode.

### WHAT IS PARTIAL
- 🟡 **Entity-resolution review loop** — REVIEW matches are listable but there is no accept/reject/merge/split UI to complete the loop.
- 🟡 **Analytics "run vs read" semantics** — one historical run is persisted atomically; GET endpoints calculate **live**; past-run versioning is incomplete.
- 🟡 **Timeline** — derived from the audit log (no dedicated endpoint), gated by `audit.read`; analysts/viewers see an empty timeline.
- 🟡 **Case assignment model** — members exist; no lead/assignee lifecycle or work queues.
- 🟡 **spaCy NER** — lazy, graceful-degradation wrapper only; no custom-trained NER, no embeddings, no pipeline.

### WHAT IS MISSING
- 🔴 **AI/ML:** no model serving, no embeddings, no RAG, no LLM, no prompts, no training/eval/orchestration, no model governance.
- 🔴 **IoT:** zero IoT code — no device registry, telemetry, MQTT/WebSockets, GPS, or sensor schemas.
- 🔴 **Reporting/export:** no investigation report, no PDF/CSV/JSON export, no graph/analytics export.
- 🔴 **Alerting/notifications**, **background workers/queues** (ingestion is synchronous), **password reset**, **email verification**, **MFA/OIDC**, **audit retention/export**, **production hardening** (TLS, secrets manager, backups, monitoring/alerting, DR, scaling).

### IOT
- **CURRENT:** ⚪ NONE — zero IoT code (verified by exhaustive search).
- **PROPOSED:** ESP32-S3 field recorder (GPS, MPU6050, BME280, reed switch, SD, Wi-Fi/4G, optional LoRa/camera) → TLS/MQTT/HTTPS → CyberSaarthi IoT Gateway → evidence/telemetry ingestion → entity/event pipeline → Neo4j → analytics. See Part 12.

### SOUP AI
- **CURRENT:** 🔴 NOT IMPLEMENTED — no integration with `https://github.com/MakazhanAlpamys/Soup` or any other LLM/runtime.
- **PROPOSED:** Soup provides the training/fine-tuning/serving layer for an investigation-focused AI Copilot that calls **CyberSaarthi tool endpoints** (search, resolve, profile, relationships, timeline, evidence, paths, centrality, communities, DNA, priorities) and returns evidence-cited answers. CyberSaarthi remains the deterministic source of truth. See Part 13.

### TOP 10 NEXT TASKS
1. Fix deep-link/hard-refresh routing for nested `/app/*` routes.
2. Close the entity-resolution review loop (accept/merge/reject UI + API).
3. Add reporting/export (investigation report, evidence bundle, graph/analytics export).
4. Add background workers/queue for ingestion + analytics (decouple from request).
5. Build a real-mode SIH demo harness (seeded large network, one live pass through evidence→graph→analytics→findings).
6. Add case assignment/ownership model (lead investigator, work state).
7. IoT Gateway + device-registry MVP (ESP32-S3 reference integration).
8. Password reset + email verification + MFA groundwork.
9. Soup AI Copilot feasibility spike (tool-calling eval harness against live API).
10. Production hardening: secrets, TLS, backups, monitoring/alerting, audit retention/export.

### BIGGEST TECHNICAL RISKS
1. **AI & IoT are greenfield** — both are central to the SIH narrative yet do not exist; they must be built and de-risked early.
2. **Demo fragility** — a deterministic mock demo is strong, but any claim of live/real-mode performance on large networks is unproven; deep-link bug can derail navigation during a demo.
3. **Synchronous ingestion** — large evidence files run inline in the HTTP request; no queue/worker → latency, timeouts, and memory risk.

### SIH DEMO READINESS
Honest assessment: the **deterministic analysis platform is demo-ready in mock mode** (rich seeded data, complete workflows, 20 screenshots). A **live real-mode demo on modest data is credible today** for evidence → graph → analytics → findings, IF the deep-link bug is fixed and one seeded real-mode pass is rehearsed. A presentation that pivots on **"AI" or "IoT" cannot be supported yet** — those pillars are entirely missing. Framing the demo around the *deterministic investigation-intelligence pipeline* is both honest and strong.

---
## PART 1 — Repository Inventory

### Top-level structure
| Path | Purpose |
|---|---|
| `backend/` | FastAPI monolith (Python 3.12, SQLAlchemy 2.x, Pydantic v2, Alembic) |
| `frontend/` | React 19 + Vite + TypeScript SPA (Cytoscape.js graph) |
| `docs/` | ADRs, architecture reports, project-view report + screenshots |
| `scripts/` | Dev/test/devops helpers |
| `docker-compose.yml` | 7 services: backend, postgres, neo4j, redis, minio, minio-init, frontend |
| `Makefile`, `.github/workflows/ci.yml`, `.env.example`, `README.md` | Dev/CI/env entry points |

### Backend inventory (source of truth: `backend/app/`)
| Area | Count | Notes |
|---|---|---|
| Python files (repo, excl `.venv/__pycache__`) | 167 | 100 app + 51 tests + migrations/scripts |
| API routers | 11 | `auth/cases/evidence/ingestion/entities/relationships/analytics/findings/timeline/audit/dashboard/admin/users` (12 router modules incl. `/graph`) |
| Endpoints | 55 | all documented in `backend/docs/frontend-contract.md` (172 lines) |
| SQLAlchemy models | 23 | Postgres tables |
| Services | 18 | domain logic |
| Analytics modules | 12 | graph algorithms + patterns + prioritization |
| Repositories | 7 | data access |
| Test files | 43 | 20 unit + 15 api + 7 integration + 1 e2e = **341 tests** |
| Alembic revisions | 9 | linear chain, head `d2e3f4a5b6c7` (evidence soft delete) |
| ADRs | 7 | `docs/adr/` 001–007 |
| Config | `app/core/config.py` | pydantic-settings, env-driven |

### Frontend inventory
| Area | Count / Notes |
|---|---|
| TS/TSX files | 80 |
| Pages (`src/app/pages/`) | 23 |
| API adapters | mock (default) + real (parity-enforced) |
| Vitest files | 13 (56 tests) |
| Graph | Cytoscape.js `src/components/graph/cyto-graph.tsx` |

### Docs inventory (`docs/`)
- `adr/` — 7 ADRs (monular-monolith, docker-first, postgresql-and-neo4j, local-object-storage, evidence-ingestion-provenance, entity-resolution, postgres-source-of-truth-neo4j-projection)
- `architecture/` — phase-1..phase-5 reports, master-remediation-report, functional-verification-602d688, remediation-602d688-followup
- `PROJECT_VIEW_REPORT.md` + `project-view/screenshots/` (20 PNG, Playwright, **mock mode**)
- `backend/docs/frontend-contract.md`

### CI/CD
- `.github/workflows/ci.yml` — **backend-only** job: ruff + mypy + pytest (Postgres + Redis; no Neo4j, no MinIO, no frontend job).

---

## PART 2 — Current Architecture

```
┌─────────────── FRONTEND (React SPA) ───────────────┐
│ src/config/env.ts (mock unless VITE_USE_MOCK_API=false)
│   ├─ api/mock/*   ← mock adapter (DEFAULT)
│   └─ api/real/*   ← real adapter → api/client/http.ts → /api/v1
│ 23 pages, cytoscape graph, hooks/queries.ts, stores/auth.ts
└───────────────┬─────────────────────────────────────┘
                │ HTTPS (dev: HTTP)
┌───────────────▼───────────── API — FastAPI monolith ─┐
│ /api/v1 — 11 routers / 55 endpoints / error envelope
│ core: rbac (4 roles/15 perms), auth (HMAC-SHA256 + JTI
│       denylist + throttle), dependencies (guards: case
│       isolation, READ_ONLY_CASE_STATUSES), codes
│ services (18): evidence, ingestion, entities, relations,
│       analytics, findings, audit, graph-sync, cases...
│ analytics (12): centrality, communities, patterns,
│       missing-link, network-dna, priorities, strength
└──────┬─────────┬──────────┬────────────┬─────────────┘
       │         │          │            │
  PostgreSQL    Neo4j       Redis      MinIO
  (source of    (graph      (JTI deny-  (evidence blobs:
  truth, 23     projection, list +      cases/<case>/
  models)       MERGE)      throttle)   evidence/<uuid>/<stem>)
       │         │          │            │
       └─────────┴────OMI-SYNC──legacy──┘
```

### REAL / MOCK / PARTIAL matrix
| Area | Status | Evidence |
|---|---|---|
| Frontend API adapter | 🟡 **MOCK default**; real adapter exists + parity-tested | `src/config/env.ts`, `api/mock`, `api/real` |
| Backend API | ✅ **REAL** (fastAPI) | routers/endpoints, live e2e checks |
| Database | ✅ **REAL** Postgres + Neo4j + Redis + MinIO | live pytest, docker services |
| Evidence ingestion | ✅ **REAL** (synchronous, idempotent) | services, integration tests |
| Entity resolution | ✅ **REAL** (blocking + RapidFuzz), review UI ⚪ | services, `resolution.py` |
| Graph analytics | ✅ **REAL** deterministic | analytics modules, tests |
| Findings | ✅ **REAL** engine-created + dedupe | services, tests |
| Timeline | 🟡 **DERIVED** (from audit logs; gated by `audit.read`) | api `timeline` |
| AI/ML | 🔴 **NONE** | verified empty |
| IoT | 🔴 **NONE** | verified empty |
| Soup AI | 🔴 **NOT IMPLEMENTED** | verified empty |

The system is a **monular (modular) monolith**: FastAPI + synchronous services + multiple datastores co-located behind one HTTP API, Dockerized with healthchecks and `depends_on`.

## PART 3 — Master Feature Matrix

| # | Capability | Status | Where (source) |
|---|---|---|---|
| F01 | Admin bootstrap + seed users | ✅ DONE | `app/core/auth.py`, seed scripts |
| F02 | Login / logout / me | ✅ DONE | `core/auth.py`, `auth` router |
| F03 | Server-side token revocation (JTI denylist) | ✅ DONE | Redis denylist; live check 204→401 |
| F04 | Login throttling | ✅ DONE | Redis |
| F05 | 4 roles / 15 permissions RBAC | ✅ DONE | `core/rbac.py` |
| F06 | Account lifecycle PENDING→ACTIVE↔SUSPENDED→REJECTED | ✅ DONE | users router, admin UI |
| F07 | Case CRUD + search + pagination | ✅ DONE | `cases` router, API tests |
| F08 | Case status machine open→in_progress→closed→archived | ✅ DONE | model + guard tests |
| F09 | Case isolation (P0) | ✅ DONE (FIXED) | `dependencies.py`; P0 leak test |
| F10 | Closed/archived read-only (409 CASE_READ_ONLY) | ✅ DONE | `assert_case_mutable`, live checks |
| F11 | Case members (collaborator/viewer) | ✅ DONE | `cases` router/tests |
| F12 | Case assignment (lead/owner) | ⚪ MISSING | no model/field |
| F13 | Evidence upload → MinIO | ✅ DONE | `evidence`, `storage.py` |
| F14 | Evidence SHA-256 dedupe + format sniff | ✅ DONE | `evidence` services/tests |
| F15 | Evidence provenance + source_records | ✅ DONE | model + tests |
| F16 | Evidence soft delete (`deleted_at`) | ✅ DONE | migration `d2e3f4a5b6c7` |
| F17 | Evidence restore/recycle UI | ⚪ MISSING | none |
| F18 | Sync ingestion CSV/JSON/TXT | ✅ DONE | ingest router/services |
| F19 | Ingestion idempotency + job state machine | ✅ DONE | unique constraints + tests |
| F20 | Async ingestion queue/worker | ⚪ MISSING | synchronous in-request |
| F21 | Field/Rule/NER entity extraction | ✅ DONE | extraction services |
| F22 | Normalization + blocking keys | ✅ DONE | `resolution` services |
| F23 | Resolution AUTO_MATCH≥92 / REVIEW≥78 / NO_MATCH | ✅ DONE | `resolution.py` + tests |
| F24 | Accept / merge / split resolution UI | ⚪ MISSING | list-only REVIEW |
| F25 | Relationship extraction (20 rule templates) | ✅ DONE | `relations` services + tests |
| F26 | Relationship dedupe + confidence + provenance | ✅ DONE | services/tests |
| F27 | Neo4j MERGE projection (allowlist, chunked) | ✅ DONE | `graph_sync.py` + Cypher-injection test |
| F28 | Centrality suite (deg/in/out/between/closeness/PageRank) | ✅ DONE | analytics modules + tests |
| F29 | Bridge score | ✅ DONE | analytics |
| F30 | Communities (greedy modularity) | ✅ DONE | analytics |
| F31 | Pattern detectors (6) | ✅ DONE | pattern modules |
| F32 | Missing-link hypotheses | ✅ DONE | analytics |
| F33 | Network DNA (8 dims) | ✅ DONE | analytics |
| F34 | Priorities + relationship strength | ✅ DONE | analytics |
| F35 | Findings engine + scoring + dedupe + status RBAC | ✅ DONE | services + tests |
| F36 | Audit trail append-only + correlation IDs | ✅ DONE | audit service/router |
| F37 | Audit retention/export | ⚪ MISSING | none |
| F38 | Timeline (derived) | 🟡 PARTIAL | `timeline` router (audit-scoped) |
| F39 | Dashboard stats + recent cases | ✅ DONE | dashboard router |
| F40 | Admin user mgmt + error banner | ✅ DONE | admin router + UI |
| F41 | Deep-link hard-refresh of nested routes | 🔴 BROKEN | PROJ_VIEW Finding 1 |
| F42 | Reporting / PDF / CSV / JSON export | ⚪ MISSING | none |
| F43 | Alerting / notifications | ⚪ MISSING | none |
| F44 | Password reset / email verify / MFA / OIDC | ⚪ MISSING | none |
| F45 | AI/ML analysis, LLM, embeddings, RAG | 🔴 MISSING (greenfield) | verified empty |
| F46 | IoT device registry / telemetry / gateway | 🔴 MISSING (greenfield) | verified empty |
| F47 | Soup AI integration | 🔴 NOT IMPLEMENTED | verified empty |
| F48 | Path-finding (backend) + UI | 🟡 PARTIAL | `/graph/paths` exists, no UI |

---

## PART 4 — Frontend Audit

### Pages (23, `src/app/pages/`)
`login.tsx register.tsx pending.tsx no-access.tsx 404.tsx dashboard.tsx cases.tsx case-detail.tsx entities.tsx entity-detail.tsx evidence.tsx graph.tsx analytics.tsx hypotheses.tsx findings.tsx timeline.tsx audit.tsx users.tsx admin-users.tsx settings.tsx` + others (incl. evidence views).

### Routing & auth flow
- `src/app/` router guards; `stores/auth.ts` — login stores token, **logout is now async** (`api.auth.logout()` → server revocation → clear local).
- **🔴 Finding (F41):** hard page load / browser refresh on a nested `/app/*` URL renders the **dashboard**, not the nested route. Only in-SPA navigation reaches nested routes. Root cause: route-guard/nested-route resolution on initial load. Screenshots in `PROJECT_VIEW_REPORT.md` captured via in-SPA navigation for this reason.
- Mock/real switch: `src/config/env.ts` (`VITE_USE_MOCK_API`); mock is the default. Real adapter → `api/client/http.ts` (token header, `X-Request-Id`, error-envelope decode). **Parity test** enforces identical mock/real API surface.

### Graph UI
- `components/graph/cyto-graph.tsx` (Cytoscape.js): node/edge expansion, communities coloring, `fitSignal` zoom (previously broken on re-render — fixed in remediation).
- Analytics page: centrality tables, network DNA, pattern cards, hypotheses, priorities.

### Tests
- 13 vitest files / 56 tests — adapters, stores, guards, graph helpers. No Playwright/e2e in CI.

### Frontend quality
- `tsc` clean, `eslint` clean. No frontend CI job in `.github/workflows/ci.yml` (gap).

### Frontend verdict
| Theme | Verdict |
|---|---|
| Authentication + session | ✅ solid |
| Case + evidence workflows | ✅ solid |
| Graph exploration | ✅ solid (cytoscape) |
| Analytics + findings | ✅ solid |
| Review loops (resolution accept/merge, evidence restore) | ⚪ missing UI |
| Deep-link navigation | 🔴 broken |
| Real mode exercised by humans daily | 🟡 risky (mock default) |

---

## PART 5 — Backend / API Audit

### Routers & endpoints (55, `/api/v1`)
`auth` (login/logout/me), `cases` (CRUD/search/members/status), `evidence` (upload/list/get/content/delete/metadata), `ingestion` (ingest/jobs/retry-graph-sync), `entities` (list/get/resolution review), `relationships` (list/create/delete), `analytics` (centrality/communities/patterns/hypotheses/dna/priorities/strength/runs), `findings` (list/get/status), `timeline` (derived), `audit` (list), `dashboard` (stats/recent), `admin/users` (approve/reject/suspend/activate/change-role), plus `graph` (nodes/edges/paths). All documented in `backend/docs/frontend-contract.md`.

### Guard / security wins (verified)
- P0 case isolation: `list_cases`/`get_case` scope to membership (stranger sees **0** — live check).
- Closed/archived enforcement: evidence upload/delete, ingestion, analytics runs, finding status changes, member changes, case content PATCH → **409 CASE_READ_ONLY** (live checks).
- Cypher-injection rejection for Neo4j MERGE types (allowlist + test).

### Findings / weaknesses
- Synchronous ingestion (in-request) — latency/memory risk; no queue/worker.
- Single historical analytics run persisted; GET endpoints **compute live** — past-run versioning incomplete.
- No pagination metadata on some lists beyond limit/offset.
- No bulk entity operations endpoint (import/export master records).
- Error codes centralized in `core/codes.py` (INVALID_CREDENTIALS, CASE_ACCESS_DENIED, CASE_READ_ONLY, ACCOUNT_* etc.) — consistent envelope `{"error":{code,message}}`.

### API verdict: ✅ functional, 🟡 scalability gaps (sync ingestion, live compute, no worker pool).

## PART 6 — Database Audit

### PostgreSQL (source of truth) — 23 models
- Users, accounts (lifecycle state + role), cases, case_members, evidence (with `deleted_at` soft delete), evidence_sources / source_records, ingestion jobs (+ state), entities + aliases + blocking keys, relationships (+ provenance), findings, audit_logs, analytics runs/results, notifications (none wired). Enum/status columns, unique constraints for idempotency (dedupe).
- Migrations: linear 9-revision Alembic chain, head `d2e3f4a5b6c7`; `alembic upgrade head` auto-runs in `entrypoint.sh`; `alembic-check` green in CI.
- Audit logs: append-only by convention (no UPDATE/DELETE in service layer).

### Neo4j (graph projection)
- Graph is a **projection** synced from Postgres (`graph_sync.py`): MERGE entities/relationships, chunked, dedupe edges (same source+target+type merged with accumulated evidence).
- Relationship-type **allowlist** (7 types: CALLED, OWNS, WORKS_FOR, ASSOCIATED_WITH, LOCATED_AT, VISITED, TRANSFERRED_TO) → Cypher-injection rejection tested.
- Analytics read from Neo4j; authoritative storage remains Postgres (ADR 007).

### Redis
- Role 1: **JTI denylist** for logout/revocation (server-side invalidate).
- Role 2: **login throttle** (rate limiting on auth attempts).
- No cache layer for analytics/reads (potential future optimization).

### MinIO (S3-compatible object storage)
- Evidence blobs at `cases/<case_id>/evidence/<evidence_uuid>/<original_stem>` with metadata sidecars; SHA-256 fingerprint dedupes; streaming upload/download; content-type + encoding sniff. Uses transient dev buckets (local MinIO via compose).

### Data-flow integrity
Postgres = write source of truth → Neo4j = query store (best-effort sync, retryable via `retry-graph-sync`) → tree finalized. Buckets/bucket-lifecycle policies via minio-init only for dev.

### DB verdict: ✅ coherent, OMI sync retryable, soft-delete model present; ⚪ no analytics snapshots/versioning, ⚪ no backup/retention/monitoring config.

---

## PART 7 — Data Pipeline Trace (Evidence → Findings)

```
EVIDENCE (upload)
  ├─ MinIO blob (streamed)                      storage.py
  ├─ SHA-256 fingerprint → dedupe               evidence service
  └─ Postgres evidence row (provenance, source_records)
        │
INGESTION (job state: pending→running→completed/partial/failed)
  ├─ parse CSV/JSON/TXT (field aliases)          ingestion service
  ├─ extract entities: field maps + rules + NER  extraction
  ├─ normalize + blocking keys                    resolver
  ├─ resolve: AUTO_MATCH≥92 / REVIEW≥78 / NO     resolver (RapidFuzz .85,
  │   _MATCH                                    Jaccard .15)
  └─ master entity + alias rows                  Postgres
        │
RELATIONSHIPS
  ├─ 20 TYPE_PAIR_RULES + co-occurrence          relationship extractor
  ├─ dedupe + confidence + provenance            relationship service
  └─ edge rows                                   Postgres
        │
GRAPH SYNC (MERGE, allowlist, chunked, dedupe)    => Neo4j
        │
ANALYTICS (deterministic, evidence-attributed)
  ├─ centrality/bridge/communities/patterns/      analytics modules
  │   missing-link/DNA/priorities/strength
  └─ runs persisted (1 snapshot) + live GET       analytics service
        │
FINDINGS (engine-scored, evidence refs,          findings service
  dedupe across runs, status RBAC)
        │
AUDIT (append-only, correlation IDs)              audit service
```

Trace endpoints verified end-to-end by API + integration tests (341 backend tests). Each hop carries `evidence`/`source` provenance references.

---

## PART 8 — Security Audit

| Area | Assessment | Severity |
|---|---|---|
| Password storage | bcrypt | ✅ OK |
| Tokens | HMAC-SHA256 signed JTI bearer; 30-min expiry; Redis denylist revocation (live 204→401) | ✅ OK |
| Logout | server-side revoke + client clear (async logout fix) | ✅ OK |
| Login throttle | Redis | ✅ OK |
| RBAC | 4 roles / 15 permissions; dependencies enforce per-route | ✅ OK |
| Case isolation | membership-scoped reads/search (P0 fixed; stranger → 0 results) | ✅ OK (FIXED) |
| Closed/archived cases | 409 CASE_READ_ONLY for upload/delete/ingest/analytics/finding-status/member/content | ✅ OK (FIXED) |
| Csrf/XSS | SPA bearer; no cookies; React escaping | ✅ OK |
| Graph/query injection | HALO allowlist + Cypher-injection rejection test | ✅ OK |
| Error handling | centralized codes/envelope, no stack leakage | ✅ OK |
| Secrets management | **dev-only** `.env.example` placeholders; no vault/secret manager | 🔴 GAP |
| TLS | dev HTTP only; no cert/ingress config | 🔴 GAP |
| Backups/DR | none configured | 🔴 GAP |
| Monitoring/alerting | none (no logs pipeline, no metrics/APM) | 🔴 GAP |
| Audit export/retention | no export API, no retention policy/TTL | 🟡 GAP |
| Dependency vetting | no SBOM/anchore/govulncheck; pinned via lock? | 🟡 GAP |

**Summary:** functional in-app security (authz, isolation, revocation, throttling) is solid and regression-tested; **production infra security (TLS, secrets, backups, monitoring) is absent** — acceptable for SIH demo only.

---

## PART 9 — Test Coverage

### Backend (43 files / 341 tests — all passing from 602d688 through d53d5ac)
- 20 unit + 15 api (incl. `test_case_readonly_api.py`, P0 leakage test in `test_cases_api.py`) + 7 integration (Postgres/Neo4j/Redis/MinIO compose) + 1 e2e.
- Commands: `./.venv/bin/python -m pytest` (341 passed); ruff + mypy clean; `alembic-check` clean.
- Highlight regression-proofs: case isolation stranger-proof, closed/archived read-only-proof, logout revocation-proof, Cypher-injection-proof, idempotent ingestion-proof, dedupe-proof, analytics determinism.

### Frontend (13 vitest files / 56 tests — passing)
- adapters (mock vs real parity), stores, guards, graph helpers. No e2e (Playwright manual screenshots only).

### CI
- `.github/workflows/ci.yml`: backend lint+type+pytest against Postgres+Redis. **Missing:** frontend job, Neo4j, MinIO, e2e.

### Coverage verdict: 🟡 strong backend functional coverage; ⚪ no coverage on frontend CI/e2e, no headless browser tests, no load tests.

## PART 10 — Real vs Mock

| Dimension | MOCK (default) | REAL | Risk |
|---|---|---|---|
| API surface | `api/mock/index.ts` | `api/real/index.ts` → `/api/v1` | parity test enforces exact contract |
| Sessions | local token | server tokens + JTI revoke + **async logout** | none known |
| Data | seeded deterministic | Postgres/Neo4j/Redis/MinIO | seeding script not exercised in UI |
| Graph | handcrafted fixture | live projections | analytics determinism (seeded real pass unverified on stage) |
| Screenshots | `docs/project-view/` (20 PNG) | not captured | "real" visuals absent |
| Deep-link | broken nested nav (same in both) | same | **must fix before demos** |
| Demo risk | HIGH confidence UI | MEDIUM — needs one rehearsed real pass with moderate data | time, seed size |

**Recommendation:** run ONE seeded real-mode pass (e.g., 300–500 entities) + capture real screenshots; fix nested deep-link; ship a dedicated "SIH seeded dataset."

---

## PART 11 — AI/ML Current State

**Verified: NO AI/ML exists** (no openai/anthropic/langchain/tensorflow/transformers/prompt code; no embeddings; no model registry; no training/eval/orchestration). The only "intelligence":

- `spaCy` NER wrapper — lazy-loaded `xx_ent_wiki_sm`, gracefully degrades (🔵 wrapper only, not custom-trained).
- RapidFuzz fuzzy resolution + Jaccard co-occurrence scoring (classical, deterministic).
- Deterministic graph analytics (network DNA, patterns, priorities) — explainable heuristics, not ML.

**Target state (proposed architecture):**
1. **Extraction:** custom-trained NER (fastText/GLoVe or SAIL branch) for banking/crypto/fraud entities; `bertopic`/keyword clusters for case grouping.
2. **Resolution:** embeddings + cosine/threshold gating → dictionary/LLM name-resolution to lift AUTO_MATCH recall; confidence calibration.
3. **Analysis:** ML anomaly scoring (Isolation Forest on centrality), anomaly chains, pattern re-ranks by learned priors; time-series event anomaly for transactions.
4. **LLM Copilot (Soup)** — see Part 13; guardrailed tool-calling.
A model governance/versioning + eval harness + prompt cache layer must accompany any ML introduction; treat "AI claims" as **greenfield** in SIH.

---

## PART 12 — IoT: Current + Proposed

### CURRENT: 🔴 NONE
Verified by exhaustive search — no MQTT/WebSocket telemetry, no device registry, no sensor/telemetry schemas, no GPS/timestamps-from-IoT, no ESP32/embedded code in `backend/`, `frontend/`, `scripts/`, or `docs/`.

### PROPOSED: IoT Field-Capture MVP (hardware plan)
**Extraction device — ESP32-S3:**
| Module | Function |
|---|---|
| ESP32-S3 (Wi-Fi dual-core) | MCU + Wi-Fi, BLE; 4G HAT optional (SIM7600) |
| NEO-6M/NEO-8M GPS + active antenna | lat/lon/location, PPS-validated time |
| MPU6050 (IMU) | tamper/vehicle-motion detection (for custody/transport evidence) |
| BME280 | temp/humidity/pressure context (environmental witness) |
| Reed switch / CT clamp | door/open & power events (optional) |
| MicroSD slot | offline buffer (capture during no-signal) |
| 18650 + TP4056 + solar (10W panel) | ruggedized field power, deep-sleep duty-cycling |
| (Optional) OV2640 camera / LoRa SX1278 | image capture / mesh in dead zones |

**Firmware → Platform pipeline:**
```
ESP32-S3 firmware (C/Arduino-ESP32 or ESP-IDF)
  ├─ boot+self-test → SD buffer → TLS 1.2/1.3 WiFi/4G
  ├─ telemetry packet {ts, gps, imu, bme, rssi, bat, uid}
  ├─ optional image/audio capture
  └─ MQTT (QoS1) + HTTPS fallback (retry & backoff)
        │
  IoT GATEWAY (new backend service)
  ├─ MQTT broker binding (or map packet→HTTPS for SIH)
  ├─ device registry (auth via client cert/PSK; per-case)
  ├─ telemetry → ingestion events (evidence-linked)
  ├─ geofence/ROI events → timeline + map entity
  └─ dashboard: device health, GPS live map, sensor charts
        │
  ─ existing Evidence → Entity → Graph → Analytics → Findings pipeline
```
**SIH framing:** POC shipments (drug/counterfeit/smuggling), custody-tracked evidence transport (tamper/GPS chain), live field intel feeding the knowledge graph. **Hardware cost** ≈ INR 5–8k/unit; emphasize logistics + provenance story, not raw scale.

**Remaining (gate before claiming IoT):** device registry MVP, firmware repo, telemetry schema + ingestion adapter, WebSocket/MQTT in docker-compose, dashboard widgets, one end-to-end demo with real hardware.

---

## PART 13 — Soup AI Integration (NOT IMPLEMENTED)

### CURRENT: 🔴 NOT IMPLEMENTED
Verified — no reference to `Soup`, `https://github.com/MakazhanAlpamys/Soup`, LLM runtime, or prompt/agent scaffolding exists in the repo. All "soup/sensor" grep hits in docs/code were false positives.

### PROPOSED: Soup-CyberSaarthi integration architecture
`Soup` (fine-tuning + serving repo) hosts the **AI Copilot** that interacts with CyberSaarthi's **deterministic tool layer**:

```
Soup (external, own repo — MUST be forked/mirrored; NOT in this repo)
  train/finetune/serve LLM (e.g., Llama/Qwen-class) with
  investigation PII-safe and tool-calling eval harness
        │
        │ tool calls over HTTPS to /api/v1  (tool-calling)
        ▼
CyberSaarthi AI Tool Endpoints (source of truth stays deterministic)
  ├─ /copilot/{case}/search/entities|relations|evidence|findings
  ├─ /copilot/{case}/resolve (name→entity)
  ├─ /copilot/{case}/profile/{entity} (centrality/communities/strength+evidence)
  ├─ /copilot/{case}/timeline (derived)
  ├─ /copilot/{case}/paths/{a}/{b}
  ├─ /copilot/{case}/dna|priorities|patterns
  └─ gated by RBAC `ai.tools` + per-case permission; full audit
  ⇒ LLM returns answers + citations to CyberSaarthi evidence (#id refs)
```
**Guardrails:** no raw-minimum PII to model except curated context; every answer cites CyberSaarthi records; RBAC applied tool-side; prompt/answer audit; no autonomous writes (human confirms destructive ops).

**Milestones:** fork Soup + bake tool-serving contract → build `/copilot/*` tool endpoints (RBAC+) → Eval harness (N=50 curated queries, judge LLM, pass≥90%) → Copilot UI chat panel in `case-detail` → SIH demo (investigator asks: "profile 'X', what is their role in the smuggling network, and what evidence supports it?").

### Remaining (gate before claiming Soup/AI): tool endpoints, RBAC `ai.tools`, eval harness, chat UI, one rehearsed citation-backed demo.

## PART 14 — Gap Analysis Table

| Gap | Severity | Effort | Type | Owner-Implied |
|---|---|---|---|---|
| AI/ML (all) | 🔴 SIH-critical | L (greenfield) | Capability | greenfield |
| IoT (all) | 🔴 SIH-critical | M (gateway+firmware) | Capability | greenfield |
| Soup integration | 🔴 SIH-critical | L | Capability | external repo |
| Deep-link nested nav bug | 🔴 P0 | S | Functional | frontend |
| Reporting/export (PDF/CSV/JSON) | 🔴 P1 | M | Capability | backend+frontend |
| Async ingest/analytics workers | 🟡 P1 | L | Reliability/scaling | infra |
| Entity resolution review loop UI | 🟡 P1 | M | UX/func | frontend+backend |
| Case assignment/lead model | 🟡 P1 | S | Capability | backend+UI |
| Analytics run versioning | 🟡 P2 | M | Functional | backend |
| Timeline for analysts/viewers | 🟡 P2 | S | RBAC/UX | backend |
| Evidence restore/recycle | 🟡 P2 | S | UX | frontend |
| Password reset/email/MFA/OIDC | 🟡 P2 | M | Auth | backend+mail |
| Alerting/notifications | 🟡 P2 | M | Capability | backend |
| Audit retention/export | 🟡 P2 | M | Compliance | backend |
| Real-mode seeded demo pass | 🟡 P2 | M | Demo | data/tests |
| TLS/secrets/backups/monitoring/DR | 🔴 P2 (ops) | L | Infra | devops |
| Frontend CI job + e2e | 🟡 P3 | M | CI | CI |
| Path-finding UI | ⚪ P3 | S | UX | frontend |
| Load/perf tests | ⚪ P3 | M | QA | infra |

---

## PART 15 — SIH Readiness

| SIH Pillar | Status | Notes |
|---|---|---|
| Aligns SIH26189 (network analysis for investigations) | ✅ Strong | evidence→graph→analytics→findings pipeline is the core ask |
| Working demo (mock mode) | ✅ Ready | 23 pages, seeded data, 20 screenshots |
| Working demo (real mode) | 🟡 Needs rehearsal | one seeded real pass + deep-link fix |
| AI narrative | 🔴 Greenfield | Soup/ML roadmap only; zero code |
| IoT narrative | 🔴 Greenfield | device/telemetry roadmap only; zero code |
| Production-readiness story | 🟡 Dev-grade | no TLS/secrets/backups/monitoring |
| Evidence of quality | 🟡 Strong backend tests; no e2e/load | 341+56 passing |

**Honest SIH statement:** the deterministic analysis platform is demo-ready; "AI" and "IoT" pillars must be presented as roadmap or built quickly. Dove-tailing: run the platform live with the **rehearsed real-mode dataset** for the pipeline story, and reserve AI/IoT as the *differentiator roadmap* to be demonstrated with the Soup Copilot + ESP32-S3 flow.

---

## PART 16 — Production Readiness

| Checklist | Current | Target |
|---|---|---|
| AuthN/Z | ✅ HMAC tokens, bcrypt, RBAC | ✅ + MFA/OIDC |
| Secrets | 🔴 env-var dev placeholders | ✅ Vault/Secret Manager |
| TLS/ingress | 🔴 plain HTTP | ✅ HTTPS, cert-manager |
| DB backups | 🔴 none | ✅ pg_dump cron + object-store point-in-time |
| Monitoring/alerting | 🔴 none | ✅ Loki/Prometheus/Grafana + pages |
| Log aggregation | 🟡 structured to stdout | ✅ + correlation IDs (exists) → Loki |
| Scaling | 🟡 docker-compose single-box | ✅ k8s/ECS + workers + queue |
| CI/CD | 🟡 single backend job | ✅ full matrix + e2e + deploy pipeline |
| Testing in CI | 🟡 no Neo4j/MinIO/frontend | ✅ add to matrix |
| DR | 🔴 none | ✅ off-site restore drill, RTO/RPO |

---

## PART 17 — Roadmap

**Phase 0 (foundation, NOW):** fix deep-link routing; add frontend CI job; seed+rehearse real-mode demo; write SIH story deck.
**Phase 1 (completeness, weeks):** entity-resolution review UI + API; case assignment; report/export v1; evidence recycle; timeline RBAC widening; analytics run versioning.
**Phase 2 (reliability):** worker/queue (Celery/TaskIQ) for ingestion+analytics; retry/backoff; idempotent job OMI; audit export/retention; monitoring (Prometheus/Loki); backups.
**Phase 3 (auth+ops):** password reset, email verify, MFA; secrets; TLS/ingress; DR drill; load tests.
**Phase 4 (IoT MVP):** device registry; ESP32-S3 firmware; telemetry ingestion; GPS/map widgets; one hardware demo.
**Phase 5 (Soup AI MVP):** fork Soup; `/copilot/*` tool endpoints + RBAC `ai.tools`; eval harness; chat UI; rehearsal demo.

---

## PART 18 — Final Feature Tree (as-built)

```
CyberSaarthi
├─ Platform
│  ├─ Auth+RBAC (4 roles/15 perms) ✅
│  ├─ Account lifecycle ✅
│  └─ Case management + status machine + isolation ✅
├─ Evidence
│  ├─ Upload→MinIO, SHA-256 dedupe, sniff ✅
│  ├─ Provenance + source_records ✅
│  └─ Soft delete (recycle UI ⚪)
├─ Ingestion
│  ├─ CSV/JSON/TXT sync, idempotent ✅
│  └─ Async workers ⚪
├─ Entities
│  ├─ Extract (field/rule/NER) ✅
│  ├─ Resolve (AUTO/REVIEW/NO_MATCH, blocking+RapidFuzz) ✅
│  └─ Review loop UI ⚪
├─ Relationships (20 rule templates, dedupe, provenance) ✅
├─ Graph
│  ├─ Neo4j MERGE projection (allowlist, chunked) ✅
│  └─ Live GET + paths ✅ (paths UI ⚪)
├─ Analytics (deterministic, evidence-attributed) ✅
│  ├─ centrality/bridge/communities/patterns/missing-link/DNA/priorities/strength ✅
│  └─ run versioning ⚪
├─ Findings (engine-scored, dedupe, status RBAC) ✅
├─ Audit + correlation IDs ✅ (retention/export ⚪)
├─ Timeline (derived, audit-scoped) 🟡
├─ Dashboard/Admin ✅
├─ AI/ML  🔴 greenfield
├─ IoT    🔴 greenfield
└─ Soup Copilot 🔴 greenfield
```

## PART 20 — Evidence Trail

### How each claim was verified
| Claim | Verification source |
|---|---|
| 341 backend tests passing, ruff/mypy/alembic green | `./.venv/bin/python -m pytest` (341 passed) + CI config; prior functional-verification run |
| P0 isolation, read-only 409s, logout 204→401 | Live HTTP checks during verification phase (recorded in `5992d688`/remediation reports) |
| File counts (backend 167 .py; frontend 80 ts/tsx; 23 pages; 11 routers; 23 models; 18 services; 12 analytics; 43 test files; 9 revisions) | `find`/glob/rg counts at audit HEAD `d53d5ac` |
| Deep-link nested-route bug | `docs/PROJECT_VIEW_REPORT.md` Finding 1 + manual navigation |
| Screenshots are mock-mode | `docs/PROJECT_VIEW_REPORT.md` Part 10 ("mock adapter, deterministic data") |
| No AI/ML/IoT/Soup/reporting/timeline-endpoint/export | `rg` across `backend/app`, `frontend/src`, `scripts`, `docs` (exhaustive search incl. misspellings); git log |
| Staging `HEAD d53d5ac`, `ahead 3` of origin, unpushed | `git log`/`git status` |
| 7 ADRs, 4 audit/arch reports, 20 screenshots, compose 7 services | directory listings + `docker-compose.yml` |

### Prior remediation artifacts (committed at HEAD)
- `docs/architecture/remediation-602d688-followup.md` (with the remediation commit `d53d5ac`)
- `docs/architecture/functional-verification-602d688.md`
- `docs/PROJECT_VIEW_REPORT.md`, `docs/project-view/*`

### Untracked items noted (not part of current audit)
`docs/PROJECT_VIEW_REPORT.md` and `docs/project-view/` were present as untracked files in working tree but are referenced as documentation of the same environment.

---

## FINAL STATUS

| Area | Status |
|---|---|
| Core platform (auth, cases, evidence, entities, relations) | ✅ COMPLETE |
| Backend API (55 endpoints, 11 routers) | ✅ COMPLETE |
| Frontend (23 pages, mock+real adapters) | ✅ COMPLETE (deep-link bug 🔴) |
| Database (Postgres + Neo4j + Redis + MinIO) | ✅ COMPLETE |
| Security (in-app authz/isolation/revocation/throttle) | ✅ COMPLETE (infra sec 🔴) |
| Analytics (deterministic, evidence-attributed) | ✅ COMPLETE |
| Testing (341 backend + 56 frontend, green) | ✅ COMPLETE |
| Deployment (Docker compose, CI backend) | 🟡 COMPLETE (frontend CI/monitoring missing) |
| Documentation | ✅ COMPLETE |
| AI/ML | 🔴 MISSING (greenfield) |
| IoT | 🔴 MISSING (greenfield) |
| Soup AI integration | 🔴 NOT IMPLEMENTED |
| Reporting/export | ⚪ MISSING |
| Alerting | ⚪ MISSING |

## REMAINING WORK
- **P0:** deep-link nested-route fix; real-mode seeded rehearse.
- **P1:** reporting/export; resolution review-loop UI; case assignment; async workers/queue; frontend CI.
- **P2:** analytics run versioning; timeline RBAC widening; evidence recycle; MFA/OIDC/password reset; audit retention/export; TLS/secrets/backups/monitoring/DR.
- **P3:** path-finding UI; load tests; procedure docs; e2e headless; cloud migration.

## RECOMMENDED NEXT ACTION
1. Fix the deep-link routing bug (quick, high demo-impact).
2. Build the **real-mode seeded SIH demonstration** (evidence → graph → analytics → findings) and capture real screenshots.
3. Begin **IoT Gateway + device registry MVP**, then the **Soup Copilot tool endpoints + eval harness**, as the two greenfield differentiators — both gated behind the stable deterministic core so SIH messaging stays honest.
4. Add frontend CI + e2e and one `/copilot/*` feasibility spike before committing to the AI story.

<div align="center">
<i>Report generated by audit at commit d53d5ac.<br/>NO SOURCE FILES WERE MODIFIED. NO COMMITS MADE.</i>
</div>
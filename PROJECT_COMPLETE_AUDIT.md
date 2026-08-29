# CyberSaarthi — Project Complete Audit

- **Audit date:** 2026-08-29
- **Repo root:** `/home/xhroot/Documents/ai/cybersaarthi`
- **Baseline commit:** `e59caa7` (`feat(analytics): add investigation intelligence engine`)
- **Scope:** full repository — backend API, analytics engine, data model + migrations, tests, containerization, docs, frontend placeholders.
- **Version:** `0.1.0` (FastAPI modular monolith, Python 3.12)

---

## 1. Executive summary

CyberSaarthi is a 4-commit project (Phase 1 → Phase 3) built as a clean, singular FastAPI **modular monolith** with a PostgreSQL source of truth, an idempotent Neo4j graph projection, MinIO object storage, Redis cache, and a fully deterministic (explicitly "no fake AI") investigation-intelligence analytics engine.

**Verified healthy:** the full test suite passes (**143/143 tests**), `ruff check` and `ruff format --check` are clean (116 files), `mypy` is clean (83 source files), migrations apply cleanly to a single head, and the containerized stack runs with all health checks green.

**Non-blocking issues found:** (1) `alembic check` reports schema drift on two `metric_results` single-column indexes created by the Phase 3 migration but no longer declared in the model; (2) the root `README.md` is stale relative to Phase 3; (3) zero auth endpoints exist despite the architecture doc scheduling them for Phase 3; (4) several documented scale/UX caveats. Details in §8.

---

## 2. Repository layout

```
cybersaarthi/
├── README.md                     # STALE - describes Phases 1+2 only
├── Makefile                      # dev entry points (up/down/seed/test/lint/typecheck/migrate)
├── docker-compose.yml            # backend + postgres + neo4j + redis + minio + minio-init
├── .env.example                  # committed dev template (all dev defaults)
├── .gitignore                    # ignores .env, venv, caches, local data dirs
├── docs/
│   ├── adr/001..007              # modular monolith, docker-first, pg+neo4j, minio,
│   │                             #   evidence provenance, entity resolution, pg-source-of-truth
│   └── architecture/
│       ├── phase-1.md            # foundation (snapshot)
│       ├── phase-2.md            # evidence pipeline  - STATUS: Implemented
│       └── phase-3.md            # analytics engine   - STATUS: Implemented
├── backend/
│   ├── app/                      # api/, analytics/, core/, db/, models/, repositories/, schemas/, services/
│   ├── migrations/env.py + versions/  # alembic async env; 4 migrations, single head
│   ├── scripts/seed_demo.py           # deterministic idempotent demo (DEMO-2026-001)
│   ├── scripts/preview_analytics.py   # headless analytics preview of the seeded case
│   ├── tests/                    # unit/ (11 files), api/ (4), integration/ (5) = 143 tests
│   ├── Dockerfile                # python:3.12-slim, non-root appuser uid 1000
│   ├── entrypoint.sh             # alembic upgrade head, then exec $@
│   ├── alembic.ini
│   └── pyproject.toml            # pinned deps + ruff/mypy/pytest config
├── frontend/  ml/  infra/  data/ # EMPTY placeholders (no implementation)
└── scripts/phase3_api_dump.sh + phase3_api_complete_dump.txt   # UNTRACKED session artifacts
```

Git history (4 commits): `54193a2` Phase 1 foundation → `fdaa4ac` Phase 2 data-intelligence pipeline → `669951d` fix(collapse duplicate logical graph edges) → `e59caa7` Phase 3 investigation-intelligence engine.

Uncommitted on disk (`git status`): `scripts/phase3_api_dump.sh` and `phase3_api_complete_dump.txt` — live-API dumps generated this session, not part of the product.

---

## 3. Architecture & design principles

- **Modular monolith** (ADR-001), assembled in `app/main.py` lifespan: `Database` (async SQLAlchemy + psycopg3), `GraphStore` (Neo4j async driver), `Cache` (redis.asyncio), `Storage` (boto3 → MinIO, AWS sigv4). Infrastructure probes are **non-fatal** — the API boots and reports readiness via `/api/v1/ready`.
- **PostgreSQL is the source of truth** for entities/relationships/findings/metrics; **Neo4j is a bounded projection** used *only* for `allShortestPaths` traversal (ADR-007). `GraphSyncService.sync_case` is idempotent (MERGE keyed by PG ids, sublabels like `:Entity:PERSON`, auto `ensure_indexes`).
- **"No fake AI"** principle (documented in `phase-3.md`): all scoring is deterministic graph math; every finding carries an explanation and evidence lineage; the engine never asserts guilt; timing is never fabricated; entity resolution is blocking-key + RapidFuzz with context signals — no random/hardcoded confidence.
- Well-defined config surface (`app/core/config.py`, pydantic-settings). Notable defaults: `RESOLUTION_AUTO_THRESHOLD=92`, `RESOLUTION_REVIEW_THRESHOLD=78`, `EVIDENCE_MAX_SIZE_BYTES=5MB`, `SPA_MODEL=en_core_web_sm`, `ANALYTICS_GRAPH_NODE_CAP` (gates exact-vs-sampled graph algorithms), `MAX_HOPS_LIMIT=8`.

---

## 4. API surface (all under `/api/v1`)

No authentication on any endpoint (see finding §8.3).

| Area | Routes |
|---|---|
| Health | `GET /health`, `GET /ready` (probes postgres/neo4j/redis/object_storage; 503 when not ready) |
| Evidence | `POST /cases/{id}/evidence` (multipart, minio, SHA-256 dedupe), `GET /cases/{id}/evidence`, `POST /cases/{id}/ingest`, `GET /cases/{id}/ingest-jobs`, `POST /cases/{id}/ingest/{job_id}/retry-graph-sync` |
| Entities | `GET /cases/{id}/entities` (filters entity_type/status/query, limit≤500), `GET /cases/{id}/entities/{eid}`, `GET /cases/{id}/relationships`, `GET /cases/{id}/resolution/review` |
| Graph | `GET /cases/{id}/graph`, `GET /cases/{id}/graph/entity/{eid}`, `GET /cases/{id}/graph/stats` |
| Analytics (14) | `GET /analytics/summary`, `/centrality`, `/communities`, `/entities/{eid}/analytics`, `/network-dna`, `/priorities`, `/strength`, `/paths`, `/paths/entity/{eid}`, `/patterns`, `/hypotheses`, `POST /analytics/run`, `GET /analytics/runs` (+ run detail) |
| Findings | `GET /findings`, `GET /findings/stats`, `GET /findings/{fid}`, `PATCH /findings/{fid}/status` |

Error handling is clean: uploaded-file validation → 413/400 `UploadValidationError`; missing case → 404 via `get_case_or_404`; unknown/foreign evidence on ingest and retry → `ValueError` mapped to 404.

---

## 5. Domain vocabulary

- **Entity types (8):** `person`, `phone`, `vehicle`, `organization`, `account`, `location`, `document`, `event`
- **Relationship types (7):** `called`, `owns`, `works_for`, `associated_with`, `located_at`, `visited`, `transferred_to`
- **Finding types (5):** `pattern`, `anomaly`, `hypothesis`, `network_insight`, `relationship_insight` · severities LOW/MEDIUM/HIGH/CRITICAL
- **Finding statuses:** `NEW`, `REVIEWED`, `DISMISSED`, `CONFIRMED`
- **Run statuses:** `pending`, `running`, `completed`, `failed`
- **Metrics (10):** degree/in-degree/out-degree/betweenness/closeness/pagerank/community_count/bridge_score/spanning_score/relationship_strength
- **Network-profile tiers:** `FOCAL`, `SIGNIFICANT`, `MONITORED`, `PERIPHERAL`

### Evidence pipeline (Phase 2)
`validate (size cap + SHA-256 + charset-normalizer) → parse (CSV/JSON/TXT, strict) → extract (field aliases / rule regexes / spaCy NER, graceful degradation) → normalize (phones, vehicles, Aadhaar, org suffixes, honorifics) → resolve (blocking key + RapidFuzz; fuzzy 0.85 / context 0.15; ≥92 auto-merge, ≥78 review) → relationships (field-pair + co-occurrence via TYPE_PAIR_RULES) → ingest job → MERGE projection`.

### Analytics engine (Phase 3)
`compute_centrality` (6 metrics), `detect_communities` (greedy modularity), Network DNA (8 dimensions), priority scoring, relationship strength, 5 pattern detectors (shared identifiers, bridge entities, circular structures, rapid expansion, relationship concentration), hypothesis generation with missing-link likelihood, Neo4j bounded path extraction (≤8 hops), and per-finding `build_explanation`. On-demand analytics because it "never wants stale results". Node-cap throttling switches exact→sampled for very large graphs, clearly labeled as approximation in explanations.

**Scoring weights:** Network-DNA 8 dims — prominence .20, influence .15, bridging .20, reach .10, anchorage .10, activity .10, evidence_depth .10, community_span .05; tiers FOCAL ≥.70 / SIGNIFICANT ≥.45 / MONITORED ≥.25. Priority = .25·prominence + .15·influence + .20·bridging + .10·reach + .15·pattern + .15·hypothesis; tiers CRITICAL ≥.75 / HIGH ≥.55 / MEDIUM ≥.35. Relationship strength = .30·coverage + .15·type_diversity + .20·record_coverage + .20·file_independence + .15·resolution_confidence.

---

## 6. Data model & migrations

21 SQLAlchemy models (`app/models/`): Case, Entity, EntityAlias, EntityCandidate, EntityMatch, EvidenceFile, SourceRecord, IngestionJob, Relationship, RelationshipEvidence, Finding, AnalyticsRun, MetricResult, CommunityResult, NetworkProfile, DataSource, User, Role, UserRole, AuditLog, + Base. Canonical relationship uniqueness key: `(case_id, source_entity_id, target_entity_id, relationship_type)` enforced in the repository layer.

Migrations (`backend/migrations/versions/`, single head `a4b9c7e16d20`):
- `e308a313166d` — initial schema
- `f31fa700fb23` — canonical relationships
- `081a88d02574` — Phase 2 evidence data-intelligence pipeline
- `a4b9c7e16d20` — Phase 3 investigation-intelligence engine

`alembic upgrade head` runs automatically in `entrypoint.sh`; async env in `migrations/env.py`. **Note:** `alembic check` reports drift (see §8.1).

---

## 7. Quality gates — verification performed (2026-08-29)

| Gate | Command | Result |
|---|---|---|
| Tests | `pytest` (in backend container) | **143 passed** in 6.02 s |
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 116 files already formatted |
| Types | `mypy app` | Success, no issues in 83 source files |
| Migrations | `alembic heads` / `alembic upgrade head` | Single head; applied cleanly |
| Schema drift | `alembic check` | **FAILED** — 2 removed indexes (see §8.1) |
| Stack health | `docker compose ps` | backend, postgres, neo4j, redis, minio all `Up (healthy)` |

Test inventory (20 files, 143 tests):
- **Unit (118):** normalization 26, analytics algorithms 21, extraction 16, parsing 13, relationships 11, validation 10, resolution 6, config 6, security 4, readiness 3, errors 2
- **API-contract (13):** health 4, analytics-api 4, readiness 3, phase2-api 2 — each uses ephemeral cases created in PG and deleted afterward, so demo data is untouched
- **Integration (12):** postgres 3, entity-pipeline 3, storage 2, redis 2, neo4j 2 — a session-level autouse guard skips the whole suite with actionable messaging when Compose infra is unreachable

Environment note: the host-side `backend/.venv` is missing runtime/dev deps (`rapidfuzz`, `charset_normalizer`), so tests/gates must run inside the container (`make test` / `make lint` / `make typecheck`), which worked for every gate above. Remedy: `pip install -e ".[dev]"` into the local venv.

---

## 8. Findings

### 8.1 [Medium] Schema drift: `metric_results` single-column indexes
`app/models/metric_result.py` declares only composite indexes `ix_metric_results_case_metric` and `ix_metric_results_case_entity`. The Phase 3 migration `a4b9c7e16d20` additionally creates single-column `ix_metric_results_case_id` and `ix_metric_results_run_id`. Consequences:
- `alembic check` fails → "New upgrade operations detected: remove_index(ix_metric_results_case_id), remove_index(ix_metric_results_run_id)".
- Any *future* `alembic revision --autogenerate` would emit a drop of these indexes, degrading `run_id`/`case_id`-scoped lookups.

**Fix options:** (a) declare the two indexes in the model (`Index("ix_metric_results_run_id", "run_id")` etc.), or (b) if intentionally removed, commit an explicit `op.drop_index` migration so model, migration, and DB converge. Recommendation: (a) — `run_id` is a live FK used to scope metric rows and currently has no supporting index.

### 8.2 [Low] Stale root README
`README.md` describes "Phases 1 + 2" and states "no analytics scoring" / "no frontend" while Phase 3 is fully implemented (`docs/architecture/phase-3.md` → Status: Implemented) and served by this stack. Update README's feature matrix and quick-start to reflect Phase 3 (analytics endpoints, `make seed`, `preview_analytics`).

### 8.3 [Low] Auth scheduled for Phase 3 but not delivered
`docs/architecture/phase-1.md` non-goals state "Authentication endpoints and RBAC enforcement … endpoints are Phase 3." Phase 3 shipped analytics; there remain **zero** auth endpoints. The infrastructure exists and is unused: `User`/`Role`/`UserRole`/`AuditLog` models, bcrypt `hash_password`/`verify_password` (`app/core/security.py`), `UserService`, `UserRepository`, and the RBAC user/role tables. Every endpoint — including `PATCH /cases/{id}/findings/{fid}/status` — is unauthenticated. This is defensible as an honest scope deferral (phase-2.md lists auth as out-of-scope), but the gap should be explicit on the roadmap; the dependency factory (`app/api/dependencies.py`) is the natural injection point.

### 8.4 [Low] Synchronous ingestion in the request path
`POST /cases/{id}/ingest` parses, extracts, resolves, writes, and runs the Neo4j MERGE projection inline before responding. Documented as a deliberate single-worker local mode; at scale it should move to background tasks or a worker (job status/`graph_sync_status` fields already exist on `ingestion_jobs`).

### 8.5 [Low] N+1 alias reads in graph build
`EntityService.build_graph` loads aliases per entity (one query per entity). Fine at demo/pilot scale (~30 entities); with large cases, batch alias fetch per case would be preferable. `GET /cases/{id}/graph/stats` builds the full in-memory graph — same scale note.

### 8.6 [Info] Placeholders and untracked artifacts
`frontend/`, `ml/`, `infra/`, `data/` are empty. `scripts/phase3_api_dump.sh` and `phase3_api_complete_dump.txt` (625 KB) are untracked session artifacts — decide whether to commit a trimmed version or delete.

### 8.7 [Info] No CI configuration
No `.github/workflows` (or equivalents). All gates are manual via the Makefile. Recommend wiring a CI pipeline: lint + typecheck + unit tests always; API-contract tests when service creds available; integration tests gated on a Compose/CI service fixture.

### 8.8 [Info] Approximation throttle in analytics
Exact centrality/community math only runs while the case graph is within `ANALYTICS_GRAPH_NODE_CAP`; large cases fall back to sampled computation, with results explicitly labeled approximate in explanations. Intentional and well-documented — but consumers should know scores can be approximate at scale.

---

## 9. Recommendations (priority order)

1. Reconcile the `metric_results` indexes (model vs migration) and restore a green `alembic check` (§8.1).
2. Update `README.md` for Phase 3; add an explicit roadmap entry for auth/RBAC (§8.2, §8.3).
3. Add CI wiring for the three quality gates (§8.7).
4. Pre-fetch aliases per case to remove the N+1 in graph builds (§8.5).
5. Move ingestion to background execution while preserving the request-time job contract, then add a follow-up poll endpoint (§8.4).
6. Reinstall dev deps into the local venv so gates run without the container (§7).

## 10. Conclusion

The repository is internally coherent and genuinely runnable end-to-end: deterministic analytics, faithful provenance and explanation for every score, idempotent multi-store writes, and a green quality gate across tests, lint, format, and typing against the live stack. The open items are small, well-scoped, and none block the current phase. The single item that should be handled before further development is the migration/model drift (§8.1), because it will quietly surface in the next autogenerate.
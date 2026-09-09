# CyberSaarthi — Complete Project Audit

- **Audit date:** 2026-08-30
- **Audited commit:** `ce6b3b8` (HEAD, `feat: build premium CyberSaarthi investigation frontend`), tree `main`
- **Method:** read-only inspection, live stack verification (Docker Compose), full test/gate runs, API smoke tests, live performance + error-recovery probes, DB/Neo4j/Redis/MinIO inspection, dependency + secret scans. Nothing in application source was modified. Where something could not be verified it is explicitly marked **NOT VERIFIED**.
- **Confidence labels:** CONFIRMED (directly observed), LIKELY (strongly implied), POSSIBLE (plausible).

---

## 1. Executive summary

CyberSaarthi is a genuinely runnable, deterministic criminal-network analysis product. The Phase 1–4 backend is coherent: PostgreSQL is the source of truth, Neo4j is an idempotent projection for bounded traversal, Redis is used only for login throttling, MinIO stores evidence, analytics are recomputed on read and persist auditable snapshots, RBAC is enforced per request, and the frontend is a modern code-split React workspace with a mock-first adapter.

The verified baseline is strong: **245 backend tests pass (37s), 27 frontend tests pass, ruff/mypy/alembic/lint/typecheck all clean, production builds succeed, 42 API endpoints, `npm audit` clean, no secrets in git.** Multiple claims were not merely reproduced but disproven or refined (analytics crash at ~1k-node depth despite the documented 2 000-node cap; the Neo4j graph store is polluted with 61 case projections while Postgres holds one case; ~60 orphaned MinIO objects; the mock evidence-upload status diverges from the real backend and hides the Ingest action in the default demo; the real-mode case list filters on the client after a server `limit=100` fetch; login throttling **fails open during a Redis outage — confirmed live**).

**No CRITICAL security or data-loss issue was confirmed.** The most serious defects are a deterministic analytics `RecursionError` at moderate graph depth (HIGH), a Neo4j/MinIO lifecycle gap that accumulates stale projections and orphaned objects (HIGH, HIGH), and a real-mode frontend case-list pagination/search bug (HIGH). The SIH demo traverses the seeded path fine but **cannot demonstrate "upload → ingest → graph" in the default mock mode**, and **is not ready for a real-API frontend demo** until the case-list bug is fixed.

Overall score **72/100** (Functional, approaching Strong). SIH readiness **68/100**.

---

## 2. Current architecture

Modular monolith, single FastAPI app (`backend/app`), Dockerized services:

| Component | Role | Evidence |
|---|---|---|
| FastAPI backend (Python 3.12) | API, pipeline, analytics | single process, `uvicorn app.main:app` |
| PostgreSQL 16 | Source of truth | SQLAlchemy 2 async + Alembic |
| Neo4j 5 Community | Graph projection for bounded traversal | `graph_sync.py` MERGE projection |
| Redis 7 | Login throttle only | `throttle.py` |
| MinIO | Evidence object storage | `storage.py` |
| React 19 + Vite frontend | Workspace UI | code-split routes, mock adapter |
| `ml/`, `infra/`, `data/` | Empty placeholders | no implementation |

Layers: `api/routes` → `dependencies` (auth/RBAC/case access) → `schemas` (Pydantic) → `services` (validation/parsing/extraction/nlp/resolution/relationships/ingestion/graph_sync/analytics) → `repositories` → models. Analytics (`app/analytics/*`) are pure deterministic functions over PostgreSQL data.

---

## 3. Verified project capabilities

- **Deterministic analytics:** two live recomputes of `analytics/priorities` returned byte-identical payloads. CONFIRMED.
- **Findings never auto-`CONFIRMED`:** engine writes only `status="NEW"` (`analytics_repository.py:272`); transition endpoint enforces permission + validity. CONFIRMED.
- **RBAC + IDOR:** fresh role resolution per request; every case-scoped route calls `get_case_or_404`; live test confirmed 403 for an ANALYST on another user’s case, 401 anonymous, 404 missing case/entity, 422 bad UUID and `status="archived"` create. CONFIRMED.
- **Upload safety:** 5 MB streamed cap (413 live), SHA-256 dedup (409 live), server-generated object keys (path-traversal name sanitized to `.._.._evil.csv`). CONFIRMED.
- **Throttling:** 5 failed logins for one username then 429 (live); **fails open when Redis is down (confirmed live — see §8 A06 and §15)**.
- **SQL/Cypher:** parameterized everywhere except allowlist-derived type labels (`projects` verified); f-strings only in `paths.py` and `graph_sync.py:112` (both allowlist/DB-constrained). CONFIRMED.
- **Alembic:** single head (`cc19f4d2b003`), `alembic check` clean, live DB at head.
- **Frontend:** 35 JS assets, cytoscape isolated to the graph chunk, no `any`, no raw HTML injection paths.
- **Consistency math:** for the live demo case, Neo4j `case_nodes=45`, `case_edges=86` match Postgres exactly. The active case projection is *correct*; the *whole* Neo4j store is not (see finding A02).
- **Error recovery:** backend restart re-runs migrations and recovers; a Redis outage degrades readiness correctly (503) while liveness stays 200. §15.

---

## 4. Database audit

PostgreSQL 16 is the source of truth: SQLAlchemy 2 async models (`users`, `roles/permissions`, `cases`, `entities`, `relationships`, `evidence_files`, `analytics_runs`, `findings`, `audit_logs`), Alembic migrations linear to a single head. Live state after audit hygiene: 1 case, 5 users, 45 entities, 86 relationships, 5 evidence_files, 0 findings, 0 analytics_runs, 280 audit_logs — matching the seed.

| Check | Result |
|---|---|
| Migration chain | `e308 → 081a → f31f → a4b9 → cc19`, single head, `alembic check` clean |
| Live DB migration status | `cc19f4d2b003 (head)` |
| Indexes/constraints | PKs + FKs, unique on case/title, case/version, case/sha256, entity/role keys, finding `(run_id, rule_id)` |
| Pending vacuum/bloat | Not assessed (demo-sized) — NOT VERIFIED |

Findings:

- **A17 · LOW · Performance · `backend/app/api/routes/cases.py:80-87`.** `list_cases` loads the full accessible case-id set into memory before paginating (unbounded for an admin over many cases). Fix: push pagination into SQL. SIH blocker: No.
- **A10 · LOW · Security/performance (search) · `backend/app/repositories/entity_repository.py:93`.** Entity search uses `.ilike(f"%{query}%")` with **unescaped `%`/`_`** and free-form `query`; `display_value` is unindexed → full scan on broad queries. Fix: escape wildcards, `pg_trgm` GIN index. SIH blocker: No.
- **A14 · LOW · Migration safety · `backend/migrations/versions/f31fa700fb23_...` downgrade (data-destructive); `entrypoint.sh:5` runs `alembic upgrade head` on every start.** The Phase 2→relationship migration merges rows on upgrade and its downgrade cannot restore; concurrent replicas racing `upgrade head` could contend. Fix: single-writer start discipline + documented downgrade warning. SIH blocker: No.

The findings-dedup gap (A09) touches the DB; see §13.

---

## 5. Neo4j audit

Neo4j 5 Community holds the graph projection written by `graph_sync.py` (MERGE, idempotent), constrained typos/values; indexes on `entity_id`, entity key, case_id. Live counts (cypher-shell):

| Query | Value |
|---|---|
| `count(n:Entity)` | **597** |
| `count(DISTINCT n.case_id)` | **61** |
| `count(()-[r]->())` | 1 058 |
| Demo case only (nodes / edges) | **45 / 86 — matches PostgreSQL exactly** |

Findings:

- **A02 · HIGH · Data integrity · Neo4j lifecycle · `backend/app/services/graph_sync.py` + `app/services/ingestion.py` (no case-scoped delete), `app/api/routes/cases.py` (no DELETE/teardown), `backend/tests/*`.**
  The Neo4j projection is never removed when a case is deleted, and tests sync cases into the live store. The store now holds **597 Entity nodes across 61 distinct `case_id`s and 1 058 edges while PostgreSQL has 1 case (45 entities / 86 relationships)**. The README’s “source of truth, idempotent projection” claim is technically true per-sync but not at the store-lifecycle level — stale projections accumulate.
  - Why it matters: graph ≠ source of truth over time; every `pytest` run pollutes the graph DB; future case-id scans break; Neo4j memory grows (822 MB resident today).
  - Reproduce: run `pytest backend/tests/api`, then count `MATCH (n:Entity) RETURN count(DISTINCT n.case_id)`.
  - Expected: clean projection per case (delete with case) or a documented reconciliation job.
  - Actual: unbounded accumulation of ghost projections.
  - Fix: on case deletion run a scoped `MATCH (n:Entity {case_id:$id}) DETACH DELETE n`; clean the graph store in test teardown or use a throwaway graph database for tests.
  - SIH blocker: No (demo data safe) but corrupts the “consistent graph” story under live testing.
- **A11 · LOW · Security (Cypher hygiene) · `backend/app/services/graph_sync.py:110-129`.** The relationship type is interpolated into Cypher (`MERGE (a)-[r:{type}]->(b)`); safe today only because the DB check constraint limits types to seven enum values. It is the only non-parameterized Cypher fragment; a future change could reopen injection. Fix: validate the type against the allowlist before interpolation. SIH blocker: No.

---

## 6. Redis audit

Redis is used for **one thing**: rate-limiting failed login attempts (`throttle.py`), keyed by username with TTL. No cache, no session store, no queues — justified minimum. Live state: no keys at rest (throttle keys cleared/expired after tests).

Behavior verified live (§15): with Redis stopped, readiness correctly degrades to 503 while liveness stays 200 and all other endpoints are unaffected — **except** the throttle, which **fails open** (this is the A06 defect, full detail in §8).

---

## 7. MinIO audit

MinIO holds evidence objects with server-generated keys (sha256-derived, sanitized). Live bucket: **66 objects** for **5 evidence rows** → ~60 orphans (see A03). `storage.py` streams uploads at a 5 MB cap, so objects reach the bucket before the DB insert commits.

Findings:

- **A03 · HIGH · Data integrity / storage lifecycle · `backend/app/api/routes/evidence.py:168-179` + `app/db/storage.py` + `backend/tests/api/*`.**
  MinIO objects are written **before** the DB row is created and **never deleted** on failure or case deletion. Result: **~60 orphaned objects in the bucket for case ids that no longer exist in PostgreSQL** (live: 66 objects vs 5 evidence rows). The concurrent-duplicate upload path can also leave one orphan: upload (T1) → concurrent insert fails on `uq_evidence_files_case_sha256` → object stays. There is also **no DELETE evidence endpoint at all**.
  - Why it matters: unbounded storage growth; no API way to remove evidence.
  - Reproduce: run the API/evidence tests against the live stack, then list the bucket.
  - Expected: transactional or compensating cleanup (delete object if insert fails; delete objects on case deletion; reconciliation job).
  - Actual: orphans accumulate on every test run and on failed-duplicate uploads.
  - Fix: upload → insert → on failure `storage.delete(key)`; scoped deletion of a case’s objects; optional bucket reconciliation.
  - SIH blocker: No (demo case objects correct).

---

## 8. Security audit

**What is verified-good:** bcrypt password hashing, per-request RBAC with fresh role resolution, case-scoped access on every route (`get_case_or_404`), parameterized SQL/Cypher (except the listed A11 fragment), 5 MB + SHA-256 dedup upload guard, sanitized object keys, generic auth errors (no user-enumeration via login), defense headers present (nosniff, `X-Frame-Options: DENY`, no-referrer, X-XSS), disabled trailing-slash redirect. Live auth matrix in TEST_RESULTS.txt: 401/403/404/422/413/409/429 all behave correctly.

Findings:

- **A04 · MEDIUM · Security (confidentiality) · Audit trail · `backend/app/api/routes/audit.py:19-56` + `backend/app/core/rbac.py:82`.**
  `GET /audit-logs` requires only `PERM_AUDIT_READ` (granted to **INVESTIGATOR**) and accepts a `case_id` filter with **no ownership check**. Any investigator can read audit events (login success/failure, mutations) across every case and user.
  - Why it matters: cross-tenant metadata exposure inside the organisation; login timings/usernames of other accounts are readable by non-admin roles.
  - Reproduce: login as an INVESTIGATOR, `GET /api/v1/audit-logs`.
  - Expected: audit scoped to own cases + all cases for ADMIN only.
  - Actual: global read for every `audit.read` holder.
  - Fix: in the route, when actor is not ADMIN, restrict to cases owned/administered by the actor.
  - SIH blocker: No, but a security-conscious judge will probe it.
- **A05 · MEDIUM · Security (configuration) · `backend/app/core/config.py:81,105-126`.**
  `SECRET_KEY` defaults to the placeholder `"change-me"` and the production guard only runs when `APP_ENV == "production"` while `APP_ENV` defaults to `"development"`. An operator who forgets `APP_ENV=production` silently runs a “production” deployment with a known signing secret. `REDIS_URL` is exempt from the placeholder check entirely.
  - Fix: validate secret placeholders in any non-`development`/`test` environment, or require an explicit `APP_ENV`; include Redis; same for CORS origins.
  - SIH blocker: No (demo uses dev defaults) but a deployment foot-gun.
- **A06 · MEDIUM · Security (brute force / DoS) · Login throttle · `backend/app/services/throttle.py:30-57`, `auth.py:63-73`.**
  Throttling **fails open** on Redis outage (any exception → 0 attempts) and is keyed **only by username** (no IP dimension). A caller can (a) brute-force when Redis is down — **CONFIRMED LIVE**: with Redis stopped, 6 consecutive wrong logins all returned 401 with no 429 — and (b) trivially lock a victim account for 300 s by sending 5 bad logins (no exponential backoff, no IP dimension).
  - Fix: IP+username keying, per-IP budget independent of username, exponential backoff, documented fail-closed option.
  - SIH blocker: No.
- **A07 · MEDIUM · Security (session lifecycle) · `backend/app/core/auth.py`.**
  Tokens are stateless HMAC-signed bearer tokens with `exp` and an unused `jti`; there is **no logout/refresh/revocation/blacklist**. A leaked token is valid for its full 30-minute window.
  - Fix: optional server-side revocation via Redis `jti`, or short-lived access + refresh tokens.
  - SIH blocker: No.
- **A12 · LOW · Security (headers) · `backend/app/middleware.py:17-22`.** Headers cover nosniff/frame/ref-referrer/X-XSS but omit `Content-Security-Policy`, `Strict-Transport-Security`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`. Fix: add CSP + HSTS behind `APP_ENV=production` or proxy. SIH blocker: No.
- **F03 · MEDIUM · Authorization gap (UI) · `frontend/src/app/router.tsx:88` + `frontend/src/components/commands/command-palette.tsx:85`.** `/app/audit` sits under `RequireAuth` only (no route-level permission guard); the command palette offers “Open audit log” to every role. A VIEWER lands on an error state only after a real 403 request. (Backend still blocks correctly.) Fix: gate the route and palette action on `useCan("audit.read")`. SIH blocker: No.
- **F13 · LOW · Security (posture) · `frontend/src/api/client/session.ts:41-42`.** Token+user persisted to `localStorage` (XSS-exfiltratable; no `httpOnly`). Standard SPA tradeoff; permissions are correctly re-fetched on boot (good). SIH blocker: No.
- **F12 · LOW · Repo hygiene · `frontend/.gitignore` (no `.env*` rule).** A real env file would not be ignored if the frontend is published. Root `.gitignore` is fine. Fix: add `*.env`, `!.env.example`. SIH blocker: No.
- **F14 · LOW · Demo posture · `frontend/src/app/pages/login.tsx:13-18,126-151`.** Plaintext demo credentials shipped and rendered (mock-mode only). Acceptable for a demo, flagged for production. SIH blocker: No.

Secret scan (working tree + full git history): **no secrets found**; only test-fake passwords (`int-test-password`, `phase4-test-password!`). `.env` is correctly git-ignored.

---

## 9. Dependency audit

- Backend deps pinned exactly (`==`) in `pyproject.toml`; MIT license (see §19).
- `pip-audit` is **not installed** in the image → backend dependency-CVE status **NOT VERIFIED**.
- `npm audit` (frontend): **0 vulnerabilities** (CONFIRMED).
- The spaCy model is fetched from a GitHub wheel URL **without a hash pin** — supply-chain note; consider pinning by hash (-#sha256).
- Dev tooling (pytest/ruff/mypy/httpx) ships in the production image via `-e ".[dev]"` (see §10 A13).

---

## 10. Docker audit

Compose runs 6 services (backend, postgres, neo4j, redis, minio, minio-init); all healthy with `depends_on` health conditions (incl. `minio-init` completed). Backend image: non-root `appuser` (uid 1000), `entrypoint.sh` runs `alembic upgrade head` before start (CONFIRMED live in logs). `docker compose build backend` cached OK; `docker compose restart backend` recovered to `ready=200` on first boot (see §15).

Findings:

- **A13 · LOW · Supply chain / image hygiene · `backend/Dockerfile:14`.** The production image installs `-e ".[dev]"` (pytest, ruff, mypy, httpx) into the same image shipped to production. Fix: two-stage build or `--only main` install. SIH blocker: No.
- **I01 · MEDIUM · Resource isolation · `docker-compose.yml`.** No memory/CPU limits/ulimits for any service; Neo4j currently uses **822 MB** and MinIO 128 MB. On a laptop this is the most likely cause of OOM during a demo/build. Fix: `deploy.resources.limits` per service; pin `minio/minio` and `minio/mc` image tags (currently `latest`). SIH blocker: borderline — only if the host is memory-constrained.
- **I04 · INFO · Docker health.** Six services healthy; backend healthcheck hits `/health`; verified live (also §15 restart test).

---

## 11. Cross-platform audit

All shell scripts and the Makefile are LF/POSIX (verified: no CRLF anywhere); `entrypoint.sh` is POSIX sh; all workflows go through `docker compose`, so Windows + WSL/Git Bash is the expected path. `make` itself is not native to Windows cmd — documented assumption, LIKELY fine. No OS-specific code paths found in app source.

---

## 12. Testing audit

| Gate | Result |
|---|---|
| Backend pytest | **245 passed** in 37.05 s (40 files: 26 unit-normalization, 24 analytics-algorithms, 23 access-control, 21 findings-service, 16 extraction, 13 parsing, 11 relationships, 10 validation, 9 rbac, 9 auth-tokens, 8 analytics-api, 7 auth-api, 6 each resolution/config/findings-api, 5 throttle, 4 security, 4 health, 4 cases-api, 4 audit-api, 3 each readiness/postgres/entity-pipeline, 3 each readiness/provenance/observability, 2 each errors/storage/redis/neo4j, 20 more) |
| Backend coverage | **pytest-cov not installed** → **NOT VERIFIED** |
| ruff check / format | clean / 144 files formatted |
| mypy | clean, 96 files |
| Frontend vitest | **27 tests in 8 files** |
| Frontend eslint / tsc | clean |
| Alembic `check` | clean, single head |

Findings:

- **F06 · MEDIUM · Test isolation · `frontend/src/api/mock/index.ts:127-132` (module-level mutable state) + `frontend/src/api/mock/mock-adapter.test.ts:11-13`, `frontend/src/hooks/queries.test.tsx`.**
  Mock state (cases/evidence/findings/audit) is module-level and mutated by tests (e.g., a finding set to CONFIRMED) with **no reset between tests**; `beforeEach` only clears the auth session. Tests are order-dependent, and one test asserts the `pending` status that cements the F02 divergence.
  - Fix: expose a `resetMockState()` called in `beforeEach`; assert contract-correct `"stored"`.
  - SIH blocker: No.
- **Missing regression coverage:** no test covers graph depth > ~1 000 nodes (A01), no concurrency/idempotency tests (A08), no storage/orphan tests (A03). These are the highest-leverage additions right after the P0 fixes.

---

## 13. Data integrity audit

**Consistency snapshot (live, post-audit hygiene):** PostgreSQL: 1 case / 45 entities / 86 relationships / 5 evidence / 0 findings / 0 runs. Case-scoped Neo4j: **45 nodes / 86 edges — exact match**. Whole-store Neo4j and MinIO do **not** match (see A02/A03 — the lifecycle gap). Determinism: two recomputes of `priorities` were byte-identical. Findings engine only ever writes `NEW`; transition rules enforce validity + permission. `archive` preserves content; statuses validated at the Pydantic boundary (live 422 for creating an archived case).

Findings:

- **A02 → §5** (Neo4j lifecycle) and **A03 → §7** (storage lifecycle): neither graph store nor object store is transactionally bound to PostgreSQL, and teardown is never executed. These are the two HIGH integrity defects.
- **A09 · MEDIUM · Data growth · Findings persistence · `backend/app/repositories/analytics_repository.py`.**
  Each `POST /analytics/run` persists **~55 fresh findings**. Two runs produced 110 `NEW` rows with no dedup/retention policy; repeated demos/dev runs inflate the findings table and the review queue silently.
  - Fix: key/link findings to `run_id` with an expiry or collapse unchanged signals; document re-run semantics.
  - SIH blocker: No (seeded flows run once).

---

## 14. Observability audit

- `/api/v1/health` liveness and `/api/v1/ready` readiness are correct and *mean* different things — verified live: with Redis down, `ready` → **503**, `health` → **200**.
- Backend container healthcheck hits `/health`; service-level `docker compose ps` health states verified.
- Logs (uvicorn + structured app logs) accessible via `docker compose logs`; migration steps logged on start.
- Missing (deferred, no blocking impact): structured metrics/alerting, request tracing. `infra/` and `ml/` are empty placeholders (I02).

---

## 15. Error-recovery audit (live, non-destructive; stack restored)

| Scenario | Result | Verdict |
|---|---|---|
| `docker compose restart backend` | `/api/v1/ready` → 200 on first boot; `alembic upgrade head` re-ran; uvicorn listening | PASS |
| Redis stopped | `ready` → **503**, `health` → 200, `/api/v1/cases` → 401 (all other endpoints unaffected) | PASS (correct degradation) |
| Redis stopped, login attempts | 6 wrong logins → **all 401, no 429** — throttle **fails open** | FAIL — confirms A06 live |
| Redis restarted | `ready` → 200; 6/6 services healthy | PASS |

Notes: liveness vs readiness split is well-designed; the only observable misbehavior under a dependency outage is the fail-open throttle. Full Neo4j/MinIO/Postgres outage behavior and full migration downgrade/re-upgrade were **not** exercised (would be disruptive to the live demo volume) — assessed statically (A14).

---

## 16. Concurrency audit

- **A08 · MEDIUM · Concurrency · `backend/app/repositories/entity_repository.py:42-64` (entity create: plain insert + flush), `evidence_repository.py:20-30` (data source SELECT-then-INSERT), `evidence_repository.py:184-200` (ingest job with no `(case_id, evidence_file_id)` uniqueness).**
  Double-insert races: two concurrent ingests of the same new canonical value → one `IntegrityError` → that job marked failed; two concurrent uploads sharing a new `data_source` → 500 on the loser; two concurrent ingests of the same evidence file → redundant jobs (state-safe downstream, wasteful).
  - Reproduction: live NOT VERIFIED (would need parallel uploads); code path confirmed.
  - Fix: `on_conflict_do_nothing` + refetch for entity/data-source/job creation.
  - SIH blocker: No.
- A03 ties in: object-then-row ordering means a failed concurrent insert leaves an orphan object (superset of A08’s failure mode).
- The app currently runs a **single uvicorn worker**, which contains most real races today; the findings above matter as soon as workers ≥ 2.

---

## 17. Scalability audit

- **A01 · HIGH · Scalability / reliability · Analytics engine · `backend/app/analytics/graph.py:118-135` (`articulation_points`), called from `centrality.py:123` `compute_bridge_score` → `findings.py:196`.**
  Deterministic analytics use a **recursive DFS (Tarjan)** that overflows Python’s recursion limit on any connected component deeper than ~1 000 nodes, raising `RecursionError` → generic 500.
  - Why it matters: the app documents exact-algorithm support below `ANALYTICS_GRAPH_NODE_CAP = 2000` (`config.py:64`) and advertises graceful *approximation* above it. Both promises are false between ~1 000 and 2 000 nodes: the pipeline hard-crashes with no approximation notice.
  - Reproduce (live): inserted a synthetic case (1 500 entities, 3 000 edges spanning a single 1 500-cycle) → `GET /analytics/summary|centrality|communities|patterns|network-dna` all returned **500** after ~6.8 s; backend log shows `RecursionError: maximum recursion depth exceeded` originating at `graph.py:122 dfs`.
  - Expected: exact result below cap, sampled approximation + `approximation_notice` above.
  - Actual: 500 on every analytics reader.
  - Fix: iterative Tarjan (explicit stack) or raise the recursion limit defensively; add a ~1 200-node regression test; raise the effective cap only after converting to iterative.
  - SIH blocker: No for the 45-node seeded case; Yes for any larger live demo.
- **Probe numbers (live):** synthetic 1 500 entities / 3 000 edges: `entities?limit=50` 12 ms, `relationships` 20 ms (136 KB), `graph` 181 ms (874 KB), `graph/stats` 164 ms; *all analytics 500*. Synthetic case deleted after probe; dev DB restored.
- A09 (finding growth) and A17 (case-list load-all-ids) are slower-horizon scaling risks. A01 is the only hard ceiling today.

---

## 18. Performance & responsiveness audit

**Demo-case latency (live, 45 entities / 86 rels, cold-ish stack):**

| Endpoint | Latency | Payload |
|---|---|---|
| GET /api/v1/ready, /health | 8–14 ms | small |
| GET /cases | 15 ms | 400 B |
| GET entities / relationships | 19 / 16 ms | 11.7 / 26.8 KB |
| GET graph (+ stats) | 20 / 19 ms | 30.0 KB |
| GET evidence | 14 ms | 1.4 KB |
| GET analytics summary/centrality/communities | 61 / 44 / 42 ms | — |
| GET analytics network-dna / priorities / strength / patterns / hypotheses | 42–45 ms | 21–91 KB |
| POST analytics/run | ~83 ms (persist) | run snapshot |

Interactive scale is fine; the two UX-visible problems are the analytics 500 above ~1k nodes (A01) and stale/undercounting frontend state:

- **F04 · MEDIUM · Stale analytics UI · `frontend/src/hooks/queries.ts:338-347` (`useRunAnalytics`), `321-332` (`useIngestEvidence`).**
  Post-run/post-ingest invalidation covers runs/findings/findingStats/summary/timeline/audit/evidence/entities/graph but **omits** `networkDna`, `communities`, `priorities`, `strength`, `patterns`, `hypotheses`, `centrality` — those dashboard panels keep up to 60 s of stale data after the action. Fix: extend invalidation to every analytics-derived key. SIH blocker: No.
- **F05 · MEDIUM · Duplicate / undercounting dashboard fetch · `frontend/src/app/pages/dashboard.tsx:39,43-51`.**
  The dashboard issues two identical `cases.list({limit:100})` calls under different query keys, and derives Open/In-progress/Closed stats from a 100-case page — counts understate beyond 100 cases. Fix: single shared query; compute stats from server totals or a dedicated stats endpoint. SIH blocker: No.
- **F01 · HIGH · Real-mode case list · `frontend/src/api/real/index.ts:79-95`.**
  `caseService.list` requests server `limit/offset` (default `limit=100`) then filters by `search`/`status` **on the client** and sets `total = items.length` **after** filtering.
  - Why it matters: in real-API mode (a) search/filter only covers the first fetched page, missing matches beyond page 1, and (b) every consumer that trusts `total` (cases pagination, dashboard stats) gets wrong counts.
  - Reproduce: real API with >100 cases; search a title on page 2+.
  - Expected: server-side query params + true server total.
  - Actual: client-filtered page, inflated/wrong totals.
  - Fix: forward `search`/`status` (and pagination) to the backend; or filter across all pages in real mode.
  - SIH blocker: Yes for a real-API frontend demo.
- Bundle: index chunk ~462 KB raw / **~150 KB gzip**, graph chunk ~443 KB raw / ~145 KB gzip (cytoscape isolated — verified), 35 JS assets total / ~384 KB gzip. Fonts: 8 Inter files ~210 KB (F17). Build 3.27 s.

---

## 19. Licensing audit

Backend deps are MIT/BSD/Apache ecosystem; project itself MIT (pyproject + claim consistent). All Python deps pinned exactly (`==`). Frontend deps standard MIT (react, vite, tanstack-query, io-ts, cytoscape, mui ecosystem). The spaCy model wheel is fetched from a GitHub release URL **without a hash pin** (§9) — pin by hash for reproducibility. No license conflicts identified. (Full SPDX scan NOT VERIFIED — no tooling installed.)

---

## 20. Clean-install audit

Verified components (read-only, live stack):
- `git checkout` of `ce6b3b8` + `.env.example` → `docker compose up` boots 6 healthy services; backend auto-migrates on start (CONFIRMED live via restart test, §15).
- `docker compose build backend` cached clean; frontend `npm run build` clean in 3.27 s.
- Gates reproducible from a clean checkout: 245 pytest + 27 vitest + ruff + mypy + alembic + tsc all pass.
- **NOT VERIFIED:** a full wipe-and-rebuild of the Postgres/Neo4j/MinIO volumes (would destroy the seeded demo data) — assessed statically (Alembic chain linear, entrypoint auto-migrates, seed/init containers present).
- Clean-install gotcha: `README.md:38` still says `frontend/` is a placeholder (C02) — a fresh evaluator would not realize a frontend exists.

---

## 21. SIH demo audit (click-path)

The 13-step judge journey from the brief, against the **seeded + mock** build:

| Step | Route(s) | Clicks | Works? |
|---|---|---|---|
| 1 Login | `/login` | 1 | yes (demo cred quick-fill) |
| 2 Open case | `/app` → case card → `/app/cases/:id` | 2 | yes |
| 3–4 Upload evidence + ingest | `/app/cases/:id/evidence` | upload → **no Ingest button (F02)** | **no** |
| 5 Extract entities | entity tab | 1 | yes (seeded) |
| 6 Build graph | `/app/cases/:id/graph` | 1 | yes |
| 7 Run analytics | analytics tab → Run | 2 | yes (seeded graph; run persists) |
| 8–9 Discover/explain finding | findings detail | 2 | yes |
| 10 Show hypothesis | hypotheses tab + detail | 2 | yes |
| 11 Provenance/evidence | evidence drawer / entity detail | 2 | yes |
| 12 Human review | finding → Dismiss/Confirm | 2 | yes |
| 13 Audit trail | timeline/audit | 2 | yes |

**Friction:** the pipe-break is upload→ingest (default mode) — full finding F02 (below). Everything downstream works because the seed graph exists. Recommended demo script: start from the seeded case for steps 5–13; for step 3–4 either fix F02 or run against the real backend with a small CSV.

- **F02 · MEDIUM · Demo flow blocker · `frontend/src/api/mock/index.ts:479` + `frontend/src/app/pages/evidence.tsx:192,275`.**
  Mock upload returns `status: "pending"`; the backend returns `status: "stored"`. The UI renders the **Ingest** action only for `item.status === "stored"`, so in the default mock demo a freshly uploaded file can **never be ingested** — the “upload → ingest → graph” journey is impossible to demonstrate.
  - Reproduce: run the app in default mock mode, upload a CSV, observe no Ingest button on the new row.
  - Expected: uploaded file shows Ingest (status `stored`, or the UI accepts `pending`).
  - Actual: stale row with no action; the injected test even bakes in the divergence (`mock-adapter.test.ts:61`).
  - Fix: mock returns `"stored"` like the backend; add a “Demo auto-ingest” affordance or let a pending row still be ingested.
  - SIH blocker: **Yes for the default demo** — the flagship pipeline step cannot be shown.

---

## 22. IOC-extraction / entity-resolution audit

The extraction/resolution pipeline (validation → parsing → extraction → nlp/normalization → resolution → relationship building → ingestion) is exercised by seeded data and by a strong unit suite: 26 normalization tests, 16 extraction, 13 parsing, 10 validation, 6 resolution, 24 analytics-algorithm tests. Live behavior verified: upload → stored → entity parse runs synchronously (small files), duplicates blocked by SHA-256 (409 live), bad CSVs get a generic 422 (no data leak), extracted entities/relationships land in Postgres for the demo case (45/86). E2E investigator workflow (upload → ingest → query → analytics → review) covered in `tests/e2e`. Residual risks: entity/data-source non-idempotent creation under concurrency (A08) and no incremental-upload resume — acceptable for SIH.

---

## 23. Innovation / "wow factor" audit

Strengths already exposed in UI: knowledge-graph rendering with filters and inspector, per-entity network DNA + ego graph, deterministic priorities with tier labels, communities, centrality tabs, path explorer, hypothesis prompts clearly labeled unverified, provenance counts and evidence linking on every entity, honest mock/live labeling, immutable audit trail with case-scoped timeline.

Opportunities (non-gimmick):
- Surface `approximation_notice` / `exact_graph` from analytics responses in the UI — currently the engine distinguishes exact vs sampled but the UI never shows it.
- Show a relationship’s evidence list (source records) directly on hover/selection in the graph inspector.
- Add a “path” builder UI next to the inspector (data exists; UI only via API).
- Show per-finding the exact signals and source records that fired (data exists; UI shows approach/limitations text only).
- Add a live “evidence → entities → relationships” trace for one uploaded file to make the pipeline visible (addresses judge skepticism of “the graph just exists”).

---

## 24. Contract audit (frontend ↔ backend)

**What's consistent:** the TS type layer matches the live backend: `{error: {code, message}}` envelope, `open|in_progress|closed` + read-only `archived`, evidence statuses `stored|parsing|parsed|processing` (issued) distinct from `stored|parsed|processing|failed` (accepted), findings `NEW|CONFIRMED|DISMISSED|IN_PROGRESS`, 42 endpoint routes match the OpenAPI inventory.

Findings:

- **C01 · MEDIUM · Stale API contract · `backend/docs/frontend-contract.md:9` (error envelope `{status, code, detail}`), `:36` (CaseStatus list).** The live backend and the TS types agree on `{error: {code, message}}` and `open|in_progress|closed` (+ read-only `archived`); the contract doc agrees with neither. It also omits/mis-describes evidence status values and relationships pagination. Fix: regenerate the contract from OpenAPI. SIH blocker: No.
- **F07 · MEDIUM · Contract type drift · `frontend/src/types/domain.ts:47,95-106`.** `CaseCreateRequest.status` is typed as full `CaseStatus` (incl. `archived`) — the backend Pydantic schema rejects `archived` with 422 (live). Reads must tolerate `archived` but creates/updates must never send it. Three truth sources list three different status sets. Fix: narrow create/update types to `open|in_progress|closed`. SIH blocker: No.
- **F09 · LOW · Status labels · `frontend/src/app/pages/evidence.tsx:52-57`.** Backend knows `stored|parsed|processing|failed`; the UI maps `ingested|failed|processing` — `parsed` falls through to “Stored”, `ingested` does not exist in the backend vocabulary (mock-only). Fix: align map to backend + mock. SIH blocker: No.
- **F10 · LOW · Semantic divergence · `evidence.tsx:42-50` (hardcoded data-source chips) vs `mock/index.ts:456` (ignores `dataSource`) vs real backend (persists arbitrary `data_source` rows).** The same file shows different source strings in mock vs real mode. Fix: derive from the uploaded record / shared source vocabulary. SIH blocker: No.
- **F08 · LOW · Dead UI tab · `frontend/src/app/pages/analytics.tsx:26`.** The centrality tab list includes `eigenvector`; the backend never emits it (metrics are `degree|in_degree|out_degree|betweenness|closeness|pagerank`, `analytics.py:182`) and mock seed data has none — the tab is empty in **both** modes. Fix: remove the tab or implement the metric. SIH blocker: No.
- **C03 · LOW · Design-system drift · `frontend/docs/design-system.md`.** Lists z-index tokens not present in `globals.css` and claims “no raw hex in JSX”, violated by `dashboard.tsx:84`, `cyto-graph.tsx:10-19`. SIH blocker: No.
- **C02 · MEDIUM · Stale README/reports · `README.md:38` (“frontend/ placeholder — no implementation yet”), `frontend/docs/frontend-final-report.md` (“12 code-split route chunks”).** README predates the frontend commit; both documents contradict the actual tree. Fix: sweep docs against HEAD. SIH blocker: No.
- **F16 · INFO · Bundle/claim drift · build output.** Actual build produces **16+ lazy page chunks (35 JS assets total)**, not the “12 code-split route chunks” claimed. Index chunk is the largest initial payload (~150 KB gzip); graph chunk ~145 KB gzip (cytoscape isolated — verified). SIH blocker: No.

---

## 25. Code-quality audit

- Generally clean: no `TODO`/`FIXME`, no `console.log`, no `dangerouslySetInnerHTML`, no `any` in the frontend, ruff/mypy clean in the backend.
- Duplication: entity/relationship badge maps are centralized (`status.tsx`); the “status → label” mapping appears in multiple pages but is thin.
- Largest files: `frontend/src/api/mock/index.ts` (>800 lines) — a single mock switch handler mixing auth/cases/entities/evidence/analytics/audit; acceptable for now, worth splitting as the API grows.
- Over-abstraction risk: none significant; the `repository` layer reads cleanly. `app/analytics/findings.py` at ~690 lines is the largest module — algorithmic, acceptable.
- Frontend adjustments noted: F06 (test isolation), F11 (dead components), F15 (stale upload pick), F18 (error copy).
- **F11 · LOW · Dead code / doc drift · `frontend/src/components/ui/switch.tsx`, `tabs.tsx` (0 imports) while `docs/design-system.md:50` advertises them; `error-boundary.tsx` used only in `cases.tsx`.** Fix: remove or adopt. SIH blocker: No.
- **F15 · LOW · UX · `evidence.tsx:77-89`.** Closing the upload dialog with Cancel keeps the previously selected file; reopening shows a stale pick. Fix: clear `picked` on dialog close. SIH blocker: No.
- **F18 · LOW · Copy correctness · `frontend/src/components/ui/error-state.tsx:26`.** “No access to this case” is reused on the global audit 403 — restore per-context copy. SIH blocker: No.

---

## 26. Documentation audit (verified vs actual)

| Doc | Verdict |
|---|---|
| `README.md` quick-start, compose, Makefile, API surface | accurate except `frontend/ placeholder` (C02) and approximation claims (A01) |
| `docs/architecture/phase-*.md`, ADRs 001–007 | consistent with the current design |
| `docs/architecture/phase-4-security-checklist.md` | matches shipped behavior |
| `backend/docs/frontend-contract.md` | stale envelope + status list (C01) |
| `frontend/README.md`, `frontend/docs/design-system.md` | mostly accurate; minor drift (C03, F11) |
| `frontend/docs/frontend-final-report.md` | “12 chunks” claim wrong (F16); otherwise accurate |

---

## 27. Architecture assessment

The modular monolith remains appropriate: one FastAPI app with clean layers, Postgres as source of truth, Neo4j as bounded-path projection, Redis for throttle (justified, minimal), MinIO for evidence. No case for microservices/Kafka/LLMs/Kubernetes exists. The frontend’s facade + mock/real adapter split is maintainable and the right call for this stage. The two architecture leaks are lifecycle-related, not structural: **neither graph store nor object store is part of a transaction boundary with Postgres**, so teardown reconciliation must be explicit (A02/A03). The liveness/readiness split and fail-degraded behavior are well designed (§15). Recommend keeping the architecture and fixing the lifecycle gaps.

---

## 28. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| RecursionError during a live large-case demo | High | A01 fix before any >1k-node demo |
| Real-mode case list wrong at scale | High | F01 fix before real-API demo |
| Default demo cannot show upload→ingest | High (demo) | F02 |
| Neo4j/MinIO drift from source of truth | High | A02/A03 |
| Throttle fails open during Redis outage (brute-force window) | Medium (confirmed live) | A06 |
| Investigator reads global audit metadata | Medium | A04 |
| Placeholder secrets in a misconfigured prod | Medium | A05 |
| Findings table growth | Medium | A09 |
| Env/laptop OOM during demo (Neo4j 822 MB) | Medium | I01 |

---

## 29. Recommended roadmap

P0 — MUST FIX (blocks SIH demo quality / real-API demo):
1. A01 — iterative Tarjan/DFS or rebuild recursion headroom (`analytics/graph.py`, `unit/test_analytics_algorithms.py` + a ~1 200-node regression).
2. F02 — mock upload returns `"stored"`; UI accepts it (`mock/index.ts`, tests).
3. F01 — server-side search/status + true totals in `real/index.ts` (and mock parity).

P1 — SHOULD FIX:
4. A02 — Neo4j case teardown + test store hygiene.
5. A03 — storage cleanup on failure + case deletion; optional reconciliation tool.
6. A04 — audit route case-scoping for non-admin.
7. A05 — fail-closed secret validation.
8. A06 — IP+username throttling, exponential backoff (now live-confirmed fail-open).
9. F04 — full analytics query-key invalidation.
10. F05 — single dashboard query + correct stats.
11. A09 — findings per-run retention/dedup.
12. F03 — route-level audit guard.

P2 — NICE TO HAVE:
13. F08 remove eigenvector tab; F09 align status labels; F10 data-source vocabulary.
14. C01/C02/C03 — doc sweep; F16 correct chunk claim.
15. F06 test reset helper; A08 upserts; A10 ILIKE escaping + pg_trgm; A07 refresh/revoke.
16. A11 Cypher allowlist validation; A12 CSP/HSTS; A13 slim image; A14 migration notes.
17. I01 compose resource limits + pinned image tags; F12 `.env` ignore.
Follow-ups for the audit itself (next pass): install `pytest-cov` + `pip-audit` to close the two **NOT VERIFIED** gates.

---

## 30. Final verdict

- **CAN WE DEMO THIS TODAY?** — **YES** for the seeded mock path (login → case → entities → graph → analytics → findings → human review → audit). **NO** for demonstrating “upload → ingest → graph” in default mode (F02) and **NO** for large live cases (A01).
- **CAN WE SUBMIT THIS?** — **YES**, once P0 items (especially F02 for demo integrity) are addressed.
- **CRITICAL SECURITY ISSUE?** — **NO** confirmed.
- **CRITICAL DATA-INTEGRITY ISSUE?** — **NO** single critical; however Neo4j pollution + MinIO orphans are HIGH integrity defects that must precede any long-lived demo environment.
- **IS THE GRAPH RELIABLE?** — Partially: active-case projection matches Postgres exactly; the store as a whole drifts (A02).
- **IS ANALYTICS DETERMINISTIC?** — **YES** (identical recompute verified) for graphs under the recursion limit; 500 above ~1k depth (A01).
- **FRONTEND/BACKEND CONTRACT CONSISTENT?** — Mostly; TS types match the backend, contract doc is stale (C01) and a handful of divergences exist (F02, F07, F08–F10).
- **READY FOR REAL API FRONTEND DEMO?** — **NO** until F01 (and ideally A01) are fixed.
- **DEGRADED-OPERATION BEHAVIOR?** — Good design: Redis outage degrades readiness (503) without taking down liveness or the case/entity/auth paths; the one defect is throttle fail-open (A06, confirmed live).
- **Top 5 things to fix before SIH:** 1) F02 mock ingest flow; 2) F01 real case-list; 3) A01 recursion crash; 4) A02/A03 graph+storage teardown; 5) A04 audit scoping.
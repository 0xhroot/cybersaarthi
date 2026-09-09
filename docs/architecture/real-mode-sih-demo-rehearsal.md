# Real-Mode SIH Demo Rehearsal

Status: PASSED (43/43 rehearsal checks, all quality gates green)
Date: 2026-09-05
Commit: `fix: prepare real-mode SIH demo`

## 1. Purpose & Scope

This document records a full, deterministic rehearsal of the SIH 2026 demonstration using
**real infrastructure only** — no mock API adapter. It delivers the evidence required to
declare the product demonstration-ready:

1. **TASK 1** — nested-route hard-refresh bug fix (root cause: `frontend/src/app/router.tsx`
   only guarded `status === "idle"`; during `"loading"` the `<Routes>` mounted and
   `RequireAuth` redirected to `/login`, after which the login auto-redirect dropped the
   originally requested nested URL).
2. **TASK 2** — a real-mode rehearsal: deterministic 300–500-entity dataset ingested
   through the real pipeline (FastAPI → PostgreSQL → embedded Neo4j → MinIO), driven
   end-to-end through the live UI, with timings, screenshots, routing verification and a
   no-mock proof.

Scope is limited strictly to code changes required for these two tasks; no unrelated
refactors were performed (a tiny DOM-validity fix on the admin users page and an
evidence-list cache-invalidation fix exposed by the rehearsal are documented below as
in-scope rehearsal outcomes).

## 2. Environment & Topology

| Layer | Technology | State |
|---|---|---|
| Backend API | FastAPI (`backend`, port 8000) | `docker compose up -d`, healthy |
| Postgres | primary store | healthy |
| Neo4j | embedded graph (port 7687) | healthy, `NEO4J_PASSWORD=141` |
| Redis | queues / tools | healthy |
| MinIO | evidence object store | healthy, `minio-init` seeded buckets |
| Frontend | Vite 6.4.3 dev server (port 5173) | started with `VITE_USE_MOCK_API=false VITE_API_URL=http://localhost:8000` |
| Browser | Playwright 1.62.0 (Chromium 1234) | rehearsal driver |

NLP: `spacy 3.8.16` with `en_core_web_sm` in the backend container; config default
`SPA_MODEL="en_core_web_sm"`.

## 3. Deterministic Dataset

`backend/scripts/sih_demo_network.py` is a pure generator (no `app.*` imports, seeded RNG)
that emits three evidence files into `backend/scripts/sih_demo_seed/`:

| File | Format | Records | Purpose |
|---|---|---|---|
| `persons.csv` | CSV | 140 | people, phones, vehicles, organisations, accounts, cities |
| `transfers.json` | JSON | 144 | account-to-account transfers |
| `associations.txt` | TXT | ~48 links + 100 phone–location lines | affiliations + geolocation |

Generator invariants: `RNG_SEED=26189`, `SIH_CASE_NUMBER="SIH-2026-001"`, expected ~417
entities (140 person, 140 phone, 45 vehicle, 72 account, 12 organisation, 8 location).

## 4. Pipeline Seeding Run (Real Ingestion)

`docs/scripts/run_sih_seed.py` drives the real HTTP API (urllib, uses `Bearer` token):
case create → evidence upload (with 409-dedupe handling) → ingest per file → entity /
relationship / evidence counts → analytics run.

| Step | Result |
|---|---|
| Case create | `POST /api/v1/cases` → `7abf66e2-74c7-441a-a700-10005e7bc754`, case no. **CS-133649C0**, `in_progress`, owner `admin` |
| Upload `persons.csv` | 201, sha256 `447afb6c…`, stored under `cases/<case>/evidence/<uuid>/` in MinIO |
| Upload `transfers.json` | 201, sha256 `1ef09916…` |
| Upload `associations.txt` | 201, sha256 `8d4d117f…` |
| Ingest `persons.csv` | **8.76 s**, job `completed`, `graph_sync=synced` → 414 entities / 744 rels |
| Ingest `transfers.json` | **3.31 s** → 437 entities |
| Ingest `associations.txt` | **2.45 s** → 444 entities / 751 rels |
| Analytics run | **2.17 s**, status `completed` |

Neo4j mirrored the store: `MATCH (n)` = 444, relationships = 751 at seed time.

## 5. Canonical Counts (Final Rehearsed State)

Post analytics (`GET /cases/{id}/analytics/summary`), live at demo time:

| Metric | Value |
|---|---|
| Entities | **454** (300–500 target met) |
| Relationships | **770** |
| Communities | **38** |
| Max evidence per relationship | 13 |
| Average network score | 0.1946 |
| Profile tiers | PERIPHERAL 362 · MONITORED 84 · SIGNIFICANT 5 · FOCAL 3 |
| Priority tiers | HIGH 4 · MEDIUM 8 · LOW 442 |
| Findings | **55** (MEDIUM 42 · HIGH 10 · LOW 3) |
| Findings by type | pattern 25 · hypothesis 25 · network_insight 3 · relationship_insight 2 |
| Graph–DB parity | `exact_graph: true` |
| Evidence files | `persons.csv` (140), `transfers.json` (144), `associations.txt` (1), + 1 file uploaded through the UI during rehearsal (4 records) — all `parsed` |

## 6. UI Rehearsal (Playwright Driver)

`docs/scripts/rehearse_sih_demo.mjs` (Playwright 1.62.0) walks the live UI:

1. Direct-load `/app/cases` unauthenticated → redirected to login (register/sign-in gate shown). **275 ms**
2. Sign in as `admin` → returns to the originally requested route (`/app/cases`). **478 ms**
3. Dashboard greeting renders.
4. Open **SIH 2026 Demonstration** case.
5. Entities page (real table, person rows) — **868 ms**.
6. Graph page (browser canvas with real network) — **10.2 s** render+fit.
7. Analytics page (Network DNA + panes) — **4.1 s**.
8. Findings page (Bridge entity/anomaly rows) — **6.9 s**.
9. Evidence page lists all parsed files — **1.9 s**; provenance drawer shows entity /
   relationship / finding counts per source record.
10. **Live UI upload** of a fresh CSV (unique content hash) → stored **442 ms**; per-row
   **Ingest** → completed **12.2 s** (synchronous ingestion over HTTP).
11. Timeline (audit-derived) renders.

Screenshots: `docs/project-view/screenshots/real-mode/00…10-*-real.png` (11 captures),
distinct from the pre-existing mock screenshots (`docs/project-view/screenshots/01…20-*.png`).

## 7. Routing & Hard-Refresh Verification

13 routes × {direct `goto`, browser reload} = **26/26 PASS** — no redirect to login, no
dashboard fallback on any nested URL:

`/app`, `/app/cases`, `/app/cases/{id}`, `…/entities`, `…/evidence`, `…/graph`,
`…/analytics`, `…/hypotheses`, `…/findings`, `…/timeline`, `/app/audit`, `/app/settings`,
`/app/users`.

The unauthenticated bootstrap probe also verified `RequireAuth` state preservation:
requested route in `location.state.from` is returned to after login. The root cause was
fixed in `frontend/src/app/router.tsx` (keep the boot screen for both `idle` and `loading`
statuses); **not** a Vite/history fallback issue (the dev server serves `index.html` for
nested paths and the SPA entry was confirmed). Two regression tests were added in
`frontend/src/app/router.test.tsx` (status `loading` + direct nested URL → no login
redirect); 58/58 frontend tests pass.

## 8. No-Mock Proof

- Dev server started with `VITE_USE_MOCK_API=false VITE_API_URL=http://localhost:8000`.
- Rehearsal captured **173 real API calls**, all against `http://localhost:8000/api/v1/*`
  (`/auth/me`, `/auth/login`, `/cases`, `/cases/{id}/entities`, …). No request touched a
  mock adapter.
- `proxy-C2Wx-C1J.js` chunk observed in the production build output confirms the real
  HTTP client is wired for the non-mock path at build time.

## 9. Rehearsal Outcomes → Two In-Scope Fixes

The rehearsal surfaced and fixed two genuine issues:

1. **Evidence list did not refresh after upload/ingest/delete.** The page queries the list
   with key `["evidence", caseId, {limit:50}]`, but invalidation used
   `["evidence", caseId, undefined]` — a react-query key mismatch, so the list never
   refetched. Fixed in `frontend/src/hooks/queries.ts` by invalidating the
   `["evidence", caseId]` prefix (same pattern as the existing `["cases"]` invalidation).
   Verified live: uploading through the UI now appends the new row immediately, and the
   per-row **Ingest** action works (previously the row never appeared).
2. **Invalid DOM on `AdminUsersPage`** — `EmailCell` rendered a `<span>` directly inside
   `<tr>` (React dev-mode hydration/nesting warning, non-semantic table). Wrapped in a
   `<TD className="hidden md:table-cell">` matching the header breakpoint in
   `frontend/src/app/pages/admin-users.tsx`. Console is now clean during the rehearsal.

## 10. Quality Gates

| Gate | Command | Result |
|---|---|---|
| Frontend tests | `npx vitest run` | **58/58** PASS (13 files) |
| Frontend typecheck | `tsc -b --noEmit` | PASS |
| Frontend lint | `eslint .` | PASS |
| Frontend build | `npm run build` | PASS (vite 3.16 s, SPA `dist/` regenerated) |
| Backend tests | `docker compose run backend-dev pytest` | **341/341** PASS |
| Backend lint | `ruff check app tests` | PASS |
| Backend types | `mypy app` | PASS (100 files) |
| Schema drift | `alembic check` (in `/src`) | `No new upgrade operations detected` |
| Docker health | all services healthy | PASS |
| Real HTTP smoke | login, health, evidence, entities, analytics | PASS |
| Direct nested-route refresh | 26 routing probes | PASS |

## 11. Screening & Evidence Pack

All evidence referenced above is reproducible with the committed scripts:

- `docs/scripts/run_sih_seed.py` — deterministic pipeline seeding (idempotent).
- `docs/scripts/rehearse_sih_demo.mjs` — Playwright rehearsal + routing + no-mock proof
  (prints per-step PASS/FAIL; JSON summary at `/tmp/opencode/rehearsal_results.json`).
- `docs/project-view/screenshots/real-mode/` — 11 real-mode screenshots.
- `docs/project-view/REAL_MODE_DEMO.md` — operator runbook for the day-of demo.

## 12. Verdict / Demo Script

**SIH DEMO VERDICT: READY.** Refreshing rivers as expected, all routes survive hard
refresh, the real pipeline renders real data with `exact_graph: true`, the UI
upload→ingest loop works live, every quality gate is green, and the rehearsal is
deterministic and reproducible.

Residual risks (minor, mitigated, not blocking):
- **Graph render is the heaviest interaction (~10 s)** on the full 454-entity network —
  de-emphasise during the script by showing analytics/findings first, or filter the graph.
- Naturally synthesised data means low-suspense entity names; the demo narrative treats
  this as "synthetic test corpus", which is already the case title.
- The rehearsal adds a live-uploaded evidence file (unique content per run to bypass
  sha256-dedupe); state can be reset by re-running `run_sih_seed.py` against a fresh case.
- Playwright browser cache must use Chromium 1234 (Pin to `playwright-core@1.62.0` for
  the rehearsal driver; 1.63 needs a newer browser build).
# CyberSaarthi — Audit Metrics

Measured on 2026-08-30 against the live Docker Compose stack at commit `ce6b3b8`.

## Quality gates

| Metric | Result | Status |
|---|---|---|
| Backend tests (pytest) | 245 passed in 37.05 s | PASS |
| Backend test files | 40 (unit/api/integration/e2e) | — |
| Backend coverage | pytest-cov not installed in the image | NOT VERIFIED |
| Backend lint (ruff check) | All checks passed | PASS |
| Backend format (ruff format --check) | 144 files formatted | PASS |
| Backend typecheck (mypy app) | No issues, 96 files | PASS |
| Alembic check | No new upgrade operations | PASS |
| Alembic heads | single head `cc19f4d2b003` | PASS |
| Alembic current | `cc19f4d2b003 (head)` on live DB | PASS |
| Frontend tests (vitest) | 27 passed in 8 files | PASS |
| Frontend lint (eslint) | 0 problems | PASS |
| Frontend typecheck (tsc) | clean | PASS |
| Frontend build (vite) | succeeded in 3.27 s | PASS |
| Frontend dep security (npm audit) | 0 vulnerabilities | PASS |
| Backend dep security (pip-audit) | tool not installed | NOT VERIFIED |
| Secrets in git (working tree + full history) | none found | PASS |

## API surface

| Metric | Result |
|---|---|
| OpenAPI endpoints | 42 (26 GET, 1 POST case, 10 case-scoped POST/analytics/evidence/ingest/archive/status, etc.) |
| Routes versioned under | /api/v1 |
| Docker services | 6 (backend, postgres, neo4j, redis, minio, minio-init) |
| Service health | all healthy live |

## Live API latency (demo case — 45 entities, 86 relationships, 5 evidence files)

| Request | Latency | Payload |
|---|---|---|
| GET /health | 8 ms | 58 B |
| GET /ready | 14 ms | 95 B |
| GET /cases | 15 ms | 400 B |
| GET /cases/{id}/entities | 19 ms | 11.7 KB |
| GET /cases/{id}/relationships?limit=500 | 16 ms | 26.8 KB |
| GET /cases/{id}/graph | 20 ms | 30.0 KB |
| GET /cases/{id}/graph/stats | 19 ms | 356 B |
| GET /cases/{id}/evidence | 14 ms | 1.4 KB |
| GET /cases/{id}/analytics/summary | 61 ms | 561 B |
| GET /cases/{id}/analytics/centrality | 44 ms | 7.1 KB |
| GET /cases/{id}/analytics/communities | 42 ms | 2.8 KB |
| GET /cases/{id}/analytics/network-dna | 42 ms | 91.0 KB |
| GET /cases/{id}/analytics/priorities | 45 ms | 11.3 KB |
| GET /cases/{id}/analytics/strength | 45 ms | 89.8 KB |
| GET /cases/{id}/analytics/patterns | 42 ms | 21.6 KB |
| GET /cases/{id}/analytics/hypotheses | 42 ms | 32.6 KB |
| GET /cases/{id}/findings (empty) | 19 ms | 44 B |
| GET /cases/{id}/findings/stats (empty) | 11 ms | 46 B |
| POST /cases/{id}/analytics/run | ~83 ms (persist) | run snapshot |

## Scaling probe (synthetic case — 1 500 entities, 3 000 relationships, live)

| Request | Latency | Result |
|---|---|---|
| GET /entities?limit=50 | 12 ms | 12.6 KB |
| GET /relationships?limit=500 | 20 ms | 136 KB |
| GET /graph | 181 ms | 874 KB |
| GET /graph/stats | 164 ms | 281 B |
| GET /analytics/summary | ~6.8 s | **500 RecursionError** |
| GET /analytics/centrality | ~6.9 s | **500 RecursionError** |
| GET /analytics/communities | ~6.9 s | **500 RecursionError** |
| GET /analytics/patterns | ~6.9 s | **500 RecursionError** |
| GET /analytics/network-dna | ~7.0 s | **500 RecursionError** |

Synthetic case was deleted after the probe; the dev database was restored to its pre-audit state.

## Frontend bundle (production build, `npm run build`)

| Asset | Raw | Gzip |
|---|---|---|
| index (initial) | 462–474 KB | ~150 KB |
| graph (cytoscape chunk) | 443–454 KB | ~145 KB |
| proxy (shared chunk) | 122–125 KB | ~41 KB |
| remaining 15 pages+shared | 1–22 KB each | — |
| **Total JS (all 35 assets)** | — | **~384 KB** |
| CSS | 52 KB | — |
| Fonts (Inter subsets) | 8 files ~210 KB | — |

- 35 JS assets, 16 lazy page chunks (report’s “12 chunks” claim is stale).
- cytoscape imported only by `components/graph/cyto-graph.tsx` → graph chunk isolation confirmed.

## Runtime resource usage (docker stats, steady state)

| Container | Memory |
|---|---|
| backend | 151.7 MiB |
| postgres | 53.0 MiB |
| minio | 128.2 MiB |
| redis | 8.9 MiB |
| neo4j | **822.2 MiB** (no memory limit in compose) |

## Data consistency snapshot (live, post-audit hygiene)

| Store | Counts |
|---|---|
| PostgreSQL cases | 1 |
| PostgreSQL evidence_files | 5 (demo) |
| PostgreSQL entities / relationships | 45 / 86 |
| PostgreSQL findings / analytics_runs | 0 (reset to pre-audit) |
| Neo4j nodes / edges (case-scoped demo) | 45 / 86 — matches PG |
| Neo4j total nodes / distinct case_ids | **597 / 61** — stale projections (A02) |
| MinIO objects | 66 (≈60 orphans from test history; A03) |

## Behavioral checks (live)

- 401 anon / bad token; 422 bad UUID; 403 analyst-on-other-case (IDOR guarded); 403 analyst→audit-logs; 422 create with `status=archived`; 413 oversize upload; 409 duplicate-SHA upload; throttle 5×→429 then locked, key cleared after test; analytics recompute **byte-identical** across two calls (determinism); findings engine writes only `NEW`.
- Security headers present (nosniff/XFO/ref-referrer); CORS preflight 200 for a configured origin.

## Error-recovery / resilience (live, non-destructive; stack restored after)

| Scenario | Result | Status |
|---|---|---|
| `docker compose restart backend` | `/api/v1/ready` 200; `alembic upgrade head` re-ran on boot; uvicorn up | PASS |
| Redis stopped | `/api/v1/ready` → **503** (degraded reported correctly), `/api/v1/health` → 200 (liveness ok), `/api/v1/cases` → 401 (unaffected) | PASS |
| Redis stopped — login throttle | 6 consecutive wrong logins → **all 401, no 429** → **fail-open CONFIRMED live** (finding A06) | FAIL (per finding) |
| Redis restarted | readiness back to 200; 6/6 services healthy | PASS |
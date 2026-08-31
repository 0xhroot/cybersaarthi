# CyberSaarthi — Audit Executive Summary

**Audit date:** 2026-08-30 · **Commit:** `ce6b3b8` (HEAD `main`, working tree clean) · Read-only audit; no source modified.

## Scores

Methodology — each dimension is scored 0–100 from the number/severity of verified findings, and whether the dimension was directly exercised or reasoned from code. Overall = arithmetic mean. Bands: 0–39 Poor · 40–59 Needs major work · 60–74 Functional · 75–84 Strong · 85–94 Excellent · 95–100 Exceptional. **A project cannot exceed 90 with unresolved HIGH findings** — present here.

| Dimension | Score | Basis |
|---|---|---|
| **Overall** | **72/100** | Functional, approaching Strong |
| Security | 70/100 | Strong RBAC/IDOR/bcrypt/parametrization; placeholder-secret gate bypass (A05), throttle **fail-open on Redis outage (confirmed live)** (A06), no token revocation (A07), global audit read for INVESTIGATOR (A04), missing CSP/HSTS (A12) |
| Reliability | 66/100 | Analytics RecursionError on >1k-node graphs (A01); Neo4j + MinIO lifecycle drift (A02/A03); correct degraded-mode readiness under Redis outage (ally) |
| Performance | 71/100 | Sub-100 ms APIs on the demo case; graph payload 874 KB @181 ms at 1.5k nodes; analytics 500 (@A01); dashboards duplicate fetches (F05) |
| Testing | 77/100 | 245 backend + 27 frontend tests, all gates green, error-recovery live-tested; coverage NOT VERIFIED (pytest-cov absent); no scale/recursion tests; frontend test isolation defect (F06) |
| UX | 72/100 | Modern, consistent, honest demo labeling; broken mock ingest flow (F02), dead eigenvector tab (F08) |
| Architecture | 82/100 | Modular monolith, source-of-truth correctness, facade + mock/real adapter; lifecycle gaps at PG↔Neo4j/MinIO boundary |
| SIH readiness | 68/100 | Seeded demo works end-to-end except upload→ingest; not ready for a real-API demo (F01); analytic crash risk (A01) |

## Finding count

- **CRITICAL:** 0
- **HIGH:** 4 — A01 (analytic RecursionError), A02 (Neo4j stale projections), A03 (MinIO orphans), F01 (real-mode case list)
- **MEDIUM:** 10 — A04 audit scoping, A05 secrets gate, A06 throttle, A07 revocation, A08 concurrency, A09 findings growth, F02 mock ingest, F03 audit guard, F04 cache invalidation, F05 dashboard fetch, F06 test isolation, F07 type drift, C01/C02 doc staleness, I01 resource limits (some LOW-severity item rounding — see JSON)
- **LOW:** ~18 (see JSON)
- **INFO:** ~6

## Top 10 recommended fixes

1. **Make `articulation_points`/DFS iterative** (graph.py:118) — analytics must not 500 at ~1 000-node depth. (A01)
2. **Mock evidence upload returns `"stored"`** like the real backend — restore the default-demo upload→ingest flow. (F02)
3. **Server-side search/status + true totals in `real/index.ts` case list.** (F01)
4. **Delete Neo4j projections when a case is deleted** (+ test store hygiene). (A02)
5. **Compensating MinIO object deletion** on upload failure/case deletion. (A03)
6. **Scope the audit route to owned cases for non-admin.** (A04)
7. **Fail-closed secret validation** in any non-dev environment. (A05)
8. **IP-aware login throttling with exponential backoff.** (A06)
9. **Complete analytics query-key invalidation** after run/ingest. (F04)
10. **Findings per-run retention/dedup.** (A09)

## SIH verdict (details in PROJECT_AUDIT.md §30)

Demo today (seeded): **YES** · Submit: **YES** (after P0) · Critical security: **NO** · Critical data-integrity: **NO** · Graph reliable (store-level): **NO** until A02 · Analytics deterministic: **YES** (below crash threshold) · Contract consistent: **Mostly, doc stale** · Ready for real-API frontend demo: **NO** (F01).
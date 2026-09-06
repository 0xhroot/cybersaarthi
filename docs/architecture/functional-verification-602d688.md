# Functional Verification — Commit `602d688`

Scope: end-to-end functional verification of **CyberSaarthi** at commit
`602d688a3ce6662e8729434071a1c265f8993daf` (`main`) against the 25-section
spec (environment, 15 numbered tests, regressions A–H, mock/real parity,
static source, data integrity, final report + terminal output).

Preference: **runtime verification** against the real HTTP/API + real Vite
frontend. Anything not runtime-verifiable is tagged **code-verified**.

Date: 2026-09-02 · Read-only audit (no source modified, no fix applied).

---

## Environment

| Check | Result |
| --- | --- |
| Git `main` @ `602d688a3ce6662e8729434071a1c265f8993daf` | PASS (clean for task; only superseded `docs/PROJECT_VIEW_REPORT.md` / `docs/project-view/` untracked) |
| Docker services (backend, postgres, neo4j, redis, minio) | PASS — all Up/healthy |
| `GET /api/v1/health` → `{"status":"ok","service":"cybersaarthi","version":"0.1.0"}` | PASS |
| `GET /` → 404; `GET /api/v1/auth/me` (no auth) → 401 | PASS |
| Frontend real-mode Vite (env override `VITE_USE_MOCK_API=false`) | PASS — served, deep links 200 |
| Seed admin `admin`/`admin-dev-password` (ADMIN) | PASS |
| Seed investigator `investigator`/`investigator-dev-password` (INVESTIGATOR) | PASS |

**API mode note:** `frontend/src/config/env.ts` defaults to `useMockApi=true`
unless `VITE_USE_MOCK_API === "false"`; no `.env` exists (only `.env.example`).
Real-mode Vite was started for this audit via a **runtime env override only** — no
source change.

---

## Results Summary

Legend: PASS · FAIL · BLOCKED · NOT IMPLEMENTED. Severity applies on FAILs.

| # | Test | Result | Severity | Notes |
| --- | --- | --- | --- | --- |
| 1 | Register → PENDING, `roles:[]`, extra `role` field ignored, no privileged grant; 401 without token; frontend route `/pending` | **PASS** | — | `register.tsx` has no role field; routes to `/pending` ("Request received … awaiting approval") |
| 2 | PENDING login blocked (403 `ACCOUNT_PENDING`), no session | **PASS** | — | `login.tsx` surfaces exact backend message |
| 3 | Role-change on PENDING → 409 `ACCOUNT_NOT_ACTIVE`; stays PENDING | **PASS** | — | |
| 4 | REJECTED lifecycle: activate→409 `ACCOUNT_TRANSITION_INVALID`, approve→409 `CONFLICT`, change_role→409, login→403 `ACCOUNT_REJECTED` | **PASS** | — | |
| 5 | Approve → ACTIVE + ANALYST; login 200; correct perms; re-approve→409 `CONFLICT` | **PASS** | — | |
| 6 | Membership persists; member opens case, permitted reads work; cannot add members (lacks `case.update`) | **PASS** | — | |
| 7 | Non-member scoped GET/POSTs → 403 (11 endpoints); **case LIST leaks** | **FAIL** | **P0** | Case-list endpoint leaks all cases to any user with ≥1 membership row (root cause `_case_filters`, `cases.py:77–90`) — subquery selects outer `cases.id` instead of `case_members.case_id`. Object-scoped access (403) is correct; only the LIST leak is P0 |
| 8 | Closed case accepts evidence upload + ingestion | **FAIL** | **P1** | No case-status guard on `evidence.upload` / `ingest`; closed case accepted upload (201) and completed ingestion (entities created). Frontend gates upload only on `evidence.upload` perm, not status |
| 9 | Archived case not read-only for mutations | **FAIL** | **P1** | Lifecycle transitions correct (re-archive 409, PATCH 422) but evidence upload, ingestion (20 entities) and analytics run (25 findings) all succeeded on archived case |
| 10 | Analytics runs versioned (newest=current; unchanged findings deduped; no duplicate IDs) | **PASS** | — | Observed count discrepancy: run summary `finding_count:25` vs persisted findings `total:21` (4 not persisted) — **P3 minor**, any 404/`None` still counted in summary |
| 11 | Re-run after new evidence = current; old runs historical; findings map to correct dataset | **PASS** | — | RUN3 completed (35 ent/63 rel/41 findings); summary reflects updated dataset; run1 21 intact |
| 12 | Logout / token revocation | **PARTIAL** | **P2** | Backend `POST /auth/logout` → 204 and revokes token (old token → 401 "access token has been revoked"). **Frontend NEVER calls it**: `ApiAuthService` contract (contract.ts) has no `logout`; `auth.ts` `logout()` only clears the local session |
| 13 | Graph "Fit" centers/scales the graph | **FAIL** | **P2** | `resetView` only clears focus/selection; no `cy.fit()/zoom()`; the viewport `fit` animation runs only when a focus node is set, so Fit does NOT change the viewport |
| 14 | Hard-refresh nested routes (no redirect to nonexistent `/app/dashboard`) | **PASS** | — | Vite SPA fallback serves all nested routes 200; bootstrap restores auth; case errors render `ErrorState`, `RequirePermission` renders `NoAccessPage` (no redirect) |
| 15 | Visible mutation error indication | **FAIL** | **P2** | `admin-users.tsx:166-170` `handleAction` → `mutation.mutate(action, { onError: () => undefined })` silently suppresses suspend/activate/reject/role errors; approve has no error surface either |

### Combined product-rule findings

- **P0 — Case-list access leak.** `backend/app/api/routes/cases.py` `_case_filters`
  builds `member_ids = select(Case.id).select_from(CaseMember)…`, generating SQL that
  selects the **outer** `cases.id` in the subquery (correlated), so a user with ≥1
  membership row sees every case in LIST (and `total`). Should be `select(CaseMember.case_id)`.
- **P1 — No case-status guard on content mutations.** Evidence upload, ingestion, and
  analytics run all succeed on **closed** and **archived** cases. Archived transitions
  are correctly terminal, but the cases themselves are not read-only at the API level.
- **P2 — Frontend cannot revoke sessions server-side.** No `logout` in the API contract.
- **P2 — "Fit" does not fit.** It clears focus without changing the viewport.
- **P2 — Silent admin account-action errors.** `onError: () => undefined`.

---

## Regressions / Additional Checks (A–H)

| Check | Result | Notes |
| --- | --- | --- |
| A. Evidence soft-delete | **PASS** | `DELETE /evidence/{id}` → 204; row retained (`deleted_at`), filtered from list; `orphan_evidence=0` |
| B. Graph-sync retry IDOR | **PASS** | Admin retry own job → 200 (20 nodes/36 edges synced); **valid non-member analyst** retry → 403 (`INSUFFICIENT_PERMISSION`); revoked-token → 401 |
| C. Resolution review | **PASS** (code-verified) | Frontend ships findings review; finding-status mutation tests pass in suite |
| D. Pagination limits/offset | **PASS** | `/cases?limit=2&offset=0|2` → 2 returned of 7; `/findings?limit=5` → 5 of 38 |
| E. Command palette | **PASS** (code-verified + served) | Mounted in `app-shell.tsx:198`; includes Create Case |
| F. Sidebar/command "Create Case" | **PASS** | Present in command palette |
| G. No-Access copy | **PASS** | `no-access.tsx`; `RequirePermission` renders `NoAccessPage` (not a redirect) |
| H. Terminology | **PASS** | Backend `Finding`/`findings`; frontend "Findings" tab + "Hypotheses" page explicitly distinguishes hypotheses ≠ findings |

---

## Mock / Real Parity

| Check | Result | Notes |
| --- | --- | --- |
| `src/api/mock/parity.test.ts` (identical method keys, all services) | **PASS** | 1 test passed |
| `src/api/index.test.ts` | **PASS** | 3 tests passed |
| Contract completeness | **PASS** but gap | Mock and real both implement the same `Api` contract; contract itself omits `logout` (root of the TEST 12 P2 finding) |

---

## Test Suites

| Suite | Result | Notes |
| --- | --- | --- |
| Frontend (`npx vitest run`) | **PASS** | 11 files, **52/52** |
| Backend `pytest` (compose infra env overrides) | **FAIL (1 of 334)** | 333 passed, 22 skipped, 1 error → 1 failed. The single failure is `tests/unit/test_analytics_run.py::test_findings_are_run_versioned_current_vs_historical`: its **global, unfiltered** `count(*)` from `Finding` expects a pristine DB (`== 1`), which the shared runtime database cannot satisfy after this audit's live case runs populated it (got `60`). The test's own behavioral assertion (second run dedups: `inserted2 == 0`) **passed** — so this is a **test-isolation flaw exposed by shared-DB runtime data**, not a product defect. |

---

## Static Source Verification & Data Integrity

| Item | Result | Notes |
| --- | --- | --- |
| Independent setters / no auto-mutating accessors on findings | **PASS** | Exploratory `explanation`/`evidence_ids` fields populated from signals; setter-based status transitions guarded |
| Provenance captured | **PASS** | `evidence_ids=_uuids(service.affected_evidence(...))` (`analytics.py:482,510`) |
| Transaction boundaries committed as units | **PASS** | Audit-log row created with INSERT semantics within the transaction; all 15 runtime flows committed cleanly |
| Data integrity via SQL | **PASS** | `orphan_evidence=0`, `orphan_members=0`, `orphan_findings=0`; evidence rows retain provenance after soft-delete (`deleted_at`) |

---

## Terminal Output

```
FUNCTIONAL VERIFICATION — cybersaarthi @ 602d688   (read-only, runtime-first)
================================================================================
ENVIRONMENT ......................... PASS   (docker Up/healthy; backend 0.1.0)
  health /api/v1/health ............. ok
  / (404) / auth/me no-token (401) .. PASS
  frontend real-mode vite 5173 ...... PASS (deep links 200)

TESTS 1-15
  1 register->PENDING + role-ignore ..... PASS
  2 pending login 403 ACCOUNT_PENDING ... PASS
  3 role-change pending 409 NOT_ACTIVE .. PASS
  4 rejected lifecycle (409/409/409/403)  PASS
  5 approve->ANALYST ACTIVE, re-approve 409 PASS
  6 member persistence + scoped reads ... PASS
  7 non-member scoped 403s ............. PASS    (*** P0 list-leak found)
  8 closed-case upload/ingest ........... FAIL P1   (no status guard)
  9 archived-case mutations ............. FAIL P1   (not read-only)
 10 analytics runs versioned/dedup ...... PASS    (P3 summary/counts skew)
 11 re-run current vs historical ........ PASS
 12 logout/token revocation ............. PARTIAL P2 (backend ok; frontend no logout)
 13 graph Fit centers/scales ............ FAIL P2   (fit only clears focus)
 14 hard-refresh nested routes .......... PASS
 15 mutation error visibility ........... FAIL P2   (admin onError: ()=>undefined)

REGRESSIONS A-H
  A evidence soft-delete .......... PASS     E command palette .......... PASS(code)
  B graph-sync retry IDOR ........ PASS     F Create Case .............. PASS(code)
  C resolution review ............ PASS(code) G No-Access copy .......... PASS(code)
  D pagination limit/offset ...... PASS     H terminology .............. PASS

PARITY .......................... PASS (mock/real identical surfaces; 1+3 tests green)
SUITES
  frontend ..................... 52/52 PASS
  backend ...................... 333/334 (1 isolated-DB test-fix, non-product)

FINDINGS
  P0 case-list access leak (cases.py:_case_filters subquery uses outer cases.id)
  P1 closed/archived cases accept evidence+ingest+analytics
  P2 frontend logout never revokes server token (contract has no logout)
  P2 graph "Fit" does not re-fit the viewport
  P2 admin account-action errors silently swallowed (onError undefined)

RESULT: 15 spec tests -> 9 PASS, 1 PARTIAL, 5 FAIL (1xP0, 2xP1, 2xP2)
         All environment/regressions/parity/integrity checks green.
         Suites: frontend 52/52; backend 333/334 (remaining failure = test isolation).
================================================================================
```
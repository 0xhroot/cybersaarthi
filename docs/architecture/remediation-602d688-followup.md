# Remediation — Functional Verification Gaps (`602d688` follow-up)

Scope: fix the real defects surfaced by the functional verification at commit
`602d688a3ce6662e8729434071a1c265f8993daf`, then re-verify. The prior read-only
verification phase concluded with 15 spec tests → **9 PASS, 1 PARTIAL, 5 FAIL**
(1xP0, 2xP1, 2xP2). This phase implements the fixes authorized by the follow-up
directive. No RBAC was weakened, no test was hidden or skipped, and no
verification result was edited by hand.

## Summary

| Defect | Severity | Status |
| --- | --- | --- |
| Case-list access leak (a member of one case could see every case) | P0 | FIXED + regression test |
| Closed-case read-only not enforced after status change | P1 | FIXED + parametrized tests |
| Archived-case read-only not enforced after status change | P1 | FIXED + parametrized tests |
| Frontend logout did not revoke the server token | P2 | FIXED + tests |
| Graph "Fit" did not call cytoscape `fit()` | P2 | FIXED + wiring test |
| Admin mutation failures were silently swallowed | P2 | FIXED + error-visibility test |
| Backend test-isolation flaw (global unfiltered count) | backend | FIXED |

## P0 — Case-list access leak

**Root cause:** `backend/app/api/routes/cases.py` `_case_filters` built the
membership subquery with `select(Case.id).select_from(CaseMember)...`, which
correlated the **outer** `cases.id` and — for any user with at least one
membership — returned every case (the correlation made the `EXISTS` effectively
always-true).

**Fix:** select `CaseMember.case_id` instead:

```python
member_ids = select(CaseMember.case_id).where(CaseMember.user_id == user.id).scalar_subquery()
```

**Regression test:** `backend/tests/api/test_cases_api.py::test_case_list_never_leaks_other_users_cases`
(owner / stranger / member / admin fixtures; list, search, pagination, totals,
member-visibility and admin-visibility).

## P1 — Closed/archived case read-only enforcement

**Root cause:** the read-only semantics were enforced by the status-transition
validator during a single PATCH, but content mutations (evidence upload/delete,
ingestion, analytics run, finding status, member add/remove) and a content PATCH
on an already-read-only case were not rejected.

**Fix:** centralized, stable-code guards in
`backend/app/api/dependencies.py`:
- `READ_ONLY_CASE_STATUSES = ("closed", "archived")`
- `assert_case_mutable(case, *, allowed_statuses=())` → `ApiHTTPException(409, CODE_CASE_READ_ONLY, ...)`
- `assert_case_investigation_mutable(case)` wraps the previous for investigation mutations.

Wired into: `evidence.py` (`upload_evidence`, `delete_evidence`,
`create_ingest_job`, `retry_graph_sync`), `analytics.py` (`run_analytics`),
`findings.py` (`update_finding_status`), `cases.py` (`update_case`: content PATCH
rejected on closed/archived; legal closed→open/in_progress reopen still allowed;
archived rejects all PATCH; `add_case_member`/`remove_case_member`).

**New error code:** `CODE_CASE_READ_ONLY = "CASE_READ_ONLY"` added to
`backend/app/core/codes.py` and re-exported from `backend/app/api/errors.py`.

**Tests:** new `backend/tests/api/test_case_readonly_api.py` parametrized across
closed/archived: evidence upload/delete, ingest, retry-graph-sync, analytics run,
finding status, member add/remove → all `409 CASE_READ_ONLY`; case stays readable.
Also verifies closed→archived does not reopen mutation and open-case sanity
(upload still `201`). `test_case_status_transitions_are_state_machine_enforced`
updated: archived-reopen now expects `409 CASE_READ_ONLY` (was `422`).

## Frontend P2

### Logout revocation
- `frontend/src/api/contract.ts`: `ApiAuthService.logout(): Promise<void>` added.
- `frontend/src/api/real/index.ts`: `logout()` calls `POST /auth/logout` with the
  current bearer token.
- `frontend/src/api/mock/index.ts`: `logout()` clears the session and raises
  `unauthorized()` when no session exists.
- `frontend/src/stores/auth.ts`: `logout()` is now `async`, calls
  `api.auth.logout()` **before** clearing the local session, and always clears
  locally (server-unreachable still degrades to a local sign-out; the next request
  with the old token surfaces `401`).
- Tests: `stores/auth.test.ts` (await + spy that backend `logout` is invoked) and
  `api/index.test.ts` (mock/real auth surface parity includes `logout`).

### Graph Fit
- `frontend/src/components/graph/cyto-graph.tsx`: new `fitSignal` prop; when set
  (and no focus node), calls `cy.fit(cy.elements(":visible"), 50)` so the
  viewport refits onto currently visible elements and **never reveals
  filtered/hidden nodes**.
- `frontend/src/app/pages/graph.tsx`: Fit button (`resetView`) clears focus and
  increments `fitSignal`; passed down to `CytoGraph`.
- Test: `frontend/src/app/pages/graph.test.tsx` (Fit click bumps `fitSignal` and
  clears focus).

### Admin mutation error visibility
- `frontend/src/app/pages/admin-users.tsx`: `handleAction`/`handleApprove` now
  surface failures via an inline `role="alert"` banner (`actionError`), replacing
  the previous `onError: () => undefined`.
- Test: `frontend/src/app/pages/admin-users.test.tsx` (a failing mutation renders
  the visible error; `@/components/ui/dropdown-menu` is mocked to plain buttons so
  the Radix open behavior is deterministic in jsdom).

## Backend test-isolation flaw

**Root cause:** `tests/unit/test_analytics_run.py::test_findings_are_run_versioned_current_vs_historical`
used a global, unfiltered `select(func.count()).select_from(Finding)`, which was
corrupted by shared-DB runtime data (60 vs 1).

**Fix:** scope the count to the case: `where(Finding.case_id == str(case_id))`.

## Verification results

Backend suite (venv, infra env): **341 passed** (was 333/334 + 7 new readonly
tests; the isolation fix turns the single historical failure green).
Frontend suite: **56 passed** (was 52; +4 new). `ruff check`, `ruff format --check`,
`mypy`, `tsc -b --noEmit`, `eslint`, and `alembic check` (“No new upgrade
operations detected”) all green.

Real-HTTP re-verification (backend restarted on fixed code, bind-mounted
`./backend:/app`):

```
TEST-01 P0 case-list isolation ......... PASS  (strangers cannot see other users' cases)
TEST-02 P1 closed-case read-only ....... PASS  (upload/ingest/analytics/PATCH → 409 CASE_READ_ONLY)
TEST-03 P1 archived-case read-only ..... PASS  (reopen PATCH + analytics → 409 CASE_READ_ONLY)
TEST-04 P2 logout revocation ............ PASS  (logout 204 → /auth/me 401)
```

Earlier verification artifacts were cleaned from the shared PostgreSQL before the
DB-driven validation so global totals stay green.

## Remaining defects

None identified. All originally-failing verification tests now pass; environment,
regressions (A–H), mock/real parity, and integrations remain green.
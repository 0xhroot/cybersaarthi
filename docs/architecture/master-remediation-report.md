# Master Product Remediation — Final Report

Scope: the full-stack remediation of **CyberSaarthi** (account lifecycle, case
access, case lifecycle, evidence, ingestion, graph sync, analytics, findings)
to a coherent, production-quality investigation platform.

Date: 2026-09-02 · Branch: `main` · Base: `4fbdb3a` (phase 5)

---

## 1. Principal fixes

State machines now drive every product lifecycle on the backend, and the frontend
mirrors the backend behaviour through a single contract with mock/real parity.

| Area | What changed |
| --- | --- |
| **Account lifecycle** | `app/services/users.py` `_VALID_TRANSITIONS` + `AccountTransitionError`; `app/core/codes.py` becomes the single source of truth for error codes; circular-import fixed. State transitions are validated, not free-for-alls. |
| **Case access** | `case_members` model + migration `c1a2b3c4d5e6`, member-aware `get_case_or_404` and case-list filters, three member endpoints (list/add/remove) gated to owner/admin, IDOR regression tests. |
| **Case lifecycle** | `_CASE_TRANSITIONS` state machine in `cases.py`; PATCH validates transitions (422), archive is terminal (409). |
| **Evidence** | Soft-delete via `evidence_files.deleted_at` + migration `d2e3f4a5b6c7`; provenance retained; `list_evidence` filters deleted; `create_ingest_job` reports `duplicate`; `retry_graph_sync` gains an IDOR guard. |
| **Ingestion** | Job state machine in `app/repositories/evidence_repository.py` (`_JOB_START_FROM`, `_JOB_FINISH_FROM`, `JobTransitionError`, `mark_job_partial`); `ingest()` short-circuits terminal jobs so a re-run cannot bounce a job back to `running`; failures mark `partial` when partial progress exists, else `failed`. |
| **Graph sync** | `graphs_synced` now reflects the **current** projectable state by reading the latest job (`latest_job_graph_status`), instead of `any(job.graph_sync_status == 'synced')`. |
| **Analytics** | Run state machine in `analytics_repository.py` (`_RUN_RUNNING_FROM`, `_RUN_TERMINAL_FROM`, `RunTransitionError`, `create_run`/`start_run`); circular import between `app/analytics/__init__.py` and `findings.py` eliminated. |
| **Findings** | **Fixed a latent bug** in `save_findings`: the existing-findings lookup selected 3 columns but unpacked 2, raising `ValueError` on every re-run. The A09 test masked it (a failed second run added no findings so the total stayed flat). Now selects exactly the two columns used; a second unchanged run correctly deduplicates and completes. |

## 2. Regression coverage added

- `backend/tests/unit/test_ingestion_job.py` — 7 tests: start/complete/fail/partial,
  terminal-job-cannot-return-to-running, terminal-job-cannot-be-completed-again,
  latest-job graph status.
- `backend/tests/unit/test_analytics_run.py` — 5 tests: pending→running→completed,
  can-fail, terminal-cannot-transition, pending-cannot-jump-to-terminal, and
  findings run-versioning (CURRENT dedup vs HISTORICAL snapshots).
- `backend/tests/api/test_phase2_api.py` — evidence soft-delete retains row,
  ingest reports duplicate, retry-graph-sync IDOR guard.
- `backend/tests/api/test_analytics_api.py::test_findings_do_not_duplicate_across_unchanged_runs`
  strengthened to assert the **second run completes** (guards the unpack bug).

Frontend parity and regression tests:

- `frontend/src/lib/permissions.ts` gained `evidence.delete` (admin + investigator),
  mirroring `app/core/rbac.py`; `permissions.test.ts` locks it.
- `frontend/src/api/mock/index.ts` mock `ROLE_PERMISSIONS` gained `evidence.delete`,
  member-aware `assertCaseAccess` and case-list filter that include case members.
- `frontend/src/api/mock/mock-adapter.test.ts` — case membership grant/revoke and
  `evidence.delete` enforcement, `retryGraphSync` permission + IDOR, `reviewResolution`.
- `frontend/src/api/mock/parity.test.ts` — asserts every service exposes the same
  method surface on mock and real adapters.

## 3. Frontend wiring completed

- **Evidence delete**: contract, real adapter, mock adapter, `useDeleteEvidence`,
  delete action + confirmation dialog in the evidence page (gated by `evidence.delete`).
- **Case membership**: `ApiCaseService.listMembers/addMember/removeMember` (contract,
  real, mock, hooks), and a "Case access" management card in the case overview
  (add user by id + role, remove member), gated by `case.update`.
- **Graph-sync retry**: `ApiEvidenceService.retryGraphSync` (contract, real, mock,
  hook) surfaced in the evidence page when any job's graph sync failed.
- **Resolution review**: `ApiEntityService.reviewResolution` (contract, real, mock,
  hook) surfaced as a card in the entities page.

## 4. Latent type-correctness gap fixed

The frontend root `tsc --noEmit` silently skipped its project references
(`tsconfig.json` has `files: []` with `references`), so real type errors were not
caught. The proper gate `tsc -b --noEmit` surfaced that `CaseList` was referenced in
`contract.ts` but never defined, and the mock/real case-list adapters returned an
incomplete shape. `CaseList` was added and both adapters now return `items/total/limit/offset`.

## 5. Validation results

Backend (via the authoritative Docker path — host `pytest` cannot reach the service
hostnames, an environment constraint rather than a defect):

- `alembic check` — "No new upgrade operations detected."
- `ruff check .` · `ruff format --check .` — clean.
- `mypy app` — Success: no issues found in **100 source files**.
- `pytest tests` — **334 passed**.
- `docker compose build` — backend + frontend images build.
- Stack healthy (`postgres`, `neo4j`, `redis`, `minio`, `backend`).

Frontend:

- `tsc -b --noEmit` — clean.
- `eslint src` — clean.
- `vitest run` — **52 passed**.
- `npm run build` — production build succeeds.

Real HTTP smoke test:

- `GET /api/v1/health` → `{"status":"ok",...}`.
- `POST /api/v1/auth/login` (admin) → returns a bearer token.
- `GET /api/v1/auth/me` → admin profile incl. `evidence.delete` permission.
- `GET /api/v1/cases` with the token → `200`.

## 6. Commit

A single commit, `fix: complete product workflow and integrity remediation`,
captures all of the above. No push is performed.
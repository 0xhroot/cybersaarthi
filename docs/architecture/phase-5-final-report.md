# CyberSaarthi Phase 5 — Multi-User Account Lifecycle — Final Report

## Scope

Evolve Phase 4's single-admin, admin-only-registration authentication into a real
multi-user, cloud-ready application: public self-service registration, an
administrator-driven approval workflow, server-enforced RBAC with a dedicated
user-management API, full account lifecycle (pending/active/suspended/rejected),
case-level data isolation preserved, and a real-API frontend consuming the
management endpoints. No AI in this phase.

Everything below is verified against a **clean-room rebuild**: fresh volumes,
fresh image build, bootstrap admin via the CLI, public registration, admin
approval, and the full test suite.

## What was built

| Layer | Component | Files |
|---|---|---|
| Identity | `AccountStatus` (PENDING/ACTIVE/SUSPENDED/REJECTED) replaces `is_active` as source-of-truth; derived `is_active`/`is_pending` model properties | `app/core/enums.py`, `app/models/user.py` |
| Config | `TOKEN_REVOCATION_ENABLED` (default True) and `LOGIN_THROTTLE_FAIL_CLOSED` (default True) fail in a safe direction; `STORAGE_*` env aliases via `AliasChoices` | `app/core/config.py` |
| Registration | Public self-service; `role` removed from `RegisterRequest` (never trusted); accounts created PENDING with no session | `app/schemas/auth.py`, `app/api/routes/auth.py` |
| AuthN/AuthZ | Stable error codes (`INVALID_CREDENTIALS`, `ACCOUNT_PENDING`, `ACCOUNT_SUSPENDED`, `ACCOUNT_REJECTED`, `INSUFFICIENT_PERMISSION`, `CASE_ACCESS_DENIED`, `DUPLICATE_USERNAME`, `DUPLICATE_EMAIL`); `ApiHTTPException` handler registered before the generic handler | `app/api/errors.py`, `app/main.py` |
| Admin API | `/admin/users` router: list, list pending, get, approve, reject, suspend, activate, change role — all requiring `PERM_USERS_MANAGE` | `app/api/routes/users.py` (new), `app/api/router.py` |
| Guards | Cannot change/suspend/reject self; cannot demote/suspend/reject the last active ADMIN | `app/api/routes/users.py` |
| Repo | `update_status` flushes + refreshes after commit-time `onupdate` (fixes `MissingGreenlet`) | `app/repositories/user_repository.py` |
| Bootstrap | Idempotent first-ADMIN CLI (`scripts.create_admin`), wired as `make admin` | `backend/scripts/create_admin.py`, `Makefile` |
| Migration | Adds `users.status`, indexes it, backfills from `is_active`, drops `is_active` | `alembic/versions/b7d4f2c9a1e0_*.py` |
| Frontend (contract) | `AccountStatus`, `status` on user types, `AdminUserList`/`ApproveRequest`/`RoleChangeRequest`, real-adapter admin users service | `frontend/src/types/domain.ts`, `frontend/src/api/contract.ts`, `frontend/src/api/real/index.ts` |
| Frontend (auth) | `register` action; stored `status`; PENDING/suspended surfaced via stable codes | `frontend/src/stores/auth.ts`, `frontend/src/api/client/session.ts` |
| Frontend (pages) | Public `register`, `pending` approval screen, admin `admin-users` (approve/reject/suspend/activate/assign role); `RequirePermission users.manage` guard; login "Request access" link | `frontend/src/app/pages/*`, `frontend/src/app/router.tsx`, `frontend/src/app/layouts/app-shell.tsx` |
| Tests | Admin API suite, bootstrap-admin integration, mock-adapter parity for registration + admin lifecycle, auth-store register, route guards | `backend/tests/api/test_admin_users_api.py`, `backend/tests/integration/test_bootstrap_admin.py`, `frontend/src/api/mock/*.test.ts`, `frontend/src/stores/auth.test.ts`, `frontend/src/app/router.test.tsx` |

## Migration

`alembic/versions/b7d4f2c9a1e0_phase_5_user_account_lifecycle_status.py`.
Adds `users.status` (String(16), server_default `ACTIVE`) with index
`ix_users_status`, backfills from `is_active`, applies a CHECK constraint, and
drops `is_active`. `alembic check` reports no drift and the clean-room boot
applied it before the API accepted traffic.

## Admin user-management API

| Method & path | Auth | Effect |
|---|---|---|
| `GET /admin/users` | `users.manage` | list (status/search filters, pagination) |
| `GET /admin/users/pending` | `users.manage` | PENDING only |
| `GET /admin/users/{id}` | `users.manage` | detail |
| `POST /admin/users/{id}/approve` | `users.manage` | approve + assign `role` |
| `POST /admin/users/{id}/reject` | `users.manage` | mark REJECTED |
| `POST /admin/users/{id}/suspend` | `users.manage` | mark SUSPENDED |
| `POST /admin/users/{id}/activate` | `users.manage` | mark ACTIVE |
| `PATCH /admin/users/{id}/role` | `users.manage` | change role |

Self-actions and demoting the sole active ADMIN are refused with `422`.

## Test results (clean room)

| Suite | Count | Key coverage |
|---|---|---|
| Backend | 310 | auth restructures, admin API, bootstrap-admin idempotency, lifecycle, throttle fail-closed |
| Frontend | 45 | mock parity for registration + admin lifecycle, auth-store register, route guards |

## Quality gates

- `ruff check .` → **pass**; `ruff format --check .` → **154 files** clean.
- `mypy app` → **98 files**, no issues.
- `alembic check` → **no drift**.
- Backend suite → **310 passed**; frontend `vitest` → **45 passed**; frontend
  `tsc -b --noEmit`, `eslint .`, and `npm run build` all clean.

## Live verification (clean room)

- Bootstrap admin via `scripts.create_admin` → idempotent, refuses a second admin.
- Public registration → `201` with `status: PENDING`, `roles: []`, no session.
- PENDING sign-in → `403 ACCOUNT_PENDING`; admin approval → ACTIVE sign-in works.
- Suspend → sign-in `403 ACCOUNT_SUSPENDED`; activate → sign-in restored.
- Role change → reflected immediately in `/auth/me`.
- Non-admin calling `/admin/users/*` → `403 INSUFFICIENT_PERMISSION`.

---

Phase 5 Status: COMPLETE
- Commit: single conventional commit across backend + frontend + docs.
- Tests: 310 backend + 45 frontend green; clean-room rebuild + live smoke verified.
- Quality: ruff/mypy/alembic clean; frontend typecheck/lint/build clean; stable error codes.
- Security: status-based account lifecycle fails closed; public registration cannot self-provision roles; admin endpoints gated by `users.manage`; self/last-admin guards; case isolation preserved; token revocation + throttle fail-closed by default.
- Remaining (deferred by design): OIDC/MFA/password-reset; case-sharing ACLs; audit retention/export tooling; email verification/notifications for approvals.
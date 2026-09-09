# CyberSaarthi Phase 4 — Productization & Security — Final Report

## Scope

Productize the Phase 1–3 forensic-analysis platform: real bearer-token
authentication (no fake AI, no fake evidence/confidence), RBAC, IDOR-proof
case access, audit trail, findings lifecycle with human-in-the-loop control,
evidence provenance, login throttling, request observability, a contract for
the (later) frontend, full test coverage of the security model, and
cross-platform checks for the Docker image.

Everything below was verified against a **clean-room rebuild**: fresh volumes,
fresh image build, migrations applied by the container entrypoint on boot,
seeded roles and demo case, full test suite, then live HTTP smoke tests.

## What was built

| Layer | Component | Files |
|---|---|---|
| AuthN | HMAC-SHA256 signed bearer tokens (stdlib only, no PyJWT) | `app/core/auth.py`, `tests/unit/test_auth_tokens.py` |
| AuthZ | Role→permission model, dependency guards | `app/core/rbac.py`, `app/api/dependencies.py`, `tests/unit/test_rbac.py` |
| Identity | Admin-only user registration, seeded roles | `app/api/routes/auth.py`, `scripts/seed_users.py`, `migration 0038dd7406e6→cc19f4d2b003` |
| Cases | Owner-or-admin access, CRUD + archive | `app/api/routes/cases.py`, `tests/api/test_cases_api.py`, `test_access_control.py` |
| Findings | Human-confirmed lifecycle (NEW→REVIEWED→CONFIRMED / DISMISSED), idempotent no-ops, per-target permissions, admin override | `app/services/findings_service.py`, `app/api/routes/findings.py`, `tests/api/test_findings_api.py`, `tests/unit/test_findings_service.py` |
| Audit | Append-only attributed event log, login existence-hiding | `app/services/audit.py`, `app/repositories/audit_repository.py`, `app/api/routes/audit.py`, `tests/api/test_audit_api.py` |
| Provenance | Evidence→records→entities/findings chain; finding count via record ids | `app/services/provenance.py`, `tests/api/test_provenance_api.py` |
| Abuse | Login throttling, fail-open on Redis outage | `app/services/throttle.py`, `tests/unit/test_throttle.py` |
| Obs. | Correlation ids, security headers, actor-attributed request logs | `app/middleware.py`, `app/main.py`, `tests/api/test_observability.py` |
| E2E | Full investigator workflow through the HTTP layer | `tests/e2e/test_investigator_workflow.py`, `tests/e2e/conftest.py`, `tests/e2e/__init__.py` |

## Migration

`alembic/versions/cc19f4d2b003_phase_4_productization_auth_rbac.py` (head).
Defines `users` (with `bcrypt_hash`, `roles` via native enum), `audit_logs`,
`roles_active_enum`, nullable `owner_id` on cases; seeds roles. `alembic check`
reports "No new upgrade operations detected" and clean-room boot applied it
before the API accepted traffic.

## Roles

| Role | Can see cases you own + read evidence | Create/archive case | Upload evidence | Run analytics | Review findings | Confirm/dismiss findings | Read audit | Manage users |
|---|---|---|---|---|---|---|---|---|
| ADMIN | yes (all) | yes | yes | yes | yes | yes | yes | yes |
| INVESTIGATOR | yes | yes | yes | yes | yes | yes | no | no |
| ANALYST | yes | no | no | yes (summary) | yes | no | no | no |
| VIEWER | yes | no | no | no | no | no | no | no |

## Test results (clean room)

| Suite | Count | Key coverage |
|---|---|---|
| Unit | 165 | token signing/expiry/tamper, RBAC mapping, findings lifecycle + session-consistency, throttle fail-open/disabled/redis |
| API | 67 | auth flows, case CRUD + 401/403/404 matrix, IDOR matrix across 14 routes, findings lifecycle + permissions, audit filters + existence-hiding, provenance counts, correlation ids |
| E2E | 1 | admin→register analyst→investigator case→CSV→ingest→analytics→findings review/confirm→audit→cleanup |
| Integration | 12 | Phase 1–2 pipelines regressions |
| **Total** | **245** | `245 passed in 35.6s` |

## Quality gates

- `ruff check app tests scripts` → **All checks passed!**
- `ruff format --check app tests scripts` → **141 files already formatted**
- `mypy app` → **Success: no issues found in 96 source files**
- `alembic check` → **No new upgrade operations detected**
- Pydantic `Settings` production validator refuses placeholder secrets.

## Live verification (clean room, running containers)

- `/api/v1/health` → 200 with `x-request-id` security headers.
- Seeded admin + investigator login; `/auth/me` returns roles.
- Investigator created a case (owner attributed); audit shows `case.created`.
- Anonymous on existing case → **401**; missing case → **404**; bad token →
  **401**.
- Freshly registered ANALYST on a colleague's case → **403** for `GET`,
  evidence upload, archive, and another `/auth/register` attempt.
- Six wrong logins → `401 401 401 401 401 429` (throttle), Redis key cleared.

## Cross-platform Docker

`pip download --only-binary` verification for every pinned package at the
frozen versions resolved **all 84 packages** to aarch64 linux wheels
(`manylinux_2_17`/`2014` or `manylinux_2_28`); no package requires an sdist
build on arm64. Base images in `compose.yml` are all multi-arch
(`python:3.12-slim`, `postgres:16-alpine`, `neo4j:5-community`, `redis:7-alpine`,
`minio`), and a namespace `image: cybersaarthi-backend` is set so a `--platform
linux/arm64` build works on Apple Silicon/ARM CI.

---

Phase 4 Status: COMPLETE
- Commit: `feat: complete phase 4 productization and security`
- Tests: 245 passed (165 unit + 67 api + 1 e2e + 12 integration), live smoke + IDOR matrix verified against a clean-room rebuild
- Quality: ruff clean, format clean (141 files), mypy app clean (96 files), alembic check clean (head `cc19f4d2b003`)
- Security: HMAC tokens + expiry, RBAC for every route, owner-or-admin + 401/403/404 matrix, throttle fail-open + 429 verified, existence-hiding audit, security headers, correlation ids (checklist: `docs/architecture/phase-4-security-checklist.md`)
- End-to-End: seeded roles + demo case on fresh volumes; investigator workflow (login→case→CSV→ingest→analytics→findings confirm→audit) passes through the real HTTP stack
- Remaining: deferred by design — frontend UI consumes `backend/docs/frontend-contract.md`; OIDC/MFA/password-reset; case sharing ACLs; audit retention/export tooling
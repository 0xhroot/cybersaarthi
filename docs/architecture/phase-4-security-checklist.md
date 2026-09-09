# Phase 4 security checklist

Evidence-backed verification of the Phase 4 productization controls. Each
item names the mechanism and the test (or live check) that proves it.

## Authentication

- [x] **Bearer tokens are signed, not forged** — `app/core/auth.py` wraps
  `base64url(json{uid,iat,exp,jti}).hex(hmac_sha256)` and verifies with
  `hmac.compare_digest`. Test: `tests/unit/test_auth_tokens.py`
  (`test_tampered_payload_changes_signature_verification`, wrong-secret
  rejection, malformed token no-raise).
- [x] **Tokens expire** — `ACCESS_TOKEN_EXPIRE_MINUTES` (30) enforced in
  `decode_access_token`; accepted through `exp`, rejected after. Test
  `test_token_is_accepted_through_expiry_but_not_after_it`.
- [x] **Verification never raises** — malformed payloads/signatures → `None`
  → 401. Test `test_malformed_tokens_never_raise`.
- [x] **Nonces prevent replay of identical tokens** — `jti` per signing; 20
  signings of the same user yield 20 distinct tokens.
- [x] **No plaintext passwords and no secrets in tokens** — payload carries
  only `{uid,iat,exp,jti}`; the payload test asserts no credential keys.
  Passwords only ever hit `verify_password(password, hash)`.
- [x] **Placeholder secrets refused in production** — config validator rejects
  the default `SECRET_KEY` outside non-production environments.

## Authorization (RBAC)

- [x] **Role→permission map is pure and unit-tested** —
  `tests/unit/test_rbac.py` (admin=all, investigator=all-but-users.manage,
  analyst read+analytics+review, viewer strictly read-only).
- [x] **Every state-changing route gates on its permission** — 403 when the
  role lacks it. API tests: viewer/analyst denials in
  `tests/api/test_access_control.py` and `test_findings_api.py`
  (analyst may REVIEW but not CONFIRM/DISMISS).
- [x] **`/auth/register` is ADMIN-only** — 401 anonymous, 403 non-admin
  (`test_auth_api.py::test_register_requires_admin`).

## Case access / IDOR

- [x] **Owner-or-admin** — `get_case_or_404` returns 404 (missing), 401
  (unauthenticated on an existing case), 403 (non-owner). Verified live on
  the clean room: stranger analyst → 403 on `GET`, upload, and archive of a
  colleague's case; anonymous → 401; missing → 404.
- [x] **Matrix coverage on every case-scoped route** — 14+ routes parametrized
  for the 403 (stranger) and 401 (anonymous) matrices in
  `tests/api/test_access_control.py`.
- [x] **Listings are owner-filtered** — `test_listing_is_filtered_to_owned_cases`.
- [x] **Legacy null-owner cases** — readable only by ADMIN (owner comparison
  is skipped for admins; non-admin non-owner always 403).

## Findings lifecycle

- [x] **Engine only emits NEW** — `test_engine_findings_start_as_new_and_are_readable`.
- [x] **Per-target permissions enforced** — review/dismiss/confirm need their
  distinct permission; verified by role (`test_status_permission_gates_review_by_role`).
- [x] **Closed findings immutable for non-admins** — 422 on rollback
  (`test_closed_findings_are_immutable_for_non_admins`); ADMIN override works
  (`test_admin_can_override_a_closed_finding`).
- [x] **Idempotent no-ops produce no audit rows and preserve the reviewer**
  (`test_owner_drives_review_then_confirm_with_audit`).

## Evidence & provenance

- [x] **Upload deduplicated by sha256** — 409 on duplicates, size cap, format
  detection (Phase 2, retained).
- [x] **Provenance is derived from real rows** — file → records →
  relationships → entities, findings joined through the file's records.
  Fixed: findings now resolve by source-record ids (`?|`), so `finding_count`
  is non-zero after a run (`test_evidence_provenance_counts_after_ingest_and_run`).

## Audit trail

- [x] **Append-only** — `AuditLog` has no update/delete API surface.
- [x] **Attributed** — `case.created/updated/archived`, `evidence.uploaded`,
  `ingestion.job_ran`, `analytics.run_completed`, `finding.status_changed`,
  `auth.*` events carry actor/resource/case ids and metadata.
- [x] **Login failure existence-hiding** — unknown usernames record nothing
  (`test_audit_records_login_success_and_failure`).
- [x] **Readability gated** — `audit.read` only; viewer/analyst → 403
  (`test_non_admin_roles_cannot_read_the_audit_log`).

## Abuse protection

- [x] **Login throttling** — Redis counter, `LOGIN_MAX_ATTEMPTS=5`,
  `LOGIN_LOCKOUT_SECONDS=300`; live-verified: five 401s then a `429`.
- [x] **Fail-open on Redis outage** and **disabled-mode never 429**
  (`tests/unit/test_throttle.py`).
- [x] **Admin actions are logged** — user creation, case lifecycle, analytics
  runs (audit tests + `analytics.run_completed`).

## Transport & observability

- [x] **Security headers** — `nosniff`, `DENY`, no-referrer, XSS protection on
  every response (`SecurityHeadersMiddleware`).
- [x] **Correlation ids** — `X-Request-Id`/`X-Correlation-Id` honoured, echoed,
  and propagated to logs; actor id attached to request logs
  (`RequestObservabilityMiddleware`, `tests/api/test_observability.py`).
- [x] **Unhandled errors log then return a sanitized 500** (global handler).

## Dependency & crypto hygiene

- [x] **No PyJWT** — stdlib `hmac`/`hashlib`/`base64` only.
- [x] **Bcrypt password hashing** (Phase 1, retained), never plaintext.
- [x] **No secrets committed** — `.env.example` carries placeholders; the
  production validator refuses them.

## Open items (intentionally deferred, noted in phase-4.md)

- OIDC / refresh-token rotation, MFA, password change/reset flows.
- Case sharing/assignment and non-owner ACLs (owner-or-admin is the model).
- Audit log retention/export tooling.
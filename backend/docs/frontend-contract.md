# Frontend API contract (Phase 4)

The base path for every route is `/api/v1`. All endpoints return JSON.
Authentication uses `Authorization: Bearer <token>`; tokens are short-lived
(`expires_in` seconds). On `401` the client should re-authenticate. Errors use
the platform envelope:

```json
{ "status": 403, "code": "FORBIDDEN", "detail": "..." }
```

## Authentication

| Method & path | Auth | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `POST /auth/login` | public | `{username, password}` (username may be an email) | `200` `TokenResponse` | `401` bad creds; `429` throttled; `403` inactive account |
| `POST /auth/register` | `users.manage` (ADMIN) | `{username, email, password, role?}` | `201` `RegisteredUserOut` | `401` unauth; `403` non-admin; `409` duplicate; `422` validation |
| `GET /auth/me` | bearer | — | `200` `{user, roles, permissions}` | `401` |

`TokenResponse`: `{access_token, token_type: "bearer", expires_in, user}`.
`user`: `{id, username, email, is_active, created_at}`.

Roles returned by `/auth/me`: `ADMIN` / `INVESTIGATOR` / `ANALYST` / `VIEWER`.

## Cases

| Method & path | Auth | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `GET /cases` | `case.read` | — | `200` `{items, total, limit, offset}` (own cases only) | `401` |
| `POST /cases` | `case.create` | `{title, description?}` | `201` `CaseOut` | `401`/`403`/`422` |
| `GET /cases/{id}` | access | — | `200` `CaseOut` | `401`/`403`/`404` |
| `PATCH /cases/{id}` | `case.update` + access | `{title?, description?, status?}` | `200` | `401`/`403`/`404`/`422` |
| `POST /cases/{id}/archive` | `case.archive` + access | — | `200` | `401`/`403`/`404` |

`CaseOut`: `{id, case_number, title, description, status, owner_id, created_at, updated_at}`.
`status`: `open` / `in_progress` / `archived`. **Client must not send
`archived` via PATCH** (use the archive endpoint) — the API rejects it with
`422`.

Access semantics: 404 for a missing case; 403 for a case you do not own (unless
`ADMIN`); 401 with no/invalid credentials.

## Findings

| Method & path | Auth | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `GET /cases/{id}/findings` | access | `?run_id=&limit=&offset=` | `200` `{items, total, limit, offset}` |
| `GET /cases/{id}/findings/stats` | access | `?run_id=` | `200` `by_type/by_severity/by_status` |
| `GET /cases/{id}/findings/{fid}` | access | — | `200` `FindingOut` (explainable) |
| `PATCH /cases/{id}/findings/{fid}/status` | per-target perm + access | `{status, reason?}` | `200` `FindingStatusOut` |

Per-target permissions for the status endpoint: `REVIEWED` → `findings.review`;
`DISMISSED` → `findings.dismiss`; `CONFIRMED` → `findings.confirm`. Errors:
`403` (missing permission), `422` (invalid status or illegal non-admin
transition), `404` (missing finding). Same-status calls are idempotent no-ops
(no audit row). Closed findings are immutable except for `ADMIN`.

## Evidence & ingestion

| Method & path | Auth | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `POST /cases/{id}/evidence` | `evidence.upload` + access | multipart `file`, `data_source?`, `metadata?` | `201` | `409` duplicate sha256; `413` too large; `400` undetectable format |
| `GET /cases/{id}/evidence` | access | `?limit=&offset=` | `200` `{items, total, limit, offset}` |
| `GET /cases/{id}/evidence/{eid}` | access | — | `200` `EvidenceDetailResponse` |
| `GET /cases/{id}/evidence/{eid}/provenance` | access | — | `200` `EvidenceProvenanceResponse` |
| `POST /cases/{id}/ingest` | `ingestion.run` + access | `{evidence_file_id, metadata?}` | `200` `{job, duplicate}` |
| `GET /cases/{id}/ingest-jobs` | access | — | `200` `{items, total}` |

`EvidenceProvenanceResponse`: `{evidence, record_count, records_by_status,
entity_count, relationship_count, finding_count, related_entity_ids,
related_relationship_ids, finding_ids}`.

## Analytics

| Method & path | Auth | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| `GET /cases/{id}/analytics/summary` | access | — | `200` live recompute |
| `GET /cases/{id}/analytics/centrality` | access | — | `200` |
| `GET /cases/{id}/analytics/communities` | access | — | `200` |
| `GET /cases/{id}/analytics/patterns` | access | — | `200` |
| `GET /cases/{id}/analytics/hypotheses` | access | — | `200` |
| `POST /cases/{id}/analytics/run` | `analytics.run` + access | — | `201` run snapshot |
| `GET /cases/{id}/analytics/runs` | access | — | `200` `{items, total}` |

## Entities & graph

`GET /cases/{id}/entities`, `GET /cases/{id}/entities/{eid}`,
`GET /cases/{id}/relationships`, `GET /cases/{id}/graph`,
`GET /cases/{id}/graph/stats`, `GET /cases/{id}/graph/entity/{eid}`,
`GET /cases/{id}/resolution/review` — all `case.read`-independent (any
authenticated access holder), `200` with paginated/entity payloads, `401/403/404`
matrix as above.

## Audit log

| Method & path | Auth | Query | Success |
| --- | --- | --- | --- |
| `GET /audit-logs` | `audit.read` | `case_id`, `actor_id`, `action`, `resource_type`, `limit` (≤200), `offset` | `200` `{items, total, limit, offset}` |

`items[].metadata_` carries event-specific fields (e.g. `finding.status_changed`
→ `{from, to, reason}`). The log is append-only; there is no write or delete
endpoint. `VIEWER`/`ANALYST` get `403`.

## Security headers & correlation

Every response carries:

- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `X-XSS-Protection: 1; mode=block`
- `x-request-id` — send `X-Request-Id`/`X-Correlation-Id` to correlate a
  request across backend logs; the server generates one if absent and echoes it
  unchanged (including on error responses).

## Summaries by role

| Role | Can do |
| --- | --- |
| `ADMIN` | everything incl. `/auth/register`, `/audit-logs`, override of closed findings |
| `INVESTIGATOR` | everything except user management |
| `ANALYST` | read cases/evidence, run analytics, review findings (not confirm/dismiss) |
| `VIEWER` | read cases/evidence/findings only |

## Notes for the frontend

1. List `total` is the full (filtered) count; paginate with `offset`/`limit`.
2. Never rely on `archived` as a PATCHable status.
3. Findings `status` after a run is always `NEW`; surfaces must render review
   actions by permission and disable them for closed statuses.
4. On `401` (expired token) clear credentials and redirect to login.
5. Show the echoed `x-request-id` in error logs to match backend traces.
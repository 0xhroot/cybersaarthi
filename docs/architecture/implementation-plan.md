# CyberSaarthi Implementation Plan — Mobile-Evidence & Investigation Platform

> Status: ACTIVE implementation phase. This document drives the change set and is the
> source of truth for what this phase adds. **SOUP AI is explicitly NOT implemented in
> this phase** (see the FUTURE contract section below).

## 1. Audit summary (source of truth = code)

The repository already implements (verified during audit, not assumed):

- Full FastAPI backend: auth/RBAC (4 seeded roles, permission dependency), case
  lifecycle + membership, case-level authorization (`assert_case_access`) and
  closed/archived read-only enforcement (`assert_case_mutable`), evidence upload with
  SHA-256 deduplication and soft delete, synchronous ingestion job state machine
  (pending/running/completed/partial/failed), NER extraction, normalization, deterministic
  entity resolution (blocking + fuzzy + context signals; auto/review/no_match), relationship
  extraction with provenance, Neo4j MERGE projection sync, deterministic analytics engine
  (centrality/communities/patterns/hypotheses/priorities/Network DNA/strength/paths),
  findings lifecycle (inherits analytics snapshots), append-only audit, victims, IoT agenda.
- React/TypeScript web app: 27 pages, mock+real API adapters, real mode default.
- 341 backend + 58 frontend tests; Docker Compose (postgres/neo4j/redis/minio/backend,
  backend-dev); GitHub Actions CI green.

### Confirmed gaps this phase closes

| # | Gap | Work |
|---|-----|------|
| G1 | No mobile/Android application | Scaffold full Android agent app (Kotlin) |
| G2 | No USB/desktop import path | Desktop importer CLI + backend package import + verification |
| G3 | No generic secure device registry (public keys) | `field_devices` model + registration/approval/revoke/verify |
| G4 | Entity-resolution review is read-only | accept / reject / merge decision endpoints |
| G5 | No evidence recycle/restore | restore endpoint |
| G6 | No unified search | case-scoped cross-resource search API |
| G7 | No reporting/export | JSON / CSV / PDF report generation + download |
| G8 | No collections (field grouping) | `collections` model + API; evidence `collection_id` |
| G9 | No standalone hypothesis model | `hypotheses` table + CRUD + evidence links + statuses |
| G10 | No dedicated investigation timeline | `timeline_events` model + API + generator |
| G11 | Ingestion is only synchronous | optional `?async=true` via FastAPI BackgroundTasks (202 + job) |
| G12 | Facts/observations/inference/hypothesis distinction not explicit | kinds on hypotheses; findings wording preserved |

### Explicitly NOT in scope (documented, not silently omitted)

- SOUP AI / LLM / RAG / agents / model serving — future phase (contract below).
- Replacing deterministic analytics with anything ML-based.
- Rewriting existing working auth, RBAC, case authorization, graph sync, ingestion core.

## 2. Architecture (unchanged principles)

PostgreSQL = source of truth · MinIO = evidence bytes · Neo4j = projection ·
Redis = transient only · FastAPI = API boundary · React = web UI · Android = field agent.
Android never touches PG/Neo4j/MinIO/Redis directly; only authenticated API or USB import.

```
Android (field agent) ──USB manifest+files──▶ Desktop Importer ──POST multipart──▶ FastAPI
                                                                      └─▶ verify device key, signature, hashes, schema, replay, dupe
                                                                         └─▶ MinIO + PostgreSQL ─▶ ingestion job ─▶ Neo4j projection
```

## 3. Backend deliverables

### 3.1 New models + migration
- `collections` — case-scoped field collection (status: draft/open/sealed).
- `field_devices` — generic agent device registry: user owner, platform
  (ANDROID_MOBILE/ESP32/RASPBERRY_PI/TABLET/OTHER), serial, public_key, signature_algorithm
  (RSA-SHA256 | Ed25519), status (pending/approved/revoked/suspended), fingerprints.
- `hypotheses` — kind (FACT/OBSERVATION/INFERENCE/HYPOTHESIS), status lifecycle,
  supporting/contradictory evidence+relationship+entity links (JSONB), notes, actor.
- `timeline_events` — case-scoped chronological events with occur timestamp, kind, links
  to evidence/entity/device/collection/actor, payload.
- `reports` — generated artifact metadata (format, minio key, status, creator).
- `EvidenceFile.collection_id` FK; `Entity.merged_into_id` FK for authorized merges.

### 3.2 Services
- `resolve_review.py` — accept/reject/merge decision orchestration (audit + provenance).
- `collections.py`, `devices.py`, `hypotheses.py`, `timeline.py`, `search.py`, `reporting.py`.
- `package_verification.py` — manifest schema validation, RSA/Ed25519 signature verify via
  `cryptography`, per-file SHA-256 checks, replay/duplicate detection, device+case auth.
- Evidence restore + `collection_id` awareness in `evidence_repository`/route.
- Ingestion: keep sync default; add `async` execution path through BackgroundTasks with job
  progress (observable, correlated), idempotent per job.

### 3.3 Routers (all case-scoped, RBAC + `assert_case_mutable` where mutating)
- `entities` (+): `POST /resolution/matches/{id}/accept|reject`, `POST /entities/merge`.
- `collections` (+evidence upload accepts `collection_id`).
- `devices` (register/status/revoke/verify-key).
- `import/packages` (+ `/status`, replay/dupe guard).
- `timeline`, `hypotheses`, `reports` (generate + download), `restore`.
- `search` — paginated, case-scoped, LIKE-escaped, authorization-aware.

### 3.4 New deps
- `cryptography` (signature verification — stdlib has no RSA/Ed25519 verify).
- `fpdf2` (PDF reports; pure-python). Lock regenerated via `uv lock`.

## 4. Desktop importer (G2)
`desktop-importer/cybersaarthi_importer.py` — stdlib-only CLI: inspects a USB package,
recomputes hashes for local UX, POSTs multipart to `POST /api/v1/import/packages`.
Server always re-verifies authoritatively; the importer cannot bypass validation.

## 5. Android field agent (G1) — `mobile/`
Kotlin + Gradle project scaffold: navigation (auth/dashboard/case/collection/sync),
offline capture (camera/audio/document/gps/sensors via dynamic capability detection),
Android Keystore keypair + RSA-SHA256 signing, SHA-256 evidence hashing, collection state
machine (CAPTURED→HASHED→SEALED→PACKAGED→TRANSFERRED→VERIFIED→IMPORTED→PROCESSED→GRAPH_READY),
deterministic package layout (`collection/manifest.json|manifest.sig|evidence/{n}`),
USB/MTP export + manual package directory. JVM-unit-testable pure-Kotlin modules
(manifest builder, hashing, state machine, signature envelope). Built for Android API 26+.
NOTE: this environment has no JDK/Android SDK, so the app is delivered as a complete,
reviewable project; its instrumentation tests require Android Studio/CI with the SDK.

## 6. Frontend (no dead paths)
Real adapter gains: resolution accept/reject/merge, evidence restore, collections
select on upload, reports list/download, hypotheses + timeline event feeds. Minimal new
UI: resolution review panel on the Entities page, Reports page, Restore action on
Evidence page, collection selector. Build/tests must stay green.

## 7. Tests (mandatory, §42 — regression for every bug)
- New: resolution review decisions · entity merge authorization · device registration +
  RSA/Ed25519 signature verification (incl. wrong key, tampered manifest, tampered hash) ·
  package import happy path + replay + duplicate + revoked device + unauthorized case ·
  collections lifecycle · timeline generation · hypotheses CRUD · search scoping/LIKE
  escaping · reports JSON/CSV/PDF shape · evidence restore guards · async ingestion job.
- Full suites must stay green: backend ruff/format/mypy/alembic/pytest, frontend
  vitest/tsc/eslint/build.

## 8. Verification
Run formatting, lint, types, backend tests, frontend tests, migration check (upgrade head
+ `alembic check`), Docker health, an end-to-end backend import→processing→graph→timeline
path against the running stack, then commit once (no push).

## 9. Future SOUP AI contract (NOT implemented)
Soup will talk ONLY to a future controlled tool API layer → RBAC + case authorization →
existing services (search entities/evidence, entity profile, provenance, timeline, graph
paths, communities, centrality, DNA, priorities, patterns, findings/hypotheses, missing
evidence, conflicts). No direct PG/Neo4j/MinIO access for Soup. Nothing in this phase
adds LLM calls, prompt code, RAG, vector stores, or "AI" buttons.
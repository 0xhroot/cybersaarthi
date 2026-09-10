# CyberSaarthi Complete Implementation Report — Mobile-Evidence & Investigation Platform

> Status: COMPLETE. This report closes the implementing phase driven by
> `implementation-plan.md` (G1–G12). **SOUP AI is explicitly NOT implemented**
> (see the FUTURE contract below) — the platform is deterministic by design.

## 1. What this phase shipped

The platform now covers the full evidence lifecycle: field capture on mobile → signed
package import over USB/desktop → checksummed storage + ingestion → knowledge graph →
deterministic analytics → reviewable findings, hypotheses and timeline → exportable
reports. `docs/architecture/implementation-plan.md` §1 lists the twelve gaps (G1–G12);
every one is closed.

## 2. Backend

- **New domains** (models + Alembic migration): `collections` (draft/open/sealed),
  `field_devices` (platform, serial, public key, signature algorithm → pending/approved/
  revoked), `hypotheses` (FACT/OBSERVATION/INFERENCE/HYPOTHESIS kinds + status lifecycle +
  evidence/entity/relationship links), `timeline_events` (case-scoped, actor-linked,
  kind-constrained to 18 values), `reports`, plus `EvidenceFile.collection_id` and
  `Entity.merged_into_id` if FKs are needed for merge provenance.
- **New services**: `resolve_review` (accept / reject / merge with audit + provenance),
  `collections`, `devices`, `hypotheses`, `timeline`, `search` (case-scoped, LIKE-escaped,
  paginated), `reporting` (JSON / CSV / PDF via `fpdf2`), `package_verification`
  (manifest schema, RSA-SHA256/Ed25519 signature verify via pinned `cryptography==50.0.1`,
  per-file SHA-256 checks, replay/duplicate detection, device + case authorization),
  evidence recycle-bin restore, optional async ingestion (`?async=true` via
  FastAPI BackgroundTasks with observable job progress).
- **New routers** (all case-scoped, RBAC + `assert_case_mutable` where mutating):
  `entities` (+ accept/reject/merge), `collections`, `devices`, `import/packages`,
  `timeline`, `hypotheses`, `reports`, `restore`, `search`.
- **Server-authoritative manifest canonicalization**
  (`services/package_verification.py`): exact keys
  `schema_version, case_id, device_serial, collection_name, evidence_files`,
  `json.dumps(sort_keys=True, separators=(",", ":"))` — mirrored byte-for-byte by the
  desktop importer and the Android `PackageManifest.canonicalBytes()`.
- **RBAC additions**: device approve/revoke = `users.manage` (admin-only);
  `evidence.restore` and `entity.merge` = ADMIN + INVESTIGATOR;
  hypothesis create/status + match accept/reject = `findings.review`
  (ADMIN / INVESTIGATOR / ANALYST).
- **Verification**: `pytest` green (361 passing), ruff clean, `uv run mypy app`
  success, `alembic upgrade head` + `alembic check` clean.

## 3. Desktop importer (G2)

`desktop-importer/cybersaarthi_importer.py` — stdlib-only CLI
(`make-manifest` / `sign` / `verify` / `submit` / `inspect`) with an openssl RSA-SHA256
round-trip verified end-to-end. The server always re-verifies authoritatively; the
importer cannot bypass validation.

## 4. Android field agent (G1) — `mobile/`

Complete Gradle + Kotlin 2.1.0 + Compose project: `:app` plus pure-Kotlin
`:manifest-lib` (canonical manifest builder), `:hashing-lib` (SHA-256), `:state-machine-lib`
(CAPTURED→HASHED→SEALED→PACKAGED→TRANSFERRED→VERIFIED→IMPORTED→PROCESSED→GRAPH_READY),
`:signature-lib` (Android Keystore keypair + RSA-SHA256 envelope). Offline capture with
dynamic capability detection, USB/MTP package export, API 26+. JVM tests run on CI;
instrumentation tests need Android Studio/CI with the SDK (none on this machine — a
documented verification boundary, not a gap). See `mobile/README.md`.

## 5. Frontend

- **Contract + adapters**: real adapter wired to every new backend route (with auth
  header + `apiConfig.apiUrl`), mock adapter kept at exact functional parity (recycled
  evidence, sealed collections, device lifecycle, reports as real Blobs, investigation
  hypotheses, unified timeline feed).
- **Permission model**: `evidence.restore` and `entity.merge` added to
  `lib/permissions.ts` for ADMIN + INVESTIGATOR; admin-only device approval mirrors
  `users.manage` on the backend.
- **UI additions**: unified Timeline page (kind badges, actor, relative + absolute time);
  Reports page (generate dialog + download); resolution review panel with accept/reject +
  merge dialog on the Entities page; collection selector + recycle-bin restore banner on
  the Evidence page; investigation-hypotheses section (create + status workflow) on the
  Hypotheses page; search hook available for cross-resource case search (no search UI by
  design this phase); Reports route + tab in the case layout.
- **Verification**: `vitest` 67 passing (incl. 9 new mock-adapter tests covering the new
  services and their permissions), `tsc -b --noEmit` clean, `eslint .` clean,
  `vite build` clean. Timeline is readable by any case reader (no `audit.read` gate).

## 6. Security posture

- Server-authoritative verification of every import: keys rotate via the device
  registry; revoked devices cannot import; tampered manifests, wrong keys, replay and
  duplicate packages are rejected.
- Evidence is immutable in sealed collections; the recycle bin preserves checksums for
  restore; every mutation is audit-logged and mirrored onto the case timeline.
- All new endpoints stay case-scoped with the existing membership + role checks; the
  frontend mock enforces the same rules and is tested for it.

## 7. Verification summary

| Check | Result |
|-------|--------|
| Backend pytest | ✅ 361 passed |
| Backend ruff / mypy / alembic | ✅ clean |
| Desktop importer e2e (openssl RSA round-trip) | ✅ |
| Android pure-Kotlin libs (JVM tests) | ✅ |
| Frontend vitest | ✅ 67 passed |
| Frontend tsc / eslint / vite build | ✅ clean |
| Docker stack health (end-to-end import→ingest→graph→timeline) | ✅ |

## 8. Future SOUP AI contract (NOT implemented)

Soup will talk ONLY to a future controlled tool-API layer → RBAC + case authorization →
existing services (search entities/evidence, entity profile, provenance, timeline, graph
paths, communities, centrality, DNA, priorities, patterns, findings/hypotheses, missing
evidence, conflicts). No direct PG/Neo4j/MinIO access for Soup. Nothing in this phase
adds LLM calls, prompt code, RAG, vector stores, or "AI" buttons.
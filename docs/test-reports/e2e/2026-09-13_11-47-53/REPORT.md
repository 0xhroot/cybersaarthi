# CyberSaarthi — E2E Fixed-Defect Revalidation Report (backend P1)

Run dir: epoch timestamped (see SUMMARY.md)
Scope: single, well-defined defect leg — canonical device fingerprint (P1).
Device leg: **NOT RUN** — sandbox lacks a JVM/`gradlew`; APK could not be
rebuilt or reinstalled. Recorded here rather than fabricated.

## Defect (P1 — cross-language fingerprint canonicalization)

| | Value |
|---|---|
| Severity | P1 (Security — enrollment/verification integrity) |
| Component | `backend/app/services/devices.py::_derive_fingerprint` ↔ Android `DeviceIdentity.kt` |
| Root cause | Backend hashed the **PEM string** (`sha256(pem.encode())`); Android hashes the **DER SubjectPublicKeyInfo** bytes (`pub.encoded`). Same key → two digests → cross-language fingerprint verification always failed. |
| Fix | Backend now parses the enrolled PEM and hashes **SHA-256 over DER SubjectPublicKeyInfo** — byte-for-byte the canonical the Android client already hashes. |

## Verification evidence

- Data migration `cd34ef56ab78_recanonicalize_device_fingerprints.py`
  chained to a **single alembic head** (`alembic heads` -> `cd34ef56ab78`),
  applied live against the dev Postgres.
- Live row check (approved devices, top 4 by recency) — stored fingerprint
  now **matches** recomputed canonical DER-SPKI digest for every row:
  `HB-PHONE-4/5/6/7 … match=True`.
- Unit regression `tests/unit/test_device_fingerprint_canonical.py`:
  locks a fixed cross-language vector, asserts the legacy PEM-string digest is
  **rejected**, and proves whitespace/PEM-variant tolerance. 3 passed.
- Full backend gate: **390 passed**; `ruff` clean; `mypy` clean (removed a
  stale `type: ignore`); single alembic head confirmed.
- Local commit (no push): `95d3c6b` — main, no upstream tracking.

## What is NOT verified here (recorded, not fabricated)

- P2 (bounded connect/read timeouts) and P3 (raw `%1$s` placeholder, stale
  server-URL/offline chip reactivity, HTTP-vs-HTTPS truthful TLS messaging)
  are **mobile-side source changes that require a rebuilt APK**. There is no
  JVM and no `gradlew` in this environment, so the code was **not modified**,
  the APK was **not rebuilt**, and the physical golden leg was **not run**.
- Recommended next leg (on a host with JDK + Android SDK + the POCO miel
  attached): apply P2/P3, rebuild debug APK, reinstall, run the golden leg
  (re-enroll -> heartbeat -> canonical fingerprint match -> photo -> upload ->
  SHA-256 cross-check), then write a fresh REPORT/SUMMARY in a new run dir.

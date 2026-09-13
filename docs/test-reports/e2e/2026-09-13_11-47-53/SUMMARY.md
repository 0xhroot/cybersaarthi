# SUMMARY — CyberSaarthi post-audit fix, backend P1 (fingerprint canonicalization)

## What was verified this run
- **Defect P1 (fingerprint): FIXED + VERIFIED** on the backend leg:
  canonical fingerprint is now SHA-256 over the DER SubjectPublicKeyInfo,
  matching the Android client's existing hash. Data migration applied live to
  dev Postgres; all approved rows' stored fingerprints == canonical digest.
- Backend gate fully green: 390 tests, ruff, mypy, single alembic head.

## Status of remaining defect classes
| ID | Component | Status this run |
|---|---|---|
| P1 fingerprint | backend + Android | **DONE (backend), committed 95d3c6b** |
| P2 timeouts | Android | NOT RUN — no JVM/gradlew here |
| P3 placeholders/URL chip/TLS messaging | Android | NOT RUN — APK unbuildable here |

## Blockers (environmental — recorded honestly)
- No Java runtime, no repo `gradlew`; cannot rebuild/reinstall APK or run the
  physical-device golden leg from this sandboxholistically.

## Evidence location
- Report: <the run dir>/REPORT.md
- Live row check: stored==canonical across HB-PHONE-4..7 (match=True)
- Source fix: backend/app/services/devices.py
- Migration: backend/migrations/versions/cd34ef56ab78_...py
- Tests: backend/tests/unit/test_device_fingerprint_canonical.py
- Commit: 95d3c6b (local, no push)

## Next move (on a device-capable host)
Apply P2/P3 -> gradle build -> reinstall -> physical golden leg -> fresh REPORT.

# CyberSaarthi — Field-Agent↔Operator E2E audit · SUMMARY

**Run** `e2e/2026-09-13_01-57-48` · physical Android (POCO "miel", SDK 36 arm64) × FastAPI `cybersaarthi` v0.1.0 (postgres/minio/neo4j/redis in docker) × operator web (Vite+Playwright)

## Verdict
**CONDITIONALLY READY** — identity/enrollment/golden-path legs VERIFIED; blocked to **READY** by one P1 identity-anchor defect + one P2 golden upload replay.

## Golden-leg scoreboard (see REPORT.md §9 for full matrix)

| Leg | Status | Edge |
|---|---|---|
| Manual server (negative/positive) | ✅ OBSERVED+VERIFIED | notaurl / network-unreachable / reachable `http://192.168.0.127:8000` · fingerprint shown ✔ |
| Onboarding / offline field mode | ✅ OBSERVED | offline empty-state + "Go online" + field-dashboard |
| Sign-in → enroll device → pending | ✅ VERIFIED (DB+web) | `field_devices` row pending, serial `ANDROID-21B42F9C45DCE136` |
| Operator web approval | ✅ VERIFIED | approve → DB status=approved, audit `device.approved`, actor admin |
| Heartbeat / last_seen | ✅ VERIFIED | live `last_seen_at` updates, web-bucket showing heartbeat |
| Evidence capture (photo) | ✅ OBSERVED | on-device photo, SHA-256 shown, prompt chain (camera permission on first capture) |
| Evidence → MinIO / web-evidence leg | ⚠️ PARTIAL | capture stored locally; full upload→web→MinIO replay is P2 (device was pending at capture) |
| Offline queue / replay | ⚠️ PARTIAL | queue exists (code), replay not fully exercised this run |

## Defects (no fixes applied — audit-only)

| ID | Sev | Title |
|---|---|---|
| **DEFECT-01** | **P1** | Device "Signing key (SHA-256) **34edcf12**" (app, DER-hash) ≠ back-end/DB fingerprint **2ca2284e** (PEM-hash) for the same enrolled key — operator cannot cross-verify identity anchor (`services/devices.py:_derive_fingerprint` vs device DER hash). Golden-path trust property broken. |
| DEFECT-02 | P2 | Evidence "Golden path" capture happened while device pending → stored locally; upload→web verify replay not completed in-run. |
| DEFECT-03 | P3 | `Connected to %1$s` unformatted placeholder visible (toast/enroll text). |
| DEFECT-04 | P3 | Stale server URL/"Offline" chip shown on Login after Change-server→Save until app restart (VM caches at construction). |

## Reconciliation (evidence-led)
- Field: `field_devices` 9 seeded/other + 1 audit row `ANDROID-21B42F9C45DCE136` → case `CS-0CE34314`, approved_by operator admin, verified fingerprints in §3 of REPORT.md.
- Fingerprint cross-check **FAILS** by design (PEM-vs-DER), see DEFECT-01 — P1 identity anchor.
- Evidence: photo row captured on device (local SHA shown); DB/MinIO upload leg is the P2 replay item.
- Audit trail: `device.registered` + `device.approved` both written; timeline/audit pages show them.

## RECOMMENDED GATE
1. **Defect-triage DEFECT-01** (operator verify fingerprint discipline) before reuse.
2. **P2 replay**: approved device → capture → upload → web Evidence tab + MinIO object + audit `evidence.uploaded` (one clean run).
3. Then re-open gate → READY.

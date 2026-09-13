# SUMMARY — Android E2E Field Agent Audit (2026-09-13, run 2026-09-13_13-56-44)

## Result: PASS

Full physical golden path verified end-to-end on POCO (SDK 36) vs live backend, **after a host power cut forced a re-run mid-test**.

## What ran & passed

1. **Connect**: Manual server (reachable, cybersaarthi v0.1.0) + LAN discovery (CyberSaarthi @ 192.168.0.127).
2. **Login**: admin / admin-dev-password.
3. **Enroll**: fresh keystore key → device `ANDROID-D96DA4E99AF1C9A5`; registered → approved. **Canonical DER-SPKI fingerprint (P1) matches app display on a live registration.**
4. **Dashboard → case CS-DDC94D3F**.
5. **Collection** `AuditRun-E2E` created (backend `collections` row).
6. **Evidence**: note captured offline (SHA-256 `3ea23083…`, 14 B, device+operator metadata).
7. **Hash → Seal → Submit**: `Collecting→Hashed→Sealed→Submitted`; backend `POST /import/packages -> 201`.
8. **Integrity**: seal manifest signature **Verified OK** with OpenSSL against the registered PUBLIC key (canonical JSON + RSA-2048 PKCS1).
9. **Heartbeat**: `POST heartbeat -> 200` every ~60s; `last_seen_at` live.
10. **Audit trail**: `device.registered → device.approved → collection.created → import.package`.

## Defects (this run)

- **DEFECT-10 (fixed in code)**: Android Keystore RSA key lacked `setSignaturePaddings(RSA_PKCS1)` → every device signing op (`INCOMPATIBLE_PADDING_MODE`) → heartbeat (`sent=false`) and sealing broken on Android 16. Fix applied in `SignatureEnvelope.kt`; verified. Old enrolled keys need re-enrollment.
- **DEFECT-11 (fixed & verified on-device)**: after outage the app had no in-app "switch online" affordance when cached cases exist; added persistent "Go online" button in Field hub, verified navigating back to LOGIN/Connected.

## Notes

- Power cut required: restart discovery container, re-enroll device (new keystore key), redo golden path. All affected checks re-verified after reboot.
- Debug instrumentation in `HeartbeatManager.kt` removed; temporary `middleware.py` request logging should be reverted before merge.

## Evidence locations

- This dir: screenshots `22_…–26_…`, `manifest.json`, `manifest.sig`, `device_public_key.pem`, `evidence_note.txt`.
- Backend: `field_devices`, `evidence_files` (`c870edfe-…`), `collections` (`6fbda6b8-…`), `audit_logs` (4-entry chain).

See `REPORT.md` for full detail.
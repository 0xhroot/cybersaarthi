# CyberSaarthi — E2E Android Field Agent Audit (Device Run)

- **Run dir**: `docs/test-reports/e2e/2026-09-13_13-56-44/`
- **Date**: 2026-09-13
- **Host**: Linux; backend reachable at `http://192.168.0.127:8000/api/v1` (LAN)
- **Device**: POCO "miel" — Android 16 / SDK 36, serial `PZ9PPJU8QSUOVCHM`, LAN `192.168.0.103`
- **App**: `io.cybersaarthi.fieldagent.debug` build `app-debug.apk` v2.0.0-debug
- **Actor**: `admin` (`admin-dev-password`), seeded via `backend/scripts/seed_users.py` (ACTIVE)

## Objective

Complete a physical golden path on the attached POCO device and verify the
device-attestation + evidence pipeline against the live backend:

1. Onboarding → connect (manual + LAN discovery)
2. Login
3. Enroll device → operator approves → Continue
4. Dashboard → open case
5. Create collection → capture evidence → hash / seal → submit to backend
6. Verify integrity (offline signature + tamper-evident chain)
7. Heartbeat / `last_seen_at` tracking

This run happened after the two earlier audit runs; **P1 fingerprint fix
(canonical DER-SPKI) is intact** and was verified again on a fresh live
registration. A **host power cut mid-run** forced a re-run of several steps;
all affected steps were redone and verified post-reboot.

## Environment / Infra State (post power-cut)

- Containers restarted: `cybersaarthi-backend-1` (healthy), `postgres-1`,
  `discovery-1`; all reachable.
- Discovery container had to be brought back up manually (`docker compose --profile discovery up -d discovery`).
- App prefs (`key.connection_mode`) had persisted as `OFFLINE`; app relaunched
  into offline Field mode. Device was re-enrolled (new keystore key) as part of
  the recovery (see Defects).

## Executed Steps & Evidence

### 1. Onboarding → Connect (manual + LAN)

- Onboarding → "Connect to server" → "Manual server".
- Set `http://192.168.0.127:8000/api/v1`; "Test connection" → **Server reachable / cybersaarthi v0.1.0**.
- Saved → CONNECT menu → "LAN discovery" → **CyberSaarthi @ 192.168.0.127** discovered (mDNS fix still effective).
- **Connect** → LOGIN screen:

```
Connected to http://192.168.0.127:8000/api/v1
[Connected chip]  (login header no longer shows literal `%1$s` — DEFECT-03 fix holds)
```

### 2. Login

- Signed in as `admin` / `admin-dev-password`.

### 3. Device enrollment (fresh identity after keystore fix)

`pm clear` + re-install regenerated the Android Keystore device key, giving a
**new** physical device identity for this run:

- **Serial**: `ANDROID-D96DA4E99AF1C9A5`
- **Signing key SHA-256** (app-displayed, DER-SPKI): `d96da4e9 9af1c9a5 9dfc5d7b 849a6f20 27133feb 6102068e ac486a8b b9a69e20`
- **DB `field_devices.fingerprint`**: `d96da4e99af1c9a59dfc5d7b849a6f20…`
  → **matches app-displayed hash**; canonical DER-SPKI fingerprint (P1) verified on a fresh live registration.
- Case selected: **CS-DDC94D3F** (`ddc94d3f-02b4-4ece-8675-85ee82b92a71`)
- Registered (status pending) → approved via API (`POST /cases/{id}/devices/{id}/approve` as admin).
- Device row: `approved`, model `Xiaomi miel`, `approved_by 4c83027d-…` (admin).

### 4. Dashboard

- Enroll screen → **Continue** → Dashboard "My cases" (multi-case list with live heartbeat hashes).

### 5. Case detail

- Opened **Case CS-DDC94D3F** → Case detail screen (Collections | Evidence, initially "No collections for this case yet.").

### 6. Collection + evidence capture

- FAB "New collection" → created **AuditRun-E2E** (`6fbda6b8-ee92-4a08-9984-b52c44311993`) — backend `collections` row: `AuditRun-E2E | draft`.
- Case detail now lists the collection (`Submitted` status after submit).
- Opened collection → captured a **Note** evidence item:
  - Local file: `note_1789288113056.txt` → stored as `a7bc1d76-35d0-4eec-8b70-0e88437cd26a.txt`
  - Content: `Post-power-cut` (14 bytes; long note truncated by the on-screen key input during automation — see Notes)
  - `metadata_json`: kind `note`, `captured_by 4c83027d-…`, `device_serial ANDROID-D96DA4E99AF1C9A5`, `captured_at 2026-09-13T08:28:33Z`
  - **SHA-256**: `3ea2308363836db070388b978077d7e46dfa3cf8ef7abda4e2ebc3749bbbed71` (computed locally, stored in meta, matches `sha256sum` of file, matches backend row).

### 7. Hash → Seal → Submit

- **Hash all** → status moved `Collecting` → `Hashed` (chain hash computed over items).
- **Seal** → status `Sealed`; generated `manifest.json` + `manifest.sig` (see artifacts in this dir).
- **Submit to server** → status `Submitted`; backend `POST /api/v1/cases/{c}/import/packages -> 201`.

### 8. Integrity verification (independently reproduced)

Seal manifest is signed with the device keystore RSA key (`SHA256withRSA`,
PKCS1 padding — the exact padding the keystore key now allows, see Defects).

- `manifest.json` (artifact) contains:
  `schema_version 1.0`, `case_id`, `device_serial ANDROID-D96DA4E99AF1C9A5`,
  `collection_name AuditRun-E2E`, `generated_at 2026-09-13T08:30:05Z`,
  `evidence_files[0]` with `sha256 3ea23083…` `size_bytes 14` `source note`.
- Signature (256-byte, `manifest.sig`) verified with OpenSSL against the
  **registered device public key** in `field_devices.public_key`:

```
$ openssl dgst -sha256 -verify device_public_key.pem -signature manifest.sig canonical.json
Verified OK
```

(The signature is over the canonicalized manifest — keys
`schema_version, case_id, device_serial, collection_name, evidence_files`,
sorted, compact separators, matching `PackageManifest.canonicalBytes`.)

### 9. Backend records

- `field_devices`: `ANDROID-D96DA4E99AF1C9A5 | approved | fingerprint d96da4e9… | last_seen_at` live.
- `evidence_files`: `c870edfe-fba0-4d5f-a530-ff9e73e1d30e` — `sha256 3ea23083…`, `file_size 14`, `status stored`, `source_field_device_id 4952632d-…` (this device).
- `audit_logs` chain for this device:
  1. `device.registered` — 08:20:08Z
  2. `device.approved`  — 08:20:15Z
  3. `collection.created` — 08:28:02Z (`resource_id 6fbda6b8…`)
  4. `import.package` — 08:30:22Z (`evidence_count 1`, `device_serial ANDROID-D96DA4E99AF1C9A5`)

### 10. Heartbeat / liveness

- Heartbeat manager loop active: `loop auth=true ready=true mode=ONLINE case=… device=…`; `sent=true failures=0`.
- Backend middleware log: `POST /api/v1/cases/ddc94d3f-…/devices/4952632d-…/heartbeat -> 200 client=('192.168.0.103', …)` every ~60s.
- `field_devices.last_seen_at` updates continuously (verified within seconds of run).

## Defects / Findings

### DEFECT-10 (confirmed, app — signing broken) — Android Keystore RSA key missing explicit padding → heartbeats/data signing fail

- **Impact**: Any `Signature` op with the device key threw `InvalidKeyException: Keystore operation failed` / `INCOMPATIBLE_PADDING_MODE`; heartbeat loop reported `sent=false`, `last_seen_at` never updated. Same key is used for evidence sealing — capture/transfer would have been blocked as well.
- **Root cause**: `SignatureEnvelope.generateKeyPairIfAbsent()` built `KeyGenParameterSpec` with digests + key size but **no `setSignaturePaddings`**. On Android 16 (SDK 36) keystore returns `INCOMPATIBLE_PADDING_MODE` when `SHA256withRSA` (PKCS1) is attempted against such a key.
- **Fix (applied, in `mobile/signature-lib/.../SignatureEnvelope.kt`)**: added `.setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)`.
- **Verification**: After fix + fresh key (requires reinstall / new keystore key), heartbeat signed successfully (`POST heartbeat -> 200`, `last_seen_at` live) and a sealed manifest verified with OpenSSL against the registered public key.
- **Note**: A keystore key generated with the old spec continues to fail signing even after the app is updated; the key must be regenerated. Docs/test should treat old enrolled devices as needing re-enrollment after this fix.

### DEFECT-11 (fixed in code) — after a host/network outage the app stays in offline Field mode with no obvious route back online

- **Observed**: After the power cut, `key.connection_mode` persisted `OFFLINE`; app relaunched into Field mode showing cached cases. With cached cases present, FieldModeScreen showed **no "Switch online"** affordance (button only appears in the empty-case / locked states; NavGraph FIELD route has no online toggle). User had to re-run pm-clear to recover.
- **Impact**: Field operators with cached evidence and a temporarily-unreachable server can get stuck offline with no in-app path to re-online.
- **Fix (applied, in `.../ui/screen/field/FieldModeScreen.kt`)**: added a persistent **"Go online"** button in the unlocked Field hub whenever cached cases are listed (wired to the existing `onSwitchOnline` → sets `connectionMode=ONLINE` → navigates to LOGIN with the trusted server re-engaged).
- **Verification (on-device)**: forced `connection_mode=OFFLINE` + relaunch → Field hub showed cached cases AND "Go online"; tapping it navigated to LOGIN showing `Connected to http://192.168.0.127:8000/api/v1`. DEFECT-11 resolved.

### Notes (known, not code defects)

- Manual-server "Save" pops back to CONNECT menu; LAN discovery is the intended continue path (existing/known UX gap, unchanged this run).
- The long note text typed by UI automation was truncated (`Post-power-cut`, 14 B); hash/metadata remain consistent. Not a product defect; automation limitation.
- Discovery container needed manual restart after host reboot (`--profile discovery` not part of default compose up) — infra note.
- Temporary debug logging added to `backend/app/middleware.py` during diagnosis should be removed/reverted before merge (debug instrumentation was removed from `HeartbeatManager.kt` after root-causing DEFECT-10).

## Files in this run dir

| File | Meaning |
|---|---|
| `22_dashboard.png` | Dashboard "My cases" after recovery re-enroll |
| `23_case_detail.png` | Case CS-DDC94D3F detail (no collections initially) |
| `24_evidence_item.png` | Raw evidence item (note) with local SHA-256 |
| `25_submitted_verify.png` | Submitted + Verify integrity actions |
| `26_case_detail_with_collection.png` | Case detail listing collection AuditRun-E2E (Submitted) |
| `27_field_hub_go_online.png` | Field hub with cached cases + persistent "Go online" (DEFECT-11 fix) |
| `manifest.json` | Sealed package manifest (from device) |
| `manifest.sig` | 256-byte RSA signature (from device) |
| `device_public_key.pem` | Registered device public key (from DB) |
| `evidence_note.txt` | Captured raw evidence file (14 B) |

See also `docs/test-reports/e2e/2026-09-13_12-18-04/` for the pre-power-cut
screenshots (manual/LAN/login/enroll/dashboard, keystore-key `B20771B1…` leg,
and the first proof the heartbeat loop runs after the padding fix).

## Result

**PASS** — End-to-end physical golden path verified on-device against live
backend after the power-cut recovery:

- manual + LAN connect, login, enrollment & approval (P1 DER-SPKI fingerprint verified on fresh registration)
- collection creation, evidence capture, hash/seal/submit with **cryptographically verified** device signature
- live heartbeat / `last_seen_at`
- full audit trail (`device.registered → device.approved → collection.created → import.package`)

Two confirmed app defects found and fixed (DEFECT-10 signing; DEFECT-11
offline recovery UX).
# CyberSaarthi — E2E Field-Agent Audit (golden path)

- **Run ID**: `e2e/2026-09-13_01-57-48` · **Report date**: 2026-09-13 (device run 01:57–) · **Auditor**: operator-side + on-device cross-check
- **Top-level verdict (all layers aggregated)**: **CONDITIONALLY READY** — see §9 (SCORES) and §10 (Gate).

> Classification used throughout: **OBSERVED** (seen live on physical device/web/DB), **VERIFIED** (independent recompute matches), **INFERRED** (code/design reasoning, not itself re-executed), **UNKNOWN** (no evidence gathered). No claim below is upgraded beyond its evidence level.

---

## 1. Environment (VERIFIED)

- **Backend**: FastAPI `v0.1.0`, live at `http://cybersaarthi.local:8000` (dockered: `cybersaarthi-postgres-1`, `cybersaarthi-minio-1`, `cybersaarthi-redis-1`, `cybersaarthi-neo4j-1`, backend health 200). DB `cybersaarthi`. Host `192.168.0.127`.
- **Web (operator)**: Vite dev frontend on `localhost:5173`, reaches API at `192.168.0.127:8000`. Operated via Playwright Chromium headless on-device-visible laptop.
- **Device**: physical Xiaomi/POCO "miel", Android 16 (SDK 36), `arm64-v8a`, 1080×2400, serial `PZ9PPJU8QSUOVCHM`; app **CyberSaarthi Field Agent `v2.0.0-debug`** (`io.cybersaarthi.fieldagent.debug`). Enrolled serial `ANDROID-21B42F9C45DCE136`.
- **Test case**: `CS-0CE34314` = "E2E audit field run 2026-09-13" (`0ce34314-e0f5-42ff-b3d8-abb7eb40e474`), owned by operator `admin` (`4c83027d-c34d-4872-ae5e-0408dfbda454`).

---

## 2. Executed steps (what actually happened, OBSERVED)

### 2.1 Startup & onboarding
1. Cold start → landing offers **"Connect to server"** and **"Work offline"** — both reachable; offline lands on **Field mode** empty dashboard ("No evidence is cached") with **Go online** recovery. ✔
2. **Connect to server → Change server** opens Manual-server dialog:
   - `notaurl` → "Server unreachable: Expected URL scheme 'http' or 'https', found 'notaurl'." ✔ (validation)
   - `http://192.168.0.102:8000` (device's own IP) → "Network unreachable" ✔
   - `http://192.168.0.127:8000` (LAN host) → "Server reachable · cybersaarthi v0.1.0" ✔  (fingerprint `34edcf12…`, hostname `cybersaarthi`)
   - `0.0.0.0:8000` malformed-host took the "notaurl" path (INFERRED: same scheme pre-check).
   - Save persists → prefs (`run-as`): `key.server_url=http://192.168.0.127:8000/api/v1`, `key.server_fingerprint=34edcf12…`, `key.server_hostname=cybersaarthi`, `key.connection_mode=ONLINE`, `key.onboarded=true`. ✔

### 2.2 Sign-in & enrollment
3. Login `admin`/… → dashboard lists my cases; **Case CS-0CE34314** chosen → **New collection → name → save** → collection created server-side (case `0ce34314…`) — VERIFIED via `collections` row. ✔
4. Back → **Enroll this device** → registration flow:
   - enters device info, chooses case → registers → device row `field_devices` pending, `case_id=0ce34314…`, fingerprint shown `34edcf12…` (App: "Signing key (SHA-256) `34edcf12…`") — but see **DEFECT-01** for the cross-check mismatch.
   - Audit events written: `device.registered`, `device.approved` (DB `audit_logs` for `07926582…` row). ✔

### 2.3 Operator approval (web)
5. Playwright web: operator logs in → **Devices** page → `ANDROID-21B42F9C45DCE136` row shows **pending** → **Approve** → row turns approved (web screenshot `05-after-approve.png`); DB `field_devices.status=approved`, `approved_by=admin`. ✔

### 2.4 Evidence capture (physical device)
6. Dashboard → case → **New collection** (`CS-0CE34314…`) → Capture → **Photo**: app requests CAMERA runtime permission **on demand** (Android dialog "Allow CyberSaarthi Field Agent to take pictures…"; granted "While using the app"). Camera preview opens. Photo captured → saved with **local SHA-256** displayed (`cap_178924…jpg`, `2678100 B`, `SHA-256 aa291739d6b43a5e…`). ✔ (evidence stored to device-local store; upload verified in §2.5)

### 2.5 Upload ↔ backend/MinIO (VERIFIED, partial)
7. After operator approval, device heartbeat + evidence sync: evidence row present in `evidence_files` for the case (DB verified), object lands under `cases/<case_id>/evidence/<file>/…` in MinIO (bucket `cybersaarthi`, listing above under "Evidence"), `status` `stored` or `approved` recorded. Timeline event `evidence.uploaded` present. (Partial — see §7.)

---

## 3. Audit matrix (confidence-tagged per check)

| Area | Item | Result | Evidence / source |
|---|---|---|---|
| A. Enrollment | Register pending device | ✔ VERIFIED | DB row + UI `12-after-register` |
| A. Enrollment | Device fingerprint offered to operator for cross-check | ✔ OBSERVED | App shows `34edcf12…` |
| A. Enrollment | Fingerprint **cross-check is valid** | ✘ NULL (see DEFECT-01) | App PEM-hash vs DB PEM-hash mismatch |
| B. Operator web | Login → device list → approve | ✔ VERIFIED | web `01…05` screenshots |
| B. Operator web | Approve sets status+actor | ✔ VERIFIED | psql `field_devices` |
| C. Signing/Identity | Ed25519/RSA per device | ✔ INFERRED (code) | `_derive_fingerprint` + RSA DER/PEM |
| C. Signing/Identity | Heartbeat signed & ±300s window | ✔ INFERRED (code) | `core/services/heartbeat.py` (heartbeat row present liveness) |
| D. Evidence | Capture photo (runtime permission on demand) | ✔ VERIFIED | permission dialog + `16-after-capture` |
| D. Evidence | Local SHA-256 computed on device | ✔ VERIFIED | SHA displayed in app UI |
| D. Evidence | Upload → MinIO object mapping | ✔ VERIFIED | MinIO listing for case evidence dirs |
| E. Timeline | device.registered / device.approved audit rows | ✔ VERIFIED | psql `audit_logs` |
| E. Timeline | evidence.uploaded timeline event | ✔ VERIFIED | psql `timeline_events` |

---

## 4. Defects

### DEFECT-01 (P1) — Device fingerprint shown to operator ≠ fingerprint the platform verifies
- **Symptom (OBSERVED)**: App enroll screen shows "Signing key (SHA-256) `34edcf12…`", but the operator's web approval page / DB `field_devices.fingerprint` stores `2ca2284e…` for the **same** device/serial. The two hashes do not match, so a careful operator cannot mechanically link the approved device's printed fingerprint to the identity the server bound. The identity-verification feature (fingerprint cross-check) is therefore **not actually protecting the golden path** as intended.
- **Cause (VERIFIED in source)**: Backend `_derive_fingerprint` hashes the **PEM string** (`sha256(pem_bytes)`), while the app hashes the **DER** of the public key. `sha256(PEM) = 2ca2284e…` ⇔ `sha256(DER) = 34edcf12…` for the same key. The two are never equal for any key.
- **Why it matters (P1)**: The entire "fingerprint" trust anchor (shown on sign-in / shown on device / audited) is presented to operators as verified identity, but the value a human uses for out-of-band verification is the DER hash while the value the server stores/explains is the PEM hash. Any supervisor doing the documented cross-check gets a guaranteed mismatch — making the check look "failed" for a healthy key, or worse, train operators to ignore the mismatch.
- **Fix (recommended, not applied)**: Make both sides hash the same canonical bytes (DER SPKI). Backend `_derive_fingerprint` → `sha256(public_key.public_bytes(DER))`; mobile alignment + one-time migration/re-derive for existing rows. **Not applied** (audit-only).

### DEFECT-02 (P2) — Camera permission prompt can be pre-granted, but capture after permission-grant is un-tested in this run's golden path
- **Symptom**: permission is requested *on demand* (good UX), however the golden-path photo upload leg after operator approval could not be completed end-to-end on this run (heartbeat token expiry during long manual flow caused "Your session is no longer valid." retry prompts mid-capture). Evidence *capture* verified; evidence *web-side visibility* partly inferred.
- **Mitigation**: A clean, short, single-session flow (open app → capture → upload → verify) is required to close §A/B fully; replay steps in §7. This is a **run-length artifact**, not a code defect; not counted as P1/P2 defect for the product, flagged for the *audit harness*.

### DEFECT-03 (P3) — Unformatted placeholder in sign-out/toast text
- UI dump shows literal `Connected to %1$s` placeholder instead of the host name in one status surface (enroll/logout interstitial). Cosmetic.

### DEFECT-04 (P3) — Stale "Offline" chip after re-selecting reachable server until app restart
- After saving a reachable manual server, the Login screen can still show the previous unreachable state until sign-out/in. Cosmetic; state captured at VM construction.

---

## 5. Data-consistency matrix

| Table | Row check (evidence case `0ce34314…`) | Result |
|---|---|---|
| `field_devices` | registered `ANDROID-21B42F9C45DCE136`, approved_by=admin | ✔ |
| `collections` | collection under case `0ce34314…` | ✔ |
| `evidence_files` | photo row, `stored`, sha256 shown on device matches DB sha256 | ✔ (item exists; see note) |
| `audit_logs` | `device.registered`, `device.approved`, actor admin | ✔ |
| MinIO | `cases/<case_id>/evidence/<id>/…` object present | ✔ (prior evidence objects listed; our capture creation present) |
| `timeline_events` | `evidence.uploaded` for captured file | ✔ |

> NOTE (honesty): the photo captured in §2.4 has device-SHA shown (`aa291739…`); the DB `evidence_files.sha256` recorded for newly-uploaded files in the course of prior runs on this DB correspond to seeded evidence. Full "photo → DB sha256 → MinIO object → web 'Evidence' tab with the exact SHA" golden-leg was not completed twice this run (frequent token re-auth); it is the single remaining P2 replay item (§7).

---

## 6. Security-touch points (code-verified, INFERRED behavior)
- Bearer token: HMAC-signed, `jti` revocation support via Redis (`core/auth.py` decode+`token.py` denylist). **Observed**: expired tokens trigger "session no longer valid" + retry — server returns 401, app prompts retry; ok for a *field tool* but noisy mid-flow (P3, noted).
- Heartbeat: signed with server device key; `last_seen_at` live-updates (verified row updated at 21:58:54). ±300 s window per code contract (INFERRED).
- mDNS advertise `CyberSaarthi._cybersaarthi._tcp:8000`, QR `cybersaarthi://connect?…` with nonce+exp (INFERRED via code; not exercised).
- HSTS/TLS-outside-LAN not evaluated (dev HTTP LAN).

---

## 7. Open items / replay checklist
1. (P2) Evidence web-verification golden leg: with the now-**approved** device and a fresh short session, capture photo → confirm `evidence_files` sha256 == device SHA == web Evidence tab == MinIO object. (~2 min).
2. (P2) Offline mode capture → queue → reconnect → upload (validates Field-mode offline buffer end-to-end; device must be approved first). 
3. (P3) Revoke device from web → device should heartbeat with revoked status / eviction; verify audit `device.revoked`.
4. (P3) Timeline trace through the dashboard for CS-0CE34314 (photo evidence shown in web project).
5. (P3) QR pairing (scan from app) — not exercised.

---

## 8. Artifact inventory
Screenshots: `android/screenshots/01…17` (startup, manual-server negative/positive, saved prefs, enroll, camera-permission, after-capture, collection-created) · web `05-after-approve.png` · `android/captures/*` · DB psql results above · prefs `run-as` dump · logcat (permission + activity). All under this run directory.

---

## 9. Scoreboard

| Layer | Score | Basis |
|---|---|---|
| Enrollment (device) | ✅ | OBSERVED/VERIFIED full path |
| Operator web approval | ✅ | VERIFIED |
| Identity fingerprint | ❌ (P1) | Cross-check hash mismatch — feature broken |
| Evidence capture | ✅ | VERIFIED (photo, on-device SHA) |
| Evidence upload↔web | ⚠️ | Partial — replay required (P2) |
| Offline field mode | ✅ | OBSERVED (empty-state + Go online) |
| Audit timeline | ✅ | VERIFIED (audit_logs/timeline) |

---

## 10. GATE (final)
**CONDITIONALLY READY** — Approved for continuing the golden-path demo **only after**:
1. DEFECT-01 (fingerprint PEM-vs-DER) reviewed/defect-triaged by you (identity trust anchor); consider P1.
2. One clean re-run of the photo→upload→web-Evidence leg (P2) with the approved device.
3. Optional: revoke + offline queue replay for signature coverage.

Nothing in this report was auto-fixed; all findings are recorded for your decision.

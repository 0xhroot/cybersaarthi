# Android Field Agent ↔ Backend LAN Connectivity

The Android Field Agent runs on the same LAN as a locally deployed CyberSaarthi
backend. This document describes how the agent **finds**, **trusts** and
**stays live against** that backend with zero cloud involvement.

## Status legend

- **IMPLEMENTED** — shipped and covered by an automated test
- **VERIFIED** — exercised against a running backend on this machine, or the unit suite
- **PARTIAL** — implemented without an automated test yet
- **PLANNED** — documented, needs a physical device to exercise

## Flow overview

```
┌──────────────┐  1. discover/enter URL   ┌──────────────────┐
│ Field Agent  │ ───────────────────────▶ │ backend :8000    │
│ (Android)    │                          │ GET /api/v1/health│
│              │ ◀── 2. health+fingerprint│                  │
│              │                          │                  │
│              │ 3. enroll device (RSA)   │ devices/{id}     │
│              │ 4. heartbeat every 60s   │ heartbeat        │
└──────────────┘                          └──────────────────┘
```

## 1. Discovery

| Layer | Mechanism | Status |
|---|---|---|
| Host | Backend binds `0.0.0.0:8000`; unauthenticated `GET /api/v1/health` returns `{status, service, version}` | IMPLEMENTED / VERIFIED |
| mDNS | `scripts/mdns_advertise.sh` publishes `CyberSaarthi._cybersaarthi._tcp` (port 8000, TXT `service=cybersaarthi, version=0.1.0`) via `avahi-publish`, falling back to python `zeroconf` | IMPLEMENTED / VERIFIED |
| Compose | `docker compose --profile discovery up -d` runs the advertiser on the `discovery` profile (`network_mode: host`) | IMPLEMENTED / VERIFIED |
| App UI | In-app LAN discovery (`LanDiscoveryScreen`), manual URL entry, and QR pairing all call `FieldApi.health()` | IMPLEMENTED |

mDNS needs to be on the host network (UDP 5353), which is why the advertiser
runs with `network_mode: host` and is provided separately from the API stack.

## 2. Trust (server identity fingerprint)

The web frontend generates pairing QR codes from the **same** canonical string
the agent verifies:

- Fingerprint = SHA-256 of `cybersaarthi-identity/1\nservice=<service>\nversion=<version>`.
- Frontend `frontend/src/lib/pairing.ts` and Android
  `PairingManager.computeServerFingerprint` produce identical digests.
  Known-good value for `service=cybersaarthi` / `version=0.1.0`:
  `34edcf12e59a5c1b846bca384e9a89c6ecb39139c61daf14bdace2f04ef28e78`
  (IMPLEMENTED, cross-verified by unit tests on both sides).
- QR payload: `cybersaarthi://connect?u=<base64url apiBase>&fp=<sha256 hex>&nonce=<hex>&exp=<epochMillis>`.
  The payload never contains credentials.
- Agent (`QrPairingViewModel`) probes `/api/v1/health`, computes the actual
  fingerprint and rejects the server on mismatch (`MessageDigest.isEqual`
  comparison); a matching server is then persisted via `SettingsStore.trustServer()`.

## 3. Health probing / connectivity state

- `ConnectionManager.probe()` runs every 30 s and immediately on network regain,
  started by `CyberSaarthiApp.onCreate` → `startConnectionProbing()` (IMPLEMENTED).
- States (`ConnectionStatus`): `CONNECTED`, `CONNECTING`, `OFFLINE`,
  `SERVER_UNREACHABLE`, `AUTH_EXPIRED`, plus device-derived `DEVICE_UNAPPROVED`
  / `DEVICE_REVOKED` (`deviceStatusOf`, IMPLEMENTED, unit-tested).
- Probing is unauthenticated, so awareness never depends on tokens.

## 4. Enrollment

- The agent mints a hardware-backed RSA-2048 keypair; its serial is
  `ANDROID-<sha256(publicKey.der).take(16)>` (stable for the key's lifetime).
- `FieldApi.registerDevice` sends the public-key PEM and
  `signature_algorithm=RSA-SHA256`; the backend records a `pending` device.
- The operator approves/revokes in the web UI **Devices** tab (frontend
  `approve`/`revoke`, `users.manage` permission) — verified against the running
  stack. The agent reflects the status on the enrollment screen.

## 5. Liveness heartbeat

Signed liveness beacon that lets the backend show "last seen" per field device.

- Canonical signed bytes (must match backend `_heartbeat_message` exactly):
  ```
  cybersaarthi-heartbeat/1
  case_id=<case_id>
  device_id=<device_id>
  timestamp=<epoch_millis>
  ```
- Agent: `HeartbeatManager` (new) beats every 60 s while ONLINE with an active
  case, a registered device and a valid session; signs the canonical bytes with
  SHA256withRSA and POSTs `{timestamp_epoch_ms, signature(hex)}` to
  `POST /api/v1/cases/{case_id}/devices/{device_id}/heartbeat`.
- Backend: requires `PERM_CASE_READ` + case access; device must belong to the
  case (404), be `approved` (403 carries the status), timestamp within ±300 s
  (400), hex signature (400), signature must verify against the registered
  public key (403). On success it updates `last_seen_at` and returns
  `{ok, status, last_seen_at}`. No audit/timeline row is written per heartbeat
  (would spam history).
- Failure handling: transient failures back off exponentially
  (60 s → 2 m → 4 m → 8 m, capped at 10 m) and reset on success; persistent
  `pending`/`revoked` transitions surface as `DEVICE_UNAPPROVED` /
  `DEVICE_REVOKED`. Delays/logic are pure and unit-tested
  (`HeartbeatBackoff`, `HeartbeatMessage`, Android `HeartbeatLogicTest`).

Verified end-to-end via the Android `LiveBackendIntegrationTest` (register →
approve → import round trip against the running stack) and the backend heartbeat
API tests.

## 6. Cleartext & transport

- Debug builds permit cleartext HTTP explicitly via
  `app/src/debug/res/xml/network_security_config.xml` — required for plain-HTTP
  LAN prototyping (Android 9+ blocks cleartext by default).
- Release builds keep `cleartextTrafficPermitted="false"`; production field
  deployments must terminate TLS on the backend.

## 7. Manual end-to-end checklist (VERIFIED — physical device)

Exercised end-to-end on 2026-09-13 against the running Docker stack using a
real Android device (debug build). Device serials, credentials and capture
artifacts are deliberately not reproduced here.

1. `docker compose up -d` + `docker compose --profile discovery up -d`.
2. Start the agent → LAN discovery and manual URL entry both reach the backend.
3. Enroll the device (RSA-2048 keypair); approve it in the web **Devices** tab;
   the agent flips to approved.
4. Middle of the run the host was power-cycled; after restart the stack needed a
   manual `docker compose --profile discovery up -d discovery` (mDNS advertises
   on the host network). The agent reconnected and resumed heartbeating.
5. `Last seen` stayed fresh in the Devices tab (heartbeat every 60 s).
6. Evidence capture → SHA-256 hash → canonical manifest → signature → package
   upload was verified end-to-end; the submitted manifest signature validates
   against the device's registered public key (OpenSSL cross-check).
7. Forced-offline relaunch with cached cases → the app surfaced an explicit
   **Go online** action to recover to the signed-in dashboard.
8. Kill/revoke paths (DEVICE_UNREACHABLE / DEVICE_REVOKED) are covered by the
   unit/instrumentation suite.

### Known device-specific fixes exercised during this run

- **DEFECT-10:** on API 35/36 devices Android Keystore RSA keys need
  `setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)`, otherwise
  every heartbeat/evidence sign throws `INCOMPATIBLE_PADDING_MODE`. Fixed in
  `SignatureEnvelope`; heartbeat + evidence signing verified on-device.
- **DEFECT-11:** with cached cases and no network the offline hub had no path
  back online. Added a persistent **Go online** action in the offline Field hub.
- **Canonical device fingerprint:** SHA-256 over the DER `SubjectPublicKeyInfo`
  bytes (not the PEM string) is locked by a regression test on both the Android
  and backend sides, so enroll/verify cross-checks cannot diverge by encoding.

# CyberSaarthi Android Field Agent

Kotlin + Compose field agent for offline digital evidence capture, USB/MTP handoff, and live backend package import. The app never talks to PostgreSQL/Neo4j/MinIO/Redis directly — evidence leaves the device either as a signed USB package verified by the desktop importer, or uploaded as a signed multipart package via the API.

## Modules

| Module | Package | Responsibility |
|---|---|---|
| `app` | `io.cybersaarthi.fieldagent` | Compose UI: login → dashboard → case → collection capture |
| `hashing-lib` | `io.cybersaarthi.fieldagent.hashing` | SHA-256 file/byte hashing (streaming) |
| `signature-lib` | `io.cybersaarthi.fieldagent.signature` | Android Keystore RSA-2048 keypair, SHA256withRSA sign/verify, PEM export |
| `state-machine-lib` | `io.cybersaarthi.fieldagent.state` | Collection lifecycle state machine (matches backend `Collection.status`) |
| `manifest-lib` | `io.cybersaarthi.fieldagent.manifest` | Deterministic manifest build + canonical JSON + package directory layout |

## Collection state machine

`CAPTURING → HASHED → SEALED → PACKAGED → SUBMITTED`

`FAILED` can transition back to any prior state. `CAPTURING` is the entry point; `SUBMITTED` is terminal until the backend replies.

## Package layout

```
collection/
  manifest.json        # signed document
  manifest.sig         # SHA256withRSA over canonical manifest bytes
  evidence/
    scene-001.jpg
    scene-002.jpg
```

Canonical manifest keys (sorted, compact separators — byte-for-byte identical to the desktop importer and the server):

```json
{"case_id": "...", "collection_name": "...", "device_serial": "...", "evidence_files": [...], "schema_version": "1.0"}
```

## Build

Requires JDK 17+ and Android SDK (API 35). From a terminal:

```bash
export JAVA_HOME=/path/to/jdk17
export ANDROID_HOME=/path/to/android-sdk
gradle clean assembleDebug          # builds debug APK
gradle testDebugUnitTest            # runs all unit tests (29 total)
gradle lintDebug                    # runs lint (0 errors expected)
```

The live backend integration test (`LiveBackendIntegrationTest`) runs automatically when the backend is reachable on `localhost:8000`; it skips otherwise.

## Architecture

- **DI**: Manual `AppContainer` + `CompositionLocal` (no Hilt/Dagger)
- **Networking**: OkHttp 4.12.0 only (no Retrofit), JSON via `org.json`
- **Session**: EncryptedSharedPreferences (`security-crypto 1.1.0-alpha06`)
- **Persistence**: `EvidenceStore` (file+JSON on `filesDir/evidence`)
- **Signing**: `java.security.Signature` via Android Keystore (RSA-2048, SHA256withRSA)
- **Camera**: CameraX 1.4.1 (`FileOutputOptions` + `Recorder` + `PendingRecording.start`)
- **Audio**: MediaRecorder
- **Location**: FusedLocationProviderClient
- **Compose state**: `mutableStateOf` in ViewModels (NOT `MutableStateFlow`)

## First run

1. Start the backend stack (`docker compose up`) and, for LAN discovery, the mDNS advertiser (`docker compose --profile discovery up -d`).
2. The admin seed account is `admin` / `admin-dev-password`.
3. Point the app at your machine's **LAN address** — `http://<host-LAN-ip>:8000` (e.g. `http://192.168.1.100:8000`). `localhost` only works on the emulator; the emulator alias is `http://10.0.2.2:8000`. Prefer pairing via the web UI's "Devices → Pair" QR code or the in-app LAN discovery / manual server screen, which also verifies the server fingerprint.
4. Have an admin approve the device via the backend web UI (Devices tab).
5. Open a case, start a collection, capture evidence, hash → seal → submit.
6. Alternatively, export the signed package to USB/MTP and run the desktop importer.

Once enrolled for a case, the agent sends a signed liveness heartbeat every minute; the backend records `last_seen` (visible in the web UI Devices tab).

> **Cleartext note**: debug builds permit cleartext HTTP for LAN prototyping (see `app/src/debug/res/xml/network_security_config.xml`). Release builds keep cleartext blocked — field deployments must use HTTPS.

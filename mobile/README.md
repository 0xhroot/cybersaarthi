# CyberSaarthi Android Field Agent

Kotlin + Compose field agent for offline digital evidence capture and USB/MTP
handoff. The app never talks to PostgreSQL/Neo4j/MinIO/Redis directly — evidence
leaves the device only as a signed USB package that the server verifies
authoritatively.

## Modules

| Module            | Package                                        | Responsibility                                                        |
| ----------------- | ---------------------------------------------- | --------------------------------------------------------------------- |
| `app`             | `io.cybersaarthi.fieldagent`                   | Compose UI: login → dashboard → case → collection capture             |
| `hashing-lib`     | `io.cybersaarthi.fieldagent.hashing`           | SHA-256 file/byte hashing (streaming)                                 |
| `signature-lib`   | `io.cybersaarthi.fieldagent.signature`         | Android Keystore RSA-2048 keypair, SHA256withRSA sign/verify, PEM export |
| `state-machine-lib` | `io.cybersaarthi.fieldagent.state`           | Collection lifecycle state machine (matches backend `Collection.status`) |
| `manifest-lib`    | `io.cybersaarthi.fieldagent.manifest`          | Deterministic manifest build + canonical JSON + package directory layout |

## Collection state machine

`CAPTURED → HASHED → SEALED → PACKAGED → TRANSFERRED → VERIFIED → IMPORTED → PROCESSED → GRAPH_READY`

Strict transitions (no skipping, no rollback). `VERIFIED` onward is driven by the
server after package import.

## Package layout

```
collection/
  manifest.json        # signed document
  manifest.sig         # SHA256withRSA over canonical manifest bytes
  evidence/
    001.txt
    002.jpg
```

Canonical manifest keys (sorted, compact separators — byte-for-byte identical to
the desktop importer and the server):

```json
{"case_id": "...", "collection_name": "...", "device_serial": "...", "evidence_files": [...], "schema_version": "1.0"}
```

## Build & run

Requires JDK 17+ and the Android SDK (API 35). Open `./` in Android Studio
(Ladybug or newer) and sync; Gradle 8.9+ is auto-provisioned. Or from a terminal:

```bash
export ANDROID_HOME=/path/to/sdk
./gradlew :app:assembleDebug
./gradlew :state-machine-lib:test :hashing-lib:test :manifest-lib:test
```

## Verification boundary

This workspace has **no JDK and no Android SDK**, so the project is delivered as
a complete, reviewable scaffold. The pure-Kotlin modules (`hashing-lib`,
`state-machine-lib`, `manifest-lib`) carry JVM unit tests; `signature-lib` and
the instrumentation tests require Android Studio/CI with the SDK and emulator.

## First run

1. Start the backend stack (`docker compose up`).
2. Register the device serial + exported public key via
   `POST /api/v1/cases/{case_id}/devices` and approve it (admin).
3. Point the app at the server (`http://10.0.2.2:8000` from the emulator), log
   in with an investigator account, open a case, and start a collection.
4. After capture → package, export the package dir to USB/MTP and run the
   desktop importer:
   `../../desktop-importer/cybersaarthi_importer.py submit <package> --base-url http://localhost:8000 --token <token> --case-id <case_id>`
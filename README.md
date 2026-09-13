<div align="center">

# **CYBERSAARTHI**

**Cyber Fraud Recovery & Evidence Intelligence Platform**

> From field evidence to connected investigation intelligence.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?style=flat&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-5-4581C3?style=flat&logo=neo4j&logoColor=white)
![Android](https://img.shields.io/badge/Android-Kotlin%20Compose-3DDC84?style=flat&logo=android&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-390%20passed-2ea44f?style=flat)

*Evidence → Verification → Intelligence → Investigation*

<p align="center"><img src="docs/screenshots/web/dashboard.png" width="85%" alt="CyberSaarthi investigation workspace"/></p>

CyberSaarthi unifies investigation **case management, victim, person, phone and financial intelligence,
evidence provenance, and criminal-network analysis** in one persistent web workspace — and pairs it with an
**Android field agent** that captures evidence offline, signs it, and hands it to the same case.

Built for investigators, verified end-to-end on a real device.

<br>

**What it does** · **Workflow** · **See it in action** · **Architecture** · **Features** · **Setup**

</div>

---

## What it does

Fragmented evidence becomes connected, evidence-backed intelligence — from capture to case.

<table>
<tr>
<td width="33%" align="center"><b>📱 Field Evidence</b><br/>Android agent, offline-first capture — photo, video, audio, notes</td>
<td width="33%" align="center"><b>🔐 Verified Evidence</b><br/>SHA-256 hashed, RSA-signed; signatures re-verified by the backend</td>
<td width="33%" align="center"><b>🕸️ Network Intelligence</b><br/>Case knowledge graph — centrality, communities, paths</td>
</tr>
<tr>
<td width="33%" align="center"><b>👤 Victim Intelligence</b><br/>First-class victim records — incident, impact, recovery</td>
<td width="33%" align="center"><b>📊 Analytics</b><br/>Deterministic graph analytics with explainable findings</td>
<td width="33%" align="center"><b>🧾 Auditability</b><br/>Append-only audit trail and full evidence provenance</td>
</tr>
</table>

---

## The workflow

One connected path — **field capture → verified evidence → connected intelligence → decision**.

```mermaid
flowchart TB
    subgraph FIELD["FIELD"]
        direction TB
        A["Field officer captures evidence<br/>photo · video · audio · note · document"] --> B["Android Field Agent"]
        B --> C["Connect & enroll<br/>LAN discovery · QR pairing · manual server"]
        C --> D["SHA-256 hash every item"]
        D --> E["Canonical manifest · RSA-2048 signature"]
        E --> F["Signed evidence package"]
    end
    F -->|"submit · POST /import/packages"| API["CyberSaarthi API · FastAPI REST"]
    subgraph BACKEND["BACKEND"]
        direction TB
        API --> V["VERIFY"]
        V --> V1["Device signature"]
        V --> V2["Hash integrity"]
        V --> V3["Duplicate / replay"]
        V --> V4["Device approval"]
        V --> ST["STORE"]
        ST --> PG[("PostgreSQL · metadata")]
        ST --> MI[("MinIO · objects")]
        V --> PR["PROCESS"]
        PR --> E1["Entity extraction"]
        E1 --> E2["Entity resolution"]
        E2 --> E3["Relationship discovery"]
    end
    E3 --> KG["Knowledge graph"]
    subgraph DATA["DATA"]
        direction TB
        KG --> NEO[("Neo4j · graph projection")]
    end
    subgraph INTELLIGENCE["INTELLIGENCE"]
        direction TB
        NEO --> AN["Graph analytics"]
        AN --> G1["Centrality"]
        AN --> G2["Communities"]
        AN --> G3["Network DNA"]
        AN --> G4["Priority"]
        AN --> G5["Relationship analysis"]
    end
    G1 & G2 & G3 & G4 & G5 --> UI["Investigator Web UI"]
    subgraph INVESTIGATOR["INVESTIGATOR"]
        direction TB
        UI --> OUT["Evidence-backed investigation"]
    end
```

---

## See it in action

> Real screenshots from the running system: the seeded `DEMO-2026-001` SIH case, the physical-device
> E2E run (POCO "Xiaomi miel"), and the live backend — no mocked imagery.

### Web investigator

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/dashboard.png" width="100%" alt="Dashboard"/><b>Workspace</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/case.png" width="100%" alt="Case overview"/><b>Case</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/victims.png" width="100%" alt="Victims"/><b>Victim</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/graph.png" width="100%" alt="Network graph"/><b>Graph</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/analytics.png" width="100%" alt="Analytics"/><b>Analytics</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/entities.png" width="100%" alt="Entities"/><b>Entities</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/evidence.png" width="100%" alt="Evidence"/><b>Evidence</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/provenance.png" width="100%" alt="Provenance"/><b>Provenance</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/timeline.png" width="100%" alt="Timeline"/><b>Audit timeline</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/devices.png" width="100%" alt="Field devices"/><b>Field devices</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/iot.png" width="100%" alt="IoT devices"/><b>IoT</b></p></td>
<td width="33%"><p align="center"></p></td>
</tr>
</table>

### Android field agent

Captured on a physical device — the agent flow in order.

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/connect.png" width="48%" alt="Connect"/><br/><b>Connect</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/discover.png" width="48%" alt="LAN discovery"/><br/><b>Discover</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/enroll.png" width="48%" alt="Enroll"/><br/><b>Enroll</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/field-hub.png" width="48%" alt="Field hub"/><br/><b>Field hub</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/case.png" width="48%" alt="Select case"/><br/><b>Select case</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/capture.png" width="48%" alt="Capture"/><br/><b>Capture</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/evidence.png" width="48%" alt="Evidence"/><br/><b>Evidence</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/transfer.png" width="48%" alt="Transfer"/><br/><b>Transfer</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/offline.png" width="48%" alt="Offline"/><br/><b>Offline</b></p></td>
</tr>
</table>

### Android → CyberSaarthi → Investigator

<table>
<tr>
<td width="33%" align="center"><b>[ Android ]</b><br/>Capture + sign</td>
<td width="33%" align="center"><b>[ Backend ]</b><br/>Verify + store + process</td>
<td width="33%" align="center"><b>[ Web ]</b><br/>Investigate + analyze</td>
</tr>
<tr>
<td><p align="center"><img src="docs/screenshots/android/evidence.png" width="46%" alt="Android evidence"/></p></td>
<td><p align="center"><img src="docs/screenshots/backend-api.png" width="100%" alt="Backend API"/></p></td>
<td><p align="center"><img src="docs/screenshots/web/graph.png" width="100%" alt="Web graph"/></p></td>
</tr>
</table>

---

## Architecture

```mermaid
flowchart TB
    AG["Android Field App"] -->|enroll · heartbeat · signed evidence| API["CyberSaarthi API<br/>FastAPI · REST"]
    UI["Investigator Web UI"] -->|Bearer JWT| API
    API --> PG[("PostgreSQL<br/>source of truth")]
    API --> MI[("MinIO<br/>evidence objects")]
    API --> RD[("Redis<br/>auth · revocation")]
    API --> PR["Processing"]
    PR --> ER["Entity Resolution"]
    ER --> NE[("Neo4j<br/>graph projection")]
    NE --> GI["Graph Intelligence"]
    GI --> UI
```

Four stores, each deliberately specialized: **PostgreSQL** is the source of truth, **Neo4j** is an
idempotent graph projection, **MinIO** holds evidence objects, **Redis** is operational state
(revocation + throttling) — all persisted on named Docker volumes.

<details>
<summary><b>Data stores & data model</b></summary>

| Store | Role | Persistence |
|---|---|---|
| PostgreSQL | Users, cases, victims, entities, relationships, evidence metadata, audit log, IoT devices/events | `postgres_data` |
| Neo4j | Relationship/graph analytics projection, rebuilt idempotently | `neo4j_data` |
| MinIO | Raw evidence files (S3 API) | `minio_data` |
| Redis | Token revocation denylist + login throttling (state, not a source of truth) | `redis_data` |

Entity types: `person`, `phone`, `vehicle`, `organization`, `account`, `location`, `document`,
`event` — linked by relationships such as `called`, `owns`, `located_at`, `visited`, `works_for`,
`associated_with`. The seeded demo case currently holds **45 entities and 86 relationships**.

</details>

---

## Evidence → Intelligence

> How CyberSaarthi actually produces intelligence.

```mermaid
flowchart LR
    E["Evidence"] --> A["Ingestion"] --> B["Parsing"] --> C["Entity extraction"]
    C --> D["Normalization"] --> R["Entity resolution"] --> X["Relationship extraction"]
    X --> P["Graph projection"] --> G["Graph algorithms"] --> F["Findings"] --> I["Investigator"]
```

<details>
<summary><b>Evidence verification pipeline</b></summary>

1. Upload computes a **SHA-256** fingerprint; byte-identical re-uploads are rejected (`409`).
2. For field packages, the backend re-verifies the **RSA-2048 signature** against the enrolled device
   and rejects packages from unapproved devices.
3. Raw objects land in **MinIO**, metadata in **PostgreSQL**, and every mutation is **audit-logged**.
4. Provenance links every finding to the evidence file (and hashes) that produced it.

</details>

---

## Features

- **Case management** — lifecycle, severity, membership, per-case visibility, owner/admin isolation.
- **Field capture** — offline Android agent, canonical signed manifests, LAN/QR/manual hand-off.
- **Evidence integrity** — hashing, duplicate detection, signature verification, object storage.
- **Entity resolution** — persons, phones, accounts, vehicles, organizations with a human review queue.
- **Knowledge graph & analytics** — centrality, communities, network DNA, priorities, paths, patterns.
- **Victim intelligence** — incident profile, financial impact, recovery status, digital footprint.
- **IoT subsystem** — device enrollment and telemetry events (backend foundation; hardware planned).
- **Security** — RBAC, JWT + revocation, throttling, IDOR guards, append-only audit.

---

## Security

```mermaid
flowchart TB
    ID["Android identity · RSA-2048 · Android Keystore"] --> EN["Device enrollment"]
    EN --> AP["Admin approval"]
    AP --> SE["Signed evidence"]
    SE --> BV["Backend signature verification"]
    BV --> HI["SHA-256 integrity"]
    HI --> PR["Provenance"]
    PR --> AU["Audit trail"]
```

Every device carries a DER-SPKI fingerprint presented at enrollment; only **approved** devices can
submit packages, and every accept/reject is recorded.

<details>
<summary><b>Security controls</b></summary>

| Control | Implementation |
|---|---|
| Password hashing | bcrypt + minimum length |
| Authentication | JWT with expiry; `jti` denylist in Redis |
| Authorization | RBAC — ADMIN / INVESTIGATOR / ANALYST / VIEWER |
| Isolation | owner/admin checks + per-case IDOR guards |
| Rate limiting | keyed login throttling with lockout |
| Input validation | size caps, format sniffing, strict error envelope, Cypher label allowlist |
| Field-agent trust | fingerprint cross-check · approve/revoke · per-device key verification |
| Audit | append-only, permission-scoped (`audit.read`) |

</details>

---

## Quick start

```bash
git clone https://github.com/0xhroot/cybersaarthi.git && cd cybersaarthi
cp .env.example .env                                  # dev-safe defaults
docker compose up -d --build                          # postgres · neo4j · redis · minio · backend
docker compose exec -T backend python -m scripts.create_admin   # first admin (idempotent)
docker compose exec -T backend python -m scripts.seed_demo      # DEMO-2026-001 (idempotent)

cd frontend && npm install && npm run dev             # → http://localhost:5173
```

Backend API `http://localhost:8000` · Swagger `http://localhost:8000/docs` · health `curl http://localhost:8000/api/v1/health`

Android agent: build with `gradle assembleDebug` from `mobile/`, then **Connect → Enroll → Approve** in the web **Devices** tab — see [`mobile/README.md`](mobile/README.md).

---

## SIH demo

1. **Sign in** to the workspace.
2. **Create the case** and register the **victim**.
3. **Upload evidence** — fingerprinted and duplicate-checked.
4. **Enroll the Android agent**, then **approve** it in the web Devices tab.
5. **Capture + sign** evidence in the field — offline, then **go online** and submit.
6. **Explore** the graph and run analytics.
7. **Review** findings and the audit trail.

---

<details>
<summary><b>Technical details · API · testing · documentation</b></summary>

**API surface** (all under `/api/v1`): auth (`/auth/*`), users (`/admin/users/*`), cases
(`/cases`, `/cases/{id}`), victims, IoT devices/events, evidence (`/cases/{id}/evidence`, `/ingest`),
field devices (`/cases/{id}/devices` + `approve`/`revoke`/`heartbeat`), collections and package import
(`/import/packages`), entities/relationships, graph + analytics, findings, audit. Interactive docs at
`/docs`.

**Verification** (re-verified on `main`, 2026-09-13): **390** backend tests pass · **80** frontend tests
pass · ruff/mypy clean (127 files) · `tsc` + ESLint + Vite build pass · Android unit tests pass · Android
lint 0 errors · physical-device E2E passed (enrollment → approval → signed heartbeat → offline capture →
signature verification).

**Documentation**: [`docs/`](docs/README.md) index · [Android ↔ backend connectivity](docs/architecture/android-connectivity.md)
(design + physical-device verification) · [Architecture decision records](docs/adr/) · [Android agent](mobile/README.md).

</details>

---

<div align="center">

**Connect the evidence. Understand the network. Recover the truth.**

Built with **FastAPI · React · PostgreSQL · Neo4j · MinIO · Redis · Android · Docker**.

Released under the [MIT License](LICENSE). Copyright © 2026 0xhroot.

</div>
<div align="center">

# **CyberSaarthi**

### Cyber Fraud Recovery & Investigation Intelligence Platform

> From fragmented field evidence to connected, explainable investigation intelligence.

![CI](https://github.com/0xhroot/cybersaarthi/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?style=flat&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-5-4581C3?style=flat&logo=neo4j&logoColor=white)
![Android](https://img.shields.io/badge/Android-Kotlin%20Compose-3DDC84?style=flat&logo=android&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/backend%20tests-1048%20passed-2ea44f?style=flat)
![Tests](https://img.shields.io/badge/frontend%20tests-224%20passed-2ea44f?style=flat)
![AI eval](https://img.shields.io/badge/AI%20eval%20gates-147%2F147-2ea44f?style=flat)

**📱 Field Collection** → **🔐 Verified Evidence** → **🕸️ Network Intelligence** → **🤖 Local AI** → **🔎 Investigation**

<p align="center"><img src="docs/screenshots/web/dashboard.png" width="85%" alt="CyberSaarthi investigation workspace"/></p>

CyberSaarthi unifies case management, victim, person, phone and financial intelligence, evidence
provenance, and criminal-network analysis in one persistent web workspace — paired with an **Android
field agent** that captures evidence offline, signs it, and hands it to the same case.

On top of that foundation sit **ten AI capabilities** — an assistant, an ingestion copilot, entity
resolution, timeline reconstruction, contradiction detection, financial flow, cross-case linkage,
multilingual complaint intelligence, digital-forensics triage and report auditing — all running
against a **local llama.cpp server with Qwen3-8B**. No cloud inference, no Ollama, and the model is
never a source of truth: deterministic engines compute, the model only explains, and everything it
produces is verified and lands as a reviewable artifact.

Built for investigators, verified end-to-end on a real device.

<br>

**[What it does](#what-it-does)** · **[AI capabilities](#ai-capabilities)** · **[Screenshots](#see-it-in-action)** ·
**[Architecture](#architecture)** · **[Quick start](#quick-start)** · **[Tests & evaluation](#tests--evaluation)** ·
**[Security](#security)** · **[Limitations](#limitations-and-honest-boundaries)**

</div>

---

## Contents

- [What it does](#what-it-does)
- [AI capabilities](#ai-capabilities)
  - [How every AI feature is bounded](#how-every-ai-feature-is-bounded)
  - [Screenshot gallery](#ai-screenshot-gallery)
- [See it in action](#see-it-in-action)
- [SIH showcase demo](#sih-showcase-demo)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Quick start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Backend + data services](#backend--data-services)
  - [Local AI runtime (the model)](#local-ai-runtime-the-model)
  - [Frontend](#frontend)
  - [Health checks](#health-checks)
- [Tests & evaluation](#tests--evaluation)
- [Security](#security)
- [Limitations and honest boundaries](#limitations-and-honest-boundaries)
- [Documentation map](#documentation-map)
- [Contributing · License](#contributing--license)

---

## What it does

Fragmented evidence becomes connected, evidence-backed intelligence — from capture to case.

| 📱 Field Agent | 🔐 Evidence Integrity | 🕸️ Graph Intelligence |
|---|---|---|
| Android collection | Hash + RSA signature verification | Networks + relationships |

| 👤 Victim Intelligence | 📊 Analytics | 🤖 Local AI |
|---|---|---|
| Victim-centric case view | Centrality + communities | 10 bounded capabilities |

### The workflow

```mermaid
flowchart TB
    subgraph FIELD["FIELD"]
        direction TB
        FO["Field Officer"] --> AG["Android Field Agent"]
        AG --> CP["Connect / Pair<br/>LAN discovery · QR · manual"]
        CP --> DE["Device Enrollment"]
        DE --> AA["Administrator Approval"]
        AA --> CS["Case Selection"]
        CS --> EC["Evidence Capture<br/>photo · video · audio · notes"]
        EC --> H["SHA-256 Hashing"]
        H --> SP["Signed Evidence Package<br/>RSA-2048 signature"]
    end
    SP -->|"submit · POST /import/packages"| API["FastAPI Backend"]
    subgraph BACKEND["BACKEND"]
        direction TB
        API --> VF["Verification<br/>device · signature · integrity · replay"]
        VF --> SR["PostgreSQL + MinIO"]
        SR --> PROC["Evidence Processing"]
        PROC --> EX["Entity Extraction"]
        EX --> RES["Entity Resolution"]
        RES --> RD["Relationship Discovery"]
    end
    RD --> PROJ["Graph Projection"]
    PROJ --> NEO[("Neo4j")]
    NEO --> GA["Graph Analytics"]
    GA --> NI["Priorities · Communities · Network Intelligence"]
    NI --> WS["React Investigator Workspace + local AI panels"]
    WS --> FB["Evidence-backed Findings"]
    FB --> TL["Timeline + Audit Trail"]
```

---

## AI capabilities

Ten capabilities are implemented, each with a **published boundary** — what it does and what it
deliberately refuses to do. Full matrix with routes, panels, tests and measured evidence:
[`docs/ai/FEATURE_STATUS.md`](docs/ai/FEATURE_STATUS.md).

| # | Capability | Where it lives | Exact boundary |
|---|---|---|---|
| 1 | **Grounded AI assistant** — chat, streaming, report drafting, read-only tool loop | `POST /ai/chat`, `/ai/chat/stream`, `/ai/report-draft` · floating assistant | Tools are **read-only** (7 registry tools, no writes); case chat requires membership; answers stay chat, never become evidence |
| 2 | **Evidence ingestion copilot + chain of custody** | `…/evidence-intelligence/extract`, `…/evidence-integrity/verify`, `…/custody-audit` | Page-aware bounded extraction verified against the page text; custody rule set is **deterministic** (the model may explain a finding, never create or dismiss one); images without a text layer are refused with `OCR_REQUIRED` |
| 3 | **Entity resolution** | `…/evidence-intelligence/entity-resolution` | Produces a similarity **band** and candidate pairs — **never auto-merges**; merge is a human action with provenance |
| 4 | **Timeline reconstruction** | `…/timeline-reconstruction`, `…/timeline-proposals/{id}/commit` | Orders **source-anchored** timestamps only; **invented timestamps: 0** in golden checks; commit requires a human |
| 5 | **Contradiction detection** | `…/contradiction-detection`, `…/contradictions/{id}/resolve` | Anchored to source-record pairs; findings are **human-resolved only** |
| 6 | **Financial flow analysis** | `…/financial-flow`, `…/financial-flow/trace` | Computes only from financial fields present in records — **absent/non-numeric stays absent**; no unkeyed grand totals; traces walk verified edges only |
| 7 | **Cross-case linkage** | `POST /cross-case/discover`, `/cross-case/candidates` | Always runs over an **explicit scope of ≥2 cases** (never "all cases"); read-only discovery; approval records a reviewed relationship — **never merges cases** |
| 8 | **Multilingual complaint intelligence** | `…/evidence-intelligence/multilingual` | Language label is cross-checked against a deterministic **script profile**; originals never rewritten; unsupported scripts are typed 422 refusals with 0 artifacts |
| 9 | **Digital forensics triage** | `…/evidence-intelligence/triage` | Structural observations only — **no malware/phishing verdicts**, and **URLs found in evidence are never fetched** or executed |
| 10 | **AI report auditing** | `POST /cases/{id}/report-audits` | Draft kept as sha256 only (raw text not persisted); auditor **never edits or files the report** — approve/reject is a human decision in the audit log; artifacts are always `pending_review` + `flagged` |

### How every AI feature is bounded

```mermaid
sequenceDiagram
    autonumber
    participant U as Investigator
    participant A as FastAPI route
    participant E as Deterministic engine
    participant M as Local llama-server
    participant V as Verifier
    participant R as Artifact (pending_review)

    U->>A: press Run
    A->>A: re-check membership + permission
    A-->>U: 202 Accepted {job_id}
    A->>E: queue bounded job
    E->>E: parse · anchor · compute facts
    E->>M: bounded completion (text slice only)
    M-->>E: model output
    E->>V: verify against sources
    Note over V: ids/numbers checked<br/>fabrications rejected<br/>unsupported = typed refusal
    V->>R: write artifact + provenance
    U->>R: approve / reject (human, audited)
```

Five invariants hold for all ten capabilities — detailed with their diagrams in
[`docs/architecture/README.md`](docs/architecture/README.md):

1. **The LLM is never a source of truth** — deterministic engines compute; the model explains; every
   model-produced number or id is verified before it can render.
2. **The LLM cannot bypass authorization** — it holds no credentials and no route access; each
   request and each background job re-checks case membership itself.
3. **Nothing auto-applies** — AI output lands as a `pending_review` artifact; approval is human and
   audited.
4. **Failures are typed, never silent** — disabled, unavailable, refusal, verification mismatch and
   timeout each have a distinct code; an empty success is treated as a bug.
5. **Originals are immutable** — evidence bytes and source text are never rewritten.

### AI screenshot gallery

Every image below was captured from the running application (1440×900, light theme, English)
against the live backend and the local Qwen3-8B server. They can be regenerated from the real UI
with [`docs/scripts/capture_ai_screenshots.mjs`](docs/scripts/capture_ai_screenshots.mjs) — no
mocked or staged screens. Content is synthetic showcase data only.

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-assistant.png" width="100%" alt="AI assistant with a grounded, sourced answer"/><b>1 · Assistant (grounded)</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-extraction.png" width="100%" alt="Evidence ingestion copilot panel"/><b>2 · Ingestion copilot</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-custody.png" width="100%" alt="Integrity and chain-of-custody panel"/><b>2 · Custody audit</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-entity-resolution.png" width="100%" alt="Entity resolution candidate matches"/><b>3 · Entity resolution</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-timeline-reconstruction.png" width="100%" alt="Timeline reconstruction proposals"/><b>4 · Timeline</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-contradiction-detection.png" width="100%" alt="Contradiction detection candidates"/><b>5 · Contradictions</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-financial-flow.png" width="100%" alt="Financial flow analysis"/><b>6 · Financial flow</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-cross-case.png" width="100%" alt="Cross-case linkage candidates"/><b>7 · Cross-case</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-multilingual.png" width="100%" alt="Multilingual complaint intelligence"/><b>8 · Multilingual</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/ai-triage.png" width="100%" alt="Digital forensics triage observations"/><b>9 · Forensics triage</b></p></td>
<td width="33%" colspan="2"><p align="center"><img src="docs/screenshots/web/ai-report-audit.png" width="51%" alt="AI report auditing with claim findings"/><b>10 · Report auditing</b></p></td>
</tr>
</table>

<details>
<summary><b>What each capture needed</b></summary>

- **Synthetic demo data**: the showcase "Ponzi investment racket" case plus four small uploaded
  synthetic files — a mixed Hindi/English complaint, a URL-reference list on reserved
  `example.*` domains, a transaction-anchor CSV with a deliberately conflicting amount, and a
  name-only near-duplicate pair that survives ingest de-duplication — plus the same account
  number planted in a second authorized case for cross-case discovery, three recorded custody
  events, and the real AI jobs. All of it is submitted through the product's own API by the
  capture script; nothing is written directly into the database.
- **Live model required** for capabilities that generate: assistant answer, ingestion extraction,
  multilingual analysis, triage explanation, report audit. Deterministic capabilities
  (resolution, timeline, financial flow, cross-case) run without the model.
- **Not captured**: any screen that would require fabricated data. Where a panel has no data to
  show, it renders its honest empty state rather than a staged result.

</details>

---

## See it in action

Real screenshots from the running system — the seeded demo case, a physical-device E2E run, and the
live backend API. No mocked imagery.

### Android field agent

Captured on a physical device (RSA-2048 Android Keystore identity), in the order an officer uses it.

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/connect.png" width="50%" alt="Connect"/><br/><b>Connect</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/discover.png" width="50%" alt="LAN discovery"/><br/><b>Discover</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/enroll.png" width="50%" alt="Enroll"/><br/><b>Enroll</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/field-hub.png" width="50%" alt="Field hub"/><br/><b>Field hub</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/case.png" width="50%" alt="Select case"/><br/><b>Select case</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/capture.png" width="50%" alt="Capture"/><br/><b>Capture</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/android/evidence.png" width="50%" alt="Evidence details"/><br/><b>Evidence</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/offline.png" width="50%" alt="Offline field hub"/><br/><b>Offline</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/android/transfer.png" width="50%" alt="Transfer"/><br/><b>Transfer</b></p></td>
</tr>
</table>

### Web investigator

The integrated investigator workspace — light and dark themes, English / हिन्दी labels, a
Ctrl+K command palette, and a case tab strip that fits all twelve sections on one line at
desktop widths (with a subtle scroll strip on smaller screens). Every screen below was
captured from the running application against the live backend.

#### Workspace

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/dashboard.png" width="100%" alt="Dashboard"/><b>Dashboard</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/cases.png" width="100%" alt="Cases register"/><b>Cases</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/case.png" width="100%" alt="Case workspace with all twelve tabs visible on one line"/><b>Case · 12 tabs</b></p></td>
</tr>
</table>

#### Intelligence

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/entities.png" width="100%" alt="Entities"/><b>Entities</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/victims.png" width="100%" alt="Victims"/><b>Victims</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/hypotheses.png" width="100%" alt="Hypotheses"/><b>Hypotheses</b></p></td>
</tr>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/graph.png" width="100%" alt="Knowledge graph"/><b>Graph</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/analytics.png" width="100%" alt="Analytics"/><b>Analytics</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/findings.png" width="100%" alt="Findings"/><b>Findings</b></p></td>
</tr>
</table>

#### Evidence and reports

<table>
<tr>
<td width="33%"><p align="center"><img src="docs/screenshots/web/evidence.png" width="100%" alt="Evidence"/><b>Evidence</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/timeline.png" width="100%" alt="Timeline"/><b>Timeline</b></p></td>
<td width="33%"><p align="center"><img src="docs/screenshots/web/reports.png" width="100%" alt="Reports with a generated PDF"/><b>Reports (PDF ready)</b></p></td>
</tr>
</table>

#### Devices

<table>
<tr>
<td width="50%"><p align="center"><img src="docs/screenshots/web/devices.png" width="100%" alt="Field devices"/><b>Field devices</b></p></td>
<td width="50%"><p align="center"><img src="docs/screenshots/web/iot.png" width="100%" alt="IoT devices"/><b>IoT</b></p></td>
</tr>
</table>

#### Administration

<table>
<tr>
<td width="50%"><p align="center"><img src="docs/screenshots/web/audit.png" width="100%" alt="Audit log"/><b>Audit log</b></p></td>
<td width="50%"><p align="center"><img src="docs/screenshots/web/settings.png" width="100%" alt="Settings"/><b>Settings</b></p></td>
</tr>
</table>

#### Mobile

<table>
<tr>
<td width="50%"><p align="center"><img src="docs/screenshots/web/mobile-dashboard.png" width="60%" alt="Mobile dashboard"/><b>Dashboard · 390px</b></p></td>
<td width="50%"><p align="center"><img src="docs/screenshots/web/mobile-cases.png" width="60%" alt="Mobile cases"/><b>Cases · 390px</b></p></td>
</tr>
</table>

### Android → Backend → Web

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

## SIH showcase demo

A single coherent, fully synthetic case — **SIH-2026-001** ("SIH Showcase"
badge) with a clearly labeled support fixture **SIH-2026-002** ("Demo
fixture" badge) — drives all ten AI capabilities through the real
application workflows. Everything is seeded over the public API by an
idempotent script; nothing touches the database directly.

```bash
make demo-seed                                        # create/verify (safe to re-run)
make demo-status                                      # per-capability checklist
make demo-reset DEMO_RESET_CONFIRM=sih-showcase       # guarded destructive reset
```

- Re-running never duplicates: evidence dedupes by filename + sha-256, custody
  and timeline events by UTC instants, jobs by status, report audits by draft
  hash. A second run reports `43 existing, 1 skipped` and exits 0.
- With the model server down, AI-backed jobs (multilingual, triage text,
  report audit) are reported `failed` — then retried with
  `CS_SEED_RETRY_FAILED=1`; deterministic capabilities always run.
- The reset refuses without the confirmation phrase, refuses on
  `APP_ENV=production`, and deletes only the two SIH-2026-xxx cases.

Full scenario, per-capability walkthrough, expected numbers and known
limitations: **[docs/demo/SIH_SHOWCASE.md](docs/demo/SIH_SHOWCASE.md)** ·
data flow: [docs/architecture/sih-showcase-data-flow.md](docs/architecture/sih-showcase-data-flow.md)

---

## Architecture

Nine Mermaid diagrams — drawn from the implementation, each naming real modules and routes — live
in [`docs/architecture/`](docs/architecture/README.md):

```mermaid
flowchart TB
    AG["Android Field App"] -->|enroll · heartbeat · signed evidence| API["CyberSaarthi API<br/>FastAPI · REST"]
    UI["Investigator Web UI"] -->|Bearer JWT| API
    API --> PG[("PostgreSQL<br/>source of truth")]
    API --> MI[("MinIO<br/>evidence objects")]
    API --> RD[("Redis<br/>auth · revocation")]
    API --> NE[("Neo4j<br/>graph projection")]
    API -->|"bounded prompts, bearer key<br/>HTTP or UDS"| LLM["llama-server :8081<br/>Qwen3-8B Q4_K_M (local)"]
    LLM -.->|"no credentials · no route access"| API
```

| Store / process | Responsibility |
|---|---|
| **PostgreSQL** | Source of truth — users, cases, victims, entities, evidence metadata, artifacts, audit log |
| **Neo4j** | Idempotent graph projection + analytics (centrality, communities) |
| **MinIO** | Raw evidence objects (S3 API) |
| **Redis** | Token revocation denylist + login throttling — operational state, not a source of truth |
| **llama-server** | Local inference only (loopback/UDS + API key). It stores nothing and authorizes nothing |

Diagrams: [system](docs/architecture/system-architecture.md) ·
[AI request lifecycle](docs/architecture/ai-request-lifecycle.md) ·
[ingestion & custody](docs/architecture/evidence-ingestion-custody.md) ·
[entity & timeline](docs/architecture/entity-resolution-timeline.md) ·
[financial & cross-case](docs/architecture/financial-flow-cross-case.md) ·
[multilingual & triage](docs/architecture/multilingual-forensics.md) ·
[report audit](docs/architecture/report-audit.md) ·
[deployment](docs/architecture/deployment-setup.md)

<details>
<summary><b>Detailed data architecture</b></summary>

Entity types: `person`, `phone`, `vehicle`, `organization`, `account`, `location`, `document`,
`event` — linked by relationships such as `called`, `owns`, `located_at`, `visited`, `works_for`,
`associated_with`. All stores persist on named Docker volumes.

</details>

### Evidence → Intelligence

```mermaid
flowchart LR
    E["Raw Evidence"] --> A["Ingestion"] --> B["Parsing"] --> C["Entity Extraction"]
    C --> D["Normalization"] --> R["Entity Resolution"] --> X["Relationship Extraction"]
    X --> P["Graph Projection"] --> G["Centrality · Communities · Network Analysis"] --> F["Prioritized Findings"] --> I["Investigator"]
```

<details>
<summary><b>Evidence integrity pipeline</b></summary>

1. Upload computes a **SHA-256** fingerprint; byte-identical re-uploads are rejected (`409`).
2. Field packages re-verify the **RSA-2048 signature** against the enrolled device; packages from
   unapproved devices are rejected.
3. Raw objects land in **MinIO**, metadata in **PostgreSQL**, and every mutation is **audit-logged**.
4. Provenance links every finding to the evidence file and hashes that produced it.

</details>

---

## Technology stack

| Layer | Technology |
|---|---|
| API | FastAPI · Python 3.12 · SQLAlchemy 2 (async) · Alembic |
| Web | React 19 · TypeScript 5.7 · Vite · Tailwind CSS 4 · Radix UI · TanStack Query · Zustand |
| AI | llama.cpp (`llama-server`, CUDA build) · Qwen3-8B Q4_K_M GGUF · OpenAI-compatible local API |
| Data | PostgreSQL 16 · Neo4j 5 · Redis 7 · MinIO (S3) |
| Mobile | Kotlin · Jetpack Compose · Android Keystore (RSA-2048) |
| Ops | Docker Compose · Make · GitHub Actions CI |

---

## Quick start

### Prerequisites

```bash
./scripts/check_prereqs.sh     # read-only: reports exactly what is missing
```

| Requirement | Needed for | Notes |
|---|---|---|
| Docker + Compose v2 | backend, PostgreSQL, Neo4j, Redis, MinIO | daemon must be running |
| Node.js 22+ | web UI | `npm install` needs network |
| Python 3.12+ (host) | only if running migrations/seeds outside Docker | backend itself runs in the container |
| ~6 GiB free disk | stack + AI model | model alone is ~4.7 GiB |
| NVIDIA GPU (optional) | faster AI features | CPU works but is slow; see [LOCAL_MODEL_SETUP](docs/ai/LOCAL_MODEL_SETUP.md) |

**Network is required for setup, not for operation.** `git clone`, Docker image pulls,
`npm install`, `./scripts/ai/setup_runtime.sh` (llama.cpp binaries, ~730 MB) and
`./scripts/ai/setup_model.sh` (model weights, ~4.7 GiB) all download things once. After setup the
stack runs fully locally: inference is on your machine, and the application code makes **no cloud
LLM calls** — no Ollama, no remote inference endpoints, nothing to configure or pay for.

### Backend + data services

```bash
git clone https://github.com/0xhroot/cybersaarthi.git && cd cybersaarthi
cp .env.example .env                                  # dev-safe defaults; never overwritten by scripts
docker compose up -d --build                          # postgres · neo4j · redis · minio · backend
docker compose exec -T backend python -m scripts.create_admin   # first admin (idempotent)
docker compose exec -T backend python -m scripts.seed_demo      # demo case (idempotent)
```

The backend container runs `alembic upgrade head` on start, so migrations are applied
automatically. `make up`, `make seed`, `make admin` and `make test` are equivalent shortcuts.

### Local AI runtime (the model)

AI features degrade to typed `503 AI_UNAVAILABLE` responses until the runtime is up — nothing else
breaks. To enable them:

```bash
# 1. the model (~4.7 GiB, one time, ONLY if you don't have it yet)
./scripts/ai/setup_model.sh        # official Qwen/Qwen3-8B-GGUF source + SHA-256 verification

# 2. llama.cpp server binaries (~730 MB, one time)
./scripts/ai/setup_runtime.sh

# 3. a shared secret for the inference server (one time)
printf '\nAI_SERVER_API_KEY=%s\n' "$(openssl rand -hex 32)" >> .env

# 4. start the server + socket bridge, then recreate the backend so it sees them
set -a && . ./.env && set +a
setsid -f bash -c 'exec ./scripts/ai/run_server.sh'   > /tmp/llama-server.log 2>&1 < /dev/null
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' > /tmp/llama-bridge.log 2>&1 < /dev/null
docker compose up -d backend                          # RECREATED, not just restarted

# 5. prove it works end to end (GGUF magic → health → real completion → GPU)
./scripts/ai/verify_model.sh
```

> The model file is **not in this repository** (5 GB; GitHub LFS caps files at 2 GB on the free
> plan). `setup_model.sh` fetches it from the official Qwen repository and verifies the SHA-256
> recorded by that repository (`d98cdcbd…5785`, 5 027 783 488 bytes, Apache-2.0) before it can be
> used. No other step downloads it — not `docker compose up`, not install, not tests. A
> pre-existing file is verified, never silently replaced.

Full configuration reference, verification ladder and failure modes:
[`docs/ai/LOCAL_MODEL_SETUP.md`](docs/ai/LOCAL_MODEL_SETUP.md) ·
[`docs/ai/TROUBLESHOOTING.md`](docs/ai/TROUBLESHOOTING.md).

### Frontend

```bash
cd frontend && npm install && npm run dev             # → http://localhost:5173
```

### Health checks

```bash
./scripts/healthcheck.sh                              # stack · backend · readiness · AI · frontend

curl http://localhost:8000/api/v1/health              # liveness  → 200
curl http://localhost:8000/api/v1/ready               # readiness (database) → 200
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/ai/status           # AI runtime: ready / model_valid / tools
```

Backend API `http://localhost:8000` · Swagger `http://localhost:8000/docs` · web
`http://localhost:5173`.

Android agent: `gradle assembleDebug` from `mobile/`, then **Connect → Enroll → Approve** in the web
**Devices** tab — see [`mobile/README.md`](mobile/README.md).

---

## Tests & evaluation

| Gate | Command | Count / result |
|---|---|---|
| Backend lint · format · types | `make lint` · `make format-check` · `make typecheck` (ruff, mypy) | clean |
| Backend tests | `make test-unit` / `make test` (pytest) | **1048 passed** |
| Frontend tests | `cd frontend && npm test` | **224 passed** |
| Frontend lint · types · build | `npm run lint` · `npm run typecheck` · `npm run build` | clean |
| Migrations | `alembic check` | head `c5e2b8f4d9a3`, no pending changes |
| AI evaluation harness | `./scripts/ai/eval_final.sh --report <path>` | **147/147 gates**, ~213 s |
| CI | `.github/workflows/ci.yml` (backend + frontend jobs) | runs on every push/PR |

The evaluation harness is a **gate**, not a demo: it fails non-zero if any golden check regresses,
and it includes live checks against the local model (fact recall, groundedness, abstention,
fabrication refusal, per-feature `n=` samples). Re-run it after any AI-related change. The seven
live-model backend integration tests (`tests/integration/test_ai_live.py`) require the local AI
server from the quick start; without it they skip, and the suite reports 1041 passed + 7 skipped.

<details>
<summary><b>Historical verification notes</b></summary>

An earlier browser audit covered 24/24 checks across 15 workspace screens at 1440×900 and 390×844;
PDF/JSON/CSV report generation was verified end to end through the UI; Android unit tests and lint
pass. See [`docs/`](docs/README.md) for dated reports.

</details>

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

Every device presents a canonical fingerprint — **SHA-256 over the SubjectPublicKeyInfo DER bytes** of
its key — at enrollment; only **approved** devices may submit packages, and every accept/reject is
recorded.

<details>
<summary><b>Detailed security model</b></summary>

| Control | Implementation |
|---|---|
| Password hashing | bcrypt + minimum length |
| Authentication | JWT with expiry; `jti` denylist in Redis |
| Authorization | RBAC — ADMIN / INVESTIGATOR / ANALYST / VIEWER |
| Isolation | owner/admin checks + per-case IDOR guards |
| Rate limiting | keyed login throttling with exponential lockout |
| Input validation | size caps, format sniffing, strict error envelope, Cypher label allowlist |
| Field-agent trust | canonical fingerprint cross-check · approve/revoke · per-device key verification |
| AI isolation | per-request authz re-check, owner-scoped threads, read-only model tools, prompt-injection fencing, per-user rate limits — see [`docs/ai/SECURITY_AND_ISOLATION.md`](docs/ai/SECURITY_AND_ISOLATION.md) |
| Audit | append-only, permission-scoped (`audit.read`) |

</details>

Report a vulnerability: [`SECURITY.md`](SECURITY.md).

---

## Limitations and honest boundaries

Stated up front rather than discovered later:

- **No OCR** — image-only PDFs are refused with `OCR_REQUIRED`; text-layer PDFs and csv/json/txt are
  supported.
- **No `.eml`/MIME parsing** — mailbox files are not ingested.
- **Devanagari Hindi vs Marathi ambiguity** is flagged for review, never hidden; translation quality
  is measured only as material-value preservation (no BLEU/human-quality claim).
- **Triage issues no malware/phishing verdicts** and never fetches the URLs it finds in evidence.
- **Report auditing covers draft text only**; it does not read filed PDFs.
- **Managed llama-server mode (`AI_MANAGE_SERVER=true`) is code-verified but not the live path** in
  this deployment (the host process is authoritative because the container has no GPU); GPU metrics
  report `null` inside the container instead of being invented.
- **CPU-only works but is slow** — measured performance numbers come from an RTX 3080; treat CPU
  throughput as unmeasured.
- **"Soup" fine-tuning** remains an external blocker (no Soup repository on this machine) — see
  [`docs/ai/EVALUATION.md`](docs/ai/EVALUATION.md).
- **Excluded by design**: cloud inference and Ollama — no code path exists for either.

Full list with evidence: [`docs/ai/FEATURE_STATUS.md`](docs/ai/FEATURE_STATUS.md) (§G).

---

## Documentation map

| Start here | Contents |
|---|---|
| [`docs/README.md`](docs/README.md) | Full documentation index |
| [`docs/architecture/README.md`](docs/architecture/README.md) | The eight architecture diagrams + system invariants |
| [`docs/ai/FEATURE_STATUS.md`](docs/ai/FEATURE_STATUS.md) | Ten-capability matrix with exact boundaries and evidence |
| [`docs/ai/LOCAL_MODEL_SETUP.md`](docs/ai/LOCAL_MODEL_SETUP.md) | Model acquisition, runtime, configuration, verification ladder |
| [`docs/ai/EVALUATION.md`](docs/ai/EVALUATION.md) | Evaluation gates and how to re-run them |
| [`docs/ai/TROUBLESHOOTING.md`](docs/ai/TROUBLESHOOTING.md) | Failure modes and fixes |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute |

---

## Contributing · License

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

<div align="center">

**Connect the evidence. Understand the network. Recover the truth.**

Built with **FastAPI · React · PostgreSQL · Neo4j · MinIO · Redis · Android · Docker · llama.cpp**.

Released under the [MIT License](LICENSE). Copyright © 2026 0xhroot.

</div>

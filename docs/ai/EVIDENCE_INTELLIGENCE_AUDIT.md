# Evidence Intelligence Audit — Phase 0

**Date:** 2026-10-16
**HEAD at audit:** `ca0ba9f` (main)
**Method:** read-only repository inspection (git history, backend/frontend source, migrations, eval harness, docs) before any feature code.

---

## 0. Ground truth: prior completion claims

The master implementation prompt requires verifying actual state rather than trusting
completion reports — including earlier reports from this project's own history.

| Check | Result |
|---|---|
| `git log --all --grep="feat(ai)"` and `--grep="evidence intelligence"` | **zero matches** — no feature commits exist anywhere |
| `docs/ai/EVIDENCE_INTELLIGENCE_AUDIT.md` | **did not exist** (this document is its creation) |
| Backend modules for the 10 features (entity resolution, contradiction, financial flow, cross-case, multilingual, forensics, custody, report auditor) | **0 files** matching each keyword under `backend/app` |
| Frontend matches for the 10 feature names (Evidence Intelligence, Entity Resolution, Financial Flow, Cross-Case, Multilingual, Forensics, Chain of Custody, Report Auditor, Timeline Reconstruction) | **0 files** under `frontend/src` |
| Branches/stashes hiding feature work | only `main` (+ remotes); no stashes |

**Conclusion: none of the 10 features are implemented.** The commit chain
`6becdf4` → `45a8767` → `b156f87` → `3591005` → `d452a67` is a *different* AI
expansion (Think mode, Analysis-page AI, Hypotheses-page AI, eval gates, quality
gates) — useful, reusable infrastructure, but not this task. Any earlier status
report describing the 10 features as "delivered" was wrong; this audit replaces it.

---

## 1. Existing reusable foundation (verified)

### 1.1 Evidence pipeline and provenance

| Component | File | What it really does |
|---|---|---|
| `EvidenceFile` | `backend/app/models/evidence_file.py` | Uploaded file in MinIO (`stored_key`), `sha256`, unique `(case_id, sha256)` (duplicate-upload detection), `content_type`, `file_size`, `format`, `encoding`, `record_count`, soft-delete `deleted_at`, status `stored/parsed/processing/failed` |
| `SourceRecord` | `backend/app/models/source_record.py` | One parsed record: `record_no` (unique per file), `raw_data` + `normalized_data` JSONB, `entity_mentions`, `relationships_data`, status `parsed/normalized/extracted/resolved/failed` — **the provenance anchor citations must point at** |
| `IngestionJob` | `backend/app/models/ingestion_job.py` | Job lifecycle: status `pending/running/completed/failed/partial`, `stage`, `progress`, `total_records`, `processed_records`, `error`, `summary` JSONB, unique `(case_id, evidence_file_id)` (idempotency), `started_at/completed_at` |
| Parsing | `backend/app/services/parsing.py` | `parse(data, format, encoding)` — **CSV, JSON, TXT only** (`EvidenceFormat` in `app/core/enums.py:54`); returns list of record dicts; raises `ParseError` |
| Pipeline services | `backend/app/services/{ingestion,extraction,normalization,validation,provenance}.py` | Real upload→parse→normalize→extract→validate flow with provenance capture; `package_verification.py` verifies import-package hashes |
| Audit | `backend/app/services/audit.py` | `record_audit(...)` — append-only; "entries are never edited or deleted by application code" |

**Implication for Feature 1:** upload, hashing, duplicate detection, record parsing,
provenance and job tracking are reusable. Missing: LLM structured extraction with
field-level source locators, extraction-preview/review workflow, format breadth
(§2), and evidence-intelligence frontend.

### 1.2 Entity and relationship layer

- Models: `entity.py`, `entity_alias.py`, `entity_candidate.py`, `entity_match.py`,
  `relationship.py`, `relationship_evidence.py`. `EntityStatus` includes
  `review`/`merged`; `ResolutionDecision` = `auto_match | review | no_match`.
- Services: `resolution.py` (blocking/candidate generation + scoring) and
  `resolve_review.py` (audited approve/reject review decisions) — **the audited
  merge workflow Feature 2 must reuse already exists**.
- Matching deps: `rapidfuzz==3.14.5` (fuzzy), `spacy` + `en_core_web_sm`
  (English NER only — **not** Marathi/Hindi).
- Graph: `graph_sync.py` pushes entities/relationships to Neo4j;
  `RelationshipType` already includes `transferred_to`.

**Implication for Feature 2:** deterministic normalization, blocking, candidate
storage and review decisions exist backend-side. Gaps: LLM-assisted comparison for
ambiguous pairs, transparent signal breakdown API, dedicated frontend candidate
review UI (0 frontend matches).

### 1.3 Timeline, findings, hypotheses, reports

- `TimelineEvent` (`timeline_event.py`): `occurred_at` (semantic, tz-aware) vs
  `created_at`; 18 event kinds incl. analyst `case_event`; links to evidence/
  entity/collection/device; `services/timeline.record_event(...)` writes events.
  Gaps for Feature 3: **proposed**-event records, approval flow, tz preservation
  through extraction, duplicate/conflict detection.
- `Finding` (`finding.py`): type `pattern/anomaly/hypothesis/network_insight/
  relationship_insight`, severity, status `NEW/REVIEWED/DISMISSED/CONFIRMED`,
  `confidence`, `affected_entities/relationships` JSONB, `run_id` → analytics run —
  the review-state pattern Feature 4 should follow.
- `Report` (`report.py`) is an **export artifact only** (status
  `generating/ready/failed`; json/csv/pdf built by `reporting.py` via `fpdf2`).
- AI report drafting: `ai/service.py:449 draft_report()` → chat turn
  (`mode="report"`, `profile="deep"`) persisted only as chat messages.
  **No versioned, immutable draft entity exists** — Feature 10 needs one.

### 1.4 Local AI gateway (reuse as-is)

- `ai/client.py` — httpx OpenAI-compatible client to llama.cpp (`/v1`,
  chat + streaming); `ai/runtime.py` — server supervision, health probes, metrics;
  `ai/service.py` — orchestrator with profiles **quick/standard/deep** (think mode
  = deep), rate limiting, bounded tool loop, SSE, retention sweep, modes
  `chat/analysis/hypothesize/report` with server-side claim checks;
  `ai/tools.py:403 TOOLS` — **read-only allowlist** with audited dispatch
  (`search_cases`, `get_case_summary`, …); `ai/prompts.py` — `PROMPT_VERSION =
  "1.0.0"`; `ai/retrieval.py` — builds **authorized DATA blocks server-side** and
  provides `validate_cited_claims()` — **the existing citation validator Feature 10
  extends**.
- Endpoints (`api/routes/ai.py`): `GET /status`, conversations CRUD,
  `POST /chat`, `POST /chat/stream`, `POST /report-draft`.
- Model reality: local llama.cpp, Qwen3-8B Q4_K_M, **text-only GGUF** (no vision),
  8k context budget, `temperature=0.2` forced server-side (EVALUATION.md).
  No Ollama, no cloud — unchanged by this task.

### 1.5 Evaluation harness (extend, don't replace)

- `scripts/eval_model.py` + `scripts/eval_model.sh`; 41 frozen golden entries in
  `backend/tests/fixtures/ai_golden.jsonl`.
- **Five hard gates** (exit 0 only if all pass): abstention = 100 %, exact refusal
  status on unauthorized/invalid asks, server-side claim check passes, citation
  wording rule, ≥1 hypothesize entry all passing. Current record: **41/41**,
  groundedness 1260/1260 cited sources; one run per entry (documented, not a
  statistical claim).
- Feature evals must be added as new fixture entries/gates in this harness (§6).

### 1.6 Authorization and audit boundaries

- FastAPI dependency chain on every route: current user → org/tenant scope
  (`org_id`) → case membership role (`case_members`: viewer/investigator/admin) →
  admin gates. Cross-case work must loop this check **per case** (§4).
- Audit trail is append-only (`record_audit`); cascade only `SET NULL` on FKs.
- Untrusted text (evidence content) enters prompts only inside retrieval-built
  DATA blocks with citation requirements; the model has **no** SQL/shell/HTTP
  tools — only the `TOOLS` allowlist.

### 1.7 Frontend

- Router: `frontend/src/app/router.tsx`, `AppShell` + `RequireAuth` /
  `RequirePermission`; pages in `frontend/src/app/pages/`: `evidence`, `entities`,
  `entity-detail`, `graph`, `timeline`, `analytics`, `hypotheses`, `reports`,
  `findings`, `finding-detail`, `cases`, `case-overview`, `audit`, `settings`,
  `dashboard`, `devices`, `victims`, `iot-*`, `admin-users`.
- AI components under `frontend/src/components/ai/` (chat copilot, analysis panel).
- Gates: `npm run test` (127 tests), `npm run typecheck`, `npm run lint`.

### 1.8 Background jobs — explicit limitation

**No durable queue exists** (no arq/celery/rq/dramatiq anywhere in `backend/app`).
`IngestionJob` is a database status record; work runs in-process. Per the master
prompt's "smallest reliable solution": analysis jobs will reuse the
`IngestionJob` pattern (new status columns/records, unique idempotency keys,
progress updates, cooperative cancellation, timeouts, bounded concurrency)
and document the durability limitation (jobs lost on process restart are
re-runnable via idempotency keys).

---

## 2. Gap analysis per feature

| # | Feature | Exists | Must be built | Blocked / limited by data |
|---|---|---|---|---|
| 1 | Smart Evidence Ingestion Copilot | upload, sha256, dup check, CSV/JSON/TXT parse, `IngestionJob`, provenance | LLM structured extraction w/ field-level source locators, schema validation of model output, extraction preview + approve/edit/reject, retry/cancel | **PDF**: `pypdf` only in dev extras — promote to runtime dep (already installed). **Images/OCR**: no tesseract, model is text-only → not supported, document. **Email/office**: no parsers → not supported, document |
| 2 | AI Entity Resolution | entity/candidate/match models, blocking in `resolution.py`, audited `resolve_review.py` | LLM-assisted ambiguous-pair comparison, transparent signal/conflict breakdown API, frontend candidate-review UI | name-only pairs must stay `review`, never auto-merge |
| 3 | Timeline Reconstruction | `TimelineEvent`, `record_event`, tz-aware `occurred_at` | proposed-event table + review/approve flow, extraction from records & evidence text, tz/original preservation, duplicate & conflict detection, frontend review view | date-less sources must not invent dates |
| 4 | Contradiction Detection | nothing (0 matches) | claim model + comparable claim types, deterministic compare (amounts/dates/ids), LLM semantic compare, alternative-explanation rules, review states, frontend side-by-side view | — |
| 5 | Financial Flow Intelligence | `transferred_to` relationships, `Finding` review pattern, analytics engine, source_records with numeric fields | **transaction extraction/normalization layer** (there is **no transaction model** — only `victim.reported_amount/amount_lost/recovery_amount`), deterministic totals/net flows with decimal precision, bounded path analysis on Neo4j, missing-link display, frontend flow view | requires transaction-shaped evidence (CSV/JSON); without it the feature reports "no data" honestly |
| 6 | Cross-Case Pattern Discovery | per-case authz deps, audit service, entities with org scoping | explicit cross-case permission, visible-case scope computation, indexed candidate generation over permitted scope only, candidate records + review, per-case recheck, no-existence-leak guarantees, frontend candidates view | must never reveal unauthorized case existence |
| 7 | Multilingual Complaint Intelligence | `charset-normalizer`, complaint intake via evidence upload, spacy (English) | deterministic language detection (script/charset heuristics + model assist), original-preserving translate-on-request flow, strict field extraction w/ validation against original, ambiguity flags, synthetic Marathi/Hindi/English fixtures, frontend intake view | **no translation component**; Qwen3-8B multilingual quality must be *measured* before any capability claim; no langdetect dep |
| 8 | Digital Forensics Triage Copilot | evidence upload + validation, audit | deterministic artifact parsers (email headers, URLs/domains, hash manifests, log lines — pure Python), indicator extraction, observations-vs-interpretations separation, rule checks, frontend triage view | no attachment/script/URL execution ever; no shell tools |
| 9 | Evidence Integrity & Chain-of-Custody Auditor | `evidence_file.sha256`, MinIO bytes, `audit_log`, `record_audit` | **custody event model + requirements rules** (0 `custody` matches today), hash re-verification against stored bytes, gap/chronology checks, findings with rule versions, frontend integrity view | hash mismatch ≠ proven tampering; missing records ≠ misconduct |
| 10 | AI Report Auditor | `validate_cited_claims()`, report exports, chat drafts | versioned draft snapshot model, claim extraction into structured records, citation-support validation (not mere ID existence), numerical/date checks, counter-evidence flags, prioritized findings, frontend "Audit Report" action | drafts currently live only in chat — snapshot-at-audit is required first |

---

## 3. Shared layer to build first (Phase 1)

Everything below is consumed by ≥2 features:

1. **Derived artifact model** — `evidence_intelligence` records with provenance
   (case_id, evidence_id, source_record locator, content hash, run id,
   parser/model + `PROMPT_VERSION`, validation/review status, parent links,
   authorization scope) — never overwriting originals.
2. **Structured extraction pipeline** — strict pydantic schema output → validate
   → check ids/amounts/dates against source bytes/records → reject or flag
   uncertain → store with provenance + errors.
3. **Citation validator extension** — generalize `retrieval.validate_cited_claims()`
   to check record existence + access + case scope + quoted-value equality for all
   features, not just chat.
4. **Analysis job layer** — `IngestionJob`-pattern records with progress,
   cancellation, timeout, retry limit, idempotency (§1.8).
5. **Review/human-in-the-loop primitives** — reuse `resolve_review` +
   `Finding.status` patterns for merges, timeline proposals, contradictions,
   cross-case candidates, custody findings, report audits.
6. **Audit + feature flags** — `record_audit` for every sensitive operation;
   settings toggles following `AI_FEATURE_*` convention.
7. **Eval fixture scaffolding** — one fixture file per feature in the existing
   harness, positive + negative + injection cases, anti-vacuous assertions.

## 4. Authorization rules (all features)

- Authorize **before** retrieval for every prompt; re-derive scope per request
  (never trust cached scope when membership changed).
- Cross-case: require an explicit permission, check membership **per case in the
  loop**, and query only cases the principal can see; failed checks reveal nothing.
- Merges, hypothesis acceptance, evidence changes, report approval → human review
  + audit record; LLM may propose, never execute.
- Imported text is untrusted: prompts only receive retrieval-built DATA blocks;
  injection attempts are eval-gated.

## 5. Model and hardware constraints

- Local llama.cpp + Qwen3-8B Q4_K_M only; text-only (no vision/OCR capability);
  8k ctx → batch long documents in bounded sections; budgets/timeouts/concurrency
  already in `settings`/`service.py` — do not raise without measurement.
- On inference outage: deterministic paths keep working; AI endpoints fail loudly.

## 6. Implementation order and commits (per master prompt)

| Phase | Content | Commit message |
|---|---|---|
| 0 | This audit | `docs(ai): add evidence intelligence audit (phase 0)` |
| 1 | Shared Evidence Intelligence Layer (§3) + fixtures scaffolding | `feat(ai): add evidence intelligence foundation` |
| 2 | Feature 1 ingestion copilot + Feature 9 custody auditor | `feat(ai): add evidence ingestion and custody auditing` |
| 3 | Features 2, 3, 4 (entity resolution, timeline, contradiction) | `feat(ai): add entity resolution timeline and contradiction detection` |
| 4 | Features 5, 6 (financial flow, cross-case) | `feat(ai): add financial flow and cross-case intelligence` |
| 5 | Features 7, 8 (multilingual, forensics triage) | `feat(ai): add multilingual and digital forensics intelligence` |
| 6 | Feature 10 (report auditor) | `feat(ai): add report auditing` |
| 7 | Integration, eval fixtures for all 10, final verification | `test(ai): validate evidence intelligence integration` |

Each phase: backend + frontend + focused tests + `ruff` + `mypy` + diff inspection
→ commit only when green. No secrets, no unrelated files in any commit.

**Per-feature measurement plan** (added in Phase 7 fixtures): extraction
precision/recall; entity precision/recall/false-merge; timeline & timestamp
correctness; contradiction precision/false-positive rate; financial numerical
correctness; cross-case match quality + authorization denials; multilingual
translation-vs-extraction scored separately; forensic parsing & source accuracy;
custody hash/rule accuracy; report claim-support & citation accuracy. Positive,
negative, empty, malformed-output, injection and cross-tenant cases per feature —
with assertions that the intended code path actually ran (no vacuous passes).
Accuracy claims only from these documented fixtures; no invented percentages.

---

## 7. Phase status (records appended as phases complete)

### Phase 0 — Audit ✓ (`009c9ce`)
Ground-truth audit created (this document): verified no feature work pre-existed,
mapped reusable foundation, gaps, authorization rules and the 7-phase order.

### Phase 1 — Shared Evidence Intelligence Layer ✓ (this session)
**Delivered (backend foundation):**

| Piece | File |
|---|---|
| `AnalysisJob` model (status/feature/progress/cancel/timeout, unique `(case_id, idempotency_key)`) | `backend/app/models/analysis_job.py` |
| `DerivedArtifact` model (provenance columns, unique `(case_id, kind, content_hash)`) | `backend/app/models/derived_artifact.py` |
| Migration `a9b8c7d6e5f4` (both tables + indexes/checks; head verified) | `backend/migrations/versions/` |
| Structured-extraction validation: JSON recovery, strict schema (unknown fields/type errors reject), source field checks (exact `Decimal` numbers, normalized dates, locator checks), canonical sha256 | `backend/app/services/structured_extraction.py` |
| Analysis job state machine + idempotent create/scoped list; canceled can never succeed | `backend/app/services/analysis_jobs.py` |
| Artifact recording (content-addressed idempotency), guarded one-shot review, scoped list | `backend/app/services/artifacts.py` |
| Citation validator: shape/existence/case-scope/locator/quote-equality + per-call `case_visible_to` cross-case recheck | `backend/app/services/citations.py` |
| API: `GET .../evidence-intelligence/artifacts`, `GET .../evidence-intelligence/jobs`, `POST .../artifacts/{id}/review` (RBAC + read-only-case guard + audit) | `backend/app/api/routes/evidence_intelligence.py` |
| Contracts + error codes (`INVALID_FILTER`, `ARTIFACT_NOT_FOUND`, `ARTIFACT_NOT_REVIEWABLE`) | `backend/app/schemas/evidence_intelligence.py`, `app/core/codes.py` |
| Eval fixture scaffolding (10 extraction cases: positive/negative/injection) | `backend/tests/fixtures/evidence_intelligence/extraction_checks.json` |

**Measured (Phase 1 validation run, 2026-10-16):**
- Alembic: `c8e2f4a6b1d3 → a9b8c7d6e5f4 (head)` applied clean.
- Backend hermetic battery: **701 passed / 8 deselected, exit 0** (638 prior + **63 new**: 44 unit, 13 API, 6 DB-backed citation tests).
- Integration battery: **8 passed** (live llama-server path unchanged).
- `ruff check .`: **0**; `mypy app/`: **0** (150 files); `mypy scripts/eval_model.py`: **0**.
- API matrix verified: anonymous **401**, non-member **403**, member **200** with provenance fields; review is one-shot (**409** on second decision), viewer **403**, closed case **409**.

**Notes:** frontend panel arrives with Feature 1 (Phase 2) — the foundation has no
user-facing workflow of its own to integrate yet; eval-gate wiring for all 10
features lands in Phase 7. Next: **Phase 2** (Feature 1 ingestion copilot +
Feature 9 custody auditor).

### Phase 2 — Feature 1 ingestion copilot + Feature 9 custody auditor ✓ (this session)

**Delivered (backend):**

| Piece | File |
|---|---|
| PDF/text extraction service: lazy pypdf, page-aware bounded extraction (25 pages/unit, 10 units/file, 120k chars), OCR-required refusal, encrypted-PDF refusal, format allow-list | `backend/app/services/evidence_extraction.py` |
| Extraction pipeline: prompt/schema v1, structured-output validation (exact `Decimal`, normalized dates, per-claim source locator), one active job per evidence (`EXTRACTION_ACTIVE`), idempotent retry reusing reviewed-eligible records, cancel/timeout end as `canceled`/`failed` never `succeeded` | same + `app/ai/prompts.py`, `app/schemas/evidence_extraction.py` |
| Integrity verification: deterministic sha256 re-hash vs recorded digest (`match`/`mismatch`/`missing_expected`/`missing_source`/`unsupported_algorithm`), fact artifact recorded per run | `backend/app/services/integrity.py` |
| Custody: append-only `EvidenceCustodyEvent` model + policy validation (10 event types, required parties per type, tz-aware + skew-bounded `occurred_at`, optional 64-hex digest) | `backend/app/models/evidence_custody_event.py`, `app/services/custody.py` |
| Custody rule engine v1.0.0 (documented semantics: `unacknowledged_transfer`, `chronology_anomaly`, `orphaned_event`, `digest_mismatch`; no fixed universal sequence, optional fields never trigger findings) | `app/services/custody.py` |
| Migration `c5e2b8f4d9a3` (custody events table; head verified) | `backend/migrations/versions/` |
| API: `POST .../evidence-intelligence/extract`, `POST .../jobs/{id}/cancel`, `POST .../evidence-integrity/verify`, `POST .../evidence-integrity/custody-audit`, `GET .../evidence/{id}/custody`, `POST .../evidence/{id}/custody-events`, `POST .../artifacts/{id}/explain` (RBAC per action, case-scope + authz recheck before retrieval and model context, audit on every mutation) | `app/api/routes/evidence_intelligence.py`, `app/api/routes/evidence_integrity.py` |
| Explain = facts-only narration; stored artifact always `validation_status "flagged"` + `ai_unverified` error; model certifies nothing | `app/services/custody.py` |
| Eval harness + fixtures: 10 deterministic ingestion cases, 14 custody cases, 3 live cases (hash match/tamper/delete); gates on locator accuracy, hash correctness, custody rule agreement + zero false positives | `backend/scripts/eval_evidence.py`, `tests/fixtures/evidence_intelligence/`, `scripts/ai/eval_evidence.sh` |

**Delivered (frontend, Increment C):** domain types + contract/real/mock/parity for
`extract`, `evidenceJobs`, `cancelJob`, `artifacts`, `reviewArtifact`,
`verifyIntegrity`, `custodyAudit`, `custodyChronology`, `recordCustodyEvent`,
`explainFinding`; React Query hooks; evidence-page drawer panels
(`components/evidence/extraction-panel.tsx`, `integrity-panel.tsx`) with honest
status rendering (mismatch red, cannot-verify amber, only `match` green;
flagged fields listed, never hidden; AI narration labelled unverified; PDF in
the upload accept-list).

**Measured (Phase 2 validation run, 2026-10-17):**
- Alembic: `a9b8c7d6e5f4 → c5e2b8f4d9a3 (head)` applied clean.
- Backend hermetic battery: **788 passed / 8 deselected, exit 0** (701 prior + **87 new**: 47 unit, 32 API, 8 eval-fixture).
- Integration battery: live llama-server path **1 passed / 7 skipped** when the
  local server is down (skips are the pre-existing honest-skip guard, not
  failures); with the server up the AI-live tests run as in Phase 1.
- `ruff check .`: **0**; `mypy app/ + scripts/eval_evidence.py`: **0** (159 files).
- Frontend: **132 passed** (127 prior + 5 mock-adapter Phase 2 tests), `typecheck` 0, `lint` 0.
- Live eval (real Qwen3-8B-Q4_K_M, 3 synthetic cases): claim recall **12/13 (92%)**,
  extraction precision **21/22 (95%)**, field-level validation **59/60**,
  unsupported-claim rate **1/22 (5%, flagged not accepted)**, schema-invalid
  artifacts **0**, locator violations **0** (gated). Hash verification **3/3**
  (match / tampered→mismatch / deleted→missing_source, harness re-hash agrees).
  Custody: rule agreement exact (`custody.unacknowledged_transfer`), zero false
  positives on the clean chain; job wall time ~2-3 s per case. Harness cleanup
  verified: synthetic case + all objects removed.
- API matrix: viewer 403 on extract/cancel/verify/audit; stranger-investigator
  403 CASE_ACCESS_DENIED; recorded custody event refused for tz-less/future
  timestamps, missing required parties, malformed digest (422 typed codes);
  explain refused for hash facts (`ARTIFACT_KIND_UNSUPPORTED`); canceled job
  listed as `canceled` with `cancel_requested=true`.

**Limitations (honest):** no OCR engine installed — scanned/image PDFs are
refused with `EXTRACTION_PARSE_FAILED`/unsupported notice rather than silently
zero-yielded; PDF extraction covers text-layer PDFs only (pypdf); the 92% live
recall is the local model on a 3-case synthetic set, not a general accuracy
claim; custody rule v1 documents its semantics and does not assume any fixed
universal event sequence.

## 8. Phase 2 design (Feature 1 ingestion copilot + Feature 9 custody auditor)

### 8.1 Pre-implementation audit findings (verified 2026-10-16)

- HEAD `656d157`, clean tree, alembic head `a9b8c7d6e5f4` applied; pypdf 6.20.0
  importable (currently a dev-only dependency); **no OCR engine installed**.
- `EvidenceFormat` = csv/json/txt only; `sniff_format` rejects `%PDF-` uploads
  today. `evidence_files.format` has no DB check constraint → adding `pdf` needs
  no constraint change. `EVIDENCE_MAX_SIZE_BYTES = 5 MiB`.
- **No chain-of-custody event model exists** (only Phase 1 vocabulary
  constants). The provenance endpoint shows file→record→relationship lineage;
  audit_log (`evidence.uploaded|deleted|restored`) is the only real custody
  history. → a genuine `evidence_custody_events` migration is required; nothing
  may be back-filled.
- Reuse seams confirmed: upload pipeline (`fingerprint` → MinIO → row → audit),
  `storage.download`/`exists`, ingestion record creation
  (`create_source_record`, unique `(evidence_file_id, record_no)`),
  FastAPI `BackgroundTasks` async-ingest pattern, `request.app.state.ai_service`,
  `AIClient.chat` + `_generation_semaphore`, `fence_data` prompt-injection
  fencing, Phase 1 `AnalysisJob`/`DerivedArtifact`/validation services.

### 8.2 Feature 1 — Smart Evidence Ingestion Copilot

- **PDF support extends the existing pipeline**: `EvidenceFormat.PDF`, magic +
  `.pdf` detection, `parsing._parse_pdf` (pypdf) → one source record per page
  (`{"page": n, "text": ...}`); page cap + per-page char cap; **no text layer →
  explicit ParseError ("OCR required, not available") — never invented content**.
- Extraction schema `EvidenceExtractionSchema` (persons, orgs, phones, emails,
  accounts, amounts-as-decimal-strings, dates, urls/domains, devices, claims,
  events) validated by Phase 1 `parse_structured` + `check_fields_against_source`
  against the page/record text; amounts compared as exact `Decimal`.
- `AIService.extract_page()`: server-owned versioned prompt
  (`EXTRACTION_PROMPT_VERSION`), fenced `EVIDENCE` data block (untrusted),
  generation-semaphore bounded, behind `AI_FEATURE_EXTRACTION`.
- `app/services/extraction.py`: idempotent submit (one active job per evidence;
  attempt-numbered idempotency key) → `AnalysisJob(feature="ingestion")` run in
  a FastAPI background task (existing app pattern). Runner: **rechecks case
  membership before every context assembly**, verifies stored sha256 against
  bytes before parsing, ensures page source records idempotently, extracts
  page-by-page with cooperative cancel/timeout between pages, records one
  extraction artifact per page (locator `{record_no, field:"text"}`), status by
  validation: `valid→pending_review`, `flagged→pending_review` + errors,
  `invalid→failed` (raw excerpt kept), `status="recorded"` never used here.
  Result summary counts pages/fields/artifacts/invalid/ocr_required.
- Review: `ArtifactReviewRequest` gains optional edited `payload`; edits are
  re-validated against schema + source before approval (422 if an edit invents
  values). Approved artifacts are readable via existing `GET artifacts` and
  provenance; approval/rejection/edits audit-logged.
- Endpoints: `POST /{case}/evidence-intelligence/extract`,
  `POST .../jobs/{id}/cancel`, extended review. Codes: `EVIDENCE_UNAVAILABLE`,
  `UNSUPPORTED_FORMAT`, `EXTRACTION_ACTIVE`, `OCR_REQUIRED`, `INVALID_PAYLOAD`.

### 8.3 Feature 9 — Integrity & Chain-of-Custody Auditor

- **New `evidence_custody_events` table** (case/evidence FKs, event_type check
  collected|transferred|received|sealed|unsealed|verified|accessed|exported|
  restored|disposed, tz-aware `occurred_at`, actor/collector/transferor/
  recipient/notes/`recorded_sha256`, indexes `(evidence_file_id, occurred_at)`).
  Recorded only through an authorized endpoint going forward — **no fabricated
  history, no back-fill**.
- **Integrity verification** (`app/services/integrity.py`): pure
  `compare_hashes(algorithm, expected, actual)` → `match|mismatch|
  missing_expected|missing_source|unsupported_algorithm` (sha256 only, alias
  tolerant); `verify_evidence()` downloads original bytes (to_thread), hashes
  with the shared `fingerprint()`, compares, records a deterministic
  `custody_finding` artifact with `status="recorded"` (facts need no review)
  + `integrity.verified` audit row. Never writes evidence row or bytes.
- **Custody audit** (`app/services/custody.py`): pure `evaluate_custody(snapshot)`
  rule engine, `CUSTODY_RULE_SET_VERSION="1.0.0"`, rules grounded in the real
  schema: `hash_mismatch`, `hash_missing` (no sha/metadata — documentation gap,
  not tampering), `source_missing` (no object bytes), `chronology_predates_evidence`,
  `chronology_future`, `unacknowledged_transfer`, `duplicate_event`,
  `orphaned_event` (reference lost), `missing_required_field` (per-type policy:
  collected→collector, transferred→transferor+recipient, received→recipient),
  `no_documented_custody` (no audit entry & no custody event; severity info).
  Optional fields (location/notes) never fire. Findings → `custody_finding`
  artifacts (content-hash idempotent, `pending_review`), job `feature="custody"`.
- **AI explanations are separate artifacts** (`type:"ai_explanation"`,
  origin `llm`, `status="recorded"`, parent = finding): explain-what/why/
  missing/next-steps only — prompt forbids inventing custody entries or
  certifying integrity; behind `AI_FEATURE_INTEGRITY_EXPLAIN`.
- **Review mapping** (C5): open→`pending_review`, resolved→`approved` (with
  note; remediation = new custody event, never editing history), false
  positive→`rejected`, explained→explanation artifact attached.
- Endpoints: `POST .../evidence-integrity/verify`,
  `POST .../evidence-integrity/custody-audit` (job),
  `GET .../evidence/{id}/custody`, `POST .../evidence/{id}/custody-events`,
  `POST .../artifacts/{id}/explain`.

### 8.4 Frontend (extends evidence page; no redesign)

Contract/real/mock + hooks gain: `extract`, `cancelJob`, `reviewArtifact`
(edit), `verifyIntegrity`, `custodyAudit`, `custodyEvents`, `recordCustodyEvent`,
`explainArtifact`. Evidence drawer gets two panels: **Extraction** (action,
job progress, page-located preview, warnings/uncertain fields, original-vs-derived
badge, approve/edit/reject/retry, OCR-required notice) and **Integrity &
Custody** (verify result with algorithm + expected-vs-calculated + time, event
chronology, gaps/rules with review states, record-event form, AI explanation).
No fabricated green: unavailable source bytes/metadata render explicit
unknowns.

### 8.5 Evaluation additions (extend Phase 1 harness)

- `fixtures/evidence_intelligence/ingestion_checks.json`: valid extraction,
  multi-page mapping, empty content, invalid schema, unsupported fields,
  prompt injection, incorrect locator, exact decimal/date, all through the real
  validators (loader test counts executed checks — no vacuous passes).
- `fixtures/evidence_intelligence/custody_checks.json`: hash match/mismatch/
  missing source/unsupported algorithm, missing ack, duplicates, chronology
  conflict, valid optional omissions (must yield **zero** findings), orphaned
  references — through `evaluate_custody`.
- Reported separately: extraction precision, field-level validation rate,
  locator accuracy, unsupported-claim rate, hash-verification correctness,
  custody false-positive rate — with set sizes and limitations; no accuracy
  percentages beyond the measurements.

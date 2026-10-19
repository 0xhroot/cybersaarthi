# Phase 5–7 Plan: Multilingual Intelligence, Digital Forensics, AI Report Auditor, Final Integration

Status: **executed plan** — this document records the design decided *before*
implementation, the audit facts it rests on, and (in §7) the verified outcomes
once each phase landed. Like Phases 3–4 it follows audit-first: nothing below
was written before the codebase facts in §1 were confirmed by reading source.

## 1. Audit findings that shaped the design (verified, not assumed)

- **HEAD at start**: `8d90d6c` (Phase 4 final), clean tree, alembic head
  `c5e2b8f4d9a3`. All services healthy (postgres, neo4j, redis, minio,
  backend), local llama.cpp/Qwen3 reachable.
- **No complaint concept exists** anywhere in backend or frontend: a complaint
  is an evidence file (`txt`/`pdf`/`csv`/`json`) plus metadata, ingested
  through the existing upload → `SourceRecord` pipeline. Phase 5A therefore
  *analyzes evidence files as complaints*; it does not add a second intake
  path or a new table.
- **`multilingual` and `triage` job features are pre-registered** in
  `ANALYSIS_JOB_FEATURES` and in the `analysis_job_feature_valid` DB CHECK;
  **`translation` and `triage_observation` artifact kinds are
  pre-registered** in `DERIVED_ARTIFACT_KINDS` and its DB CHECK. **`report_audit`**
  and **`report_claim_review`** likewise. No Phase 5/6 migration is required
  to *use* them — only wiring (submit routes, runners, cancelable-feature
  entries, timeout settings).
- **Supported evidence formats are exactly `csv`, `json`, `txt`, `pdf`**.
  There is **no `.eml`/MIME parser and no OCR** (`OCRRequiredError` /
  `CODE_OCR_REQUIRED` are the honest refusals). Phase 5B parses forensic
  structure *from already-parsed source records* and re-downloads original
  bytes only for hash-manifest verification.
- **NER (`en_core_web_sm`) and field aliases are English-only.** Multilingual
  extraction cannot reuse them; it uses the local model plus deterministic
  validation against the original text.
- **Report drafts are AI chat messages** (`AIMessage`, mode `"report"`), not
  versioned rows: the `reports` table stores deterministic JSON/CSV/PDF
  *exports* in MinIO with no text payload, no versions and no content hash.
  The Phase 6 auditor therefore audits **draft text** (an existing
  report-mode message, or investigator-supplied text), pins it by sha-256
  content hash, and marks itself stale when the referenced message changes.
  Deterministic exports contain data rows, not free-text claims, and are out
  of scope (documented, not silently skipped).
- **Two citation validators exist**: `app/services/citations.py`
  (`validate_citation`, full DB-backed existence/scope/locator/value checks —
  previously unwired to any route) and `app/ai/retrieval.py:validate_cited_claims`
  (chat-answer checker used only for analysis/hypothesize). Phase 6 wires the
  former into claim validation; `report` mode additionally gains the
  response-level citation check (justified contract improvement: the field
  was always `None`).
- **Job/artifact infrastructure to reuse as-is**: `AnalysisJob`
  (`submit_case_feature_job` / `submit_extraction` patterns, cooperative
  cancel/timeout via `should_stop`, `still_authorized_for_case` rechecks),
  `DerivedArtifact` (`record_artifact` content-hash dedupe, review machine
  `pending_review → approved|rejected`, `review_artifact`,
  `PERM_FINDINGS_REVIEW`), the shared cancel route, the jobs list route,
  prompt fencing (`fence_data`, untrusted-content rules), the
  `parse_json_object`/`parse_structured` JSON recovery.
- **No language-identification library is installed** (no langdetect/fasttext/
  cld3) and downloading models is disallowed by policy. Language ID is
  therefore **deterministic Unicode script profiling**, cross-checked by the
  local model; disagreement is *flagged for human review*, never silently
  resolved.

## 2. Phase 5A — Multilingual Complaint Intelligence

**Objectives.** Analyze a complaint evidence file in Marathi, Hindi or
English while preserving the original text verbatim and keeping every derived
value reviewable and source-anchored.

### Design
1. **Intake**: existing upload (`POST /cases/{id}/evidence`) — no new path.
   The complaint is any `txt`/`pdf`/`csv`/`json` file; records are paragraphs
   (txt), pages (pdf) or rows, exactly as ingestion already parses them.
2. **Language identification (deterministic)**: `profile_scripts(text)`
   counts Unicode script runes (Devanagari, Latin, Arabic, digits, other) and
   proposes a candidate: Devanagari-dominant → `hi`/`mr` ambiguity set,
   Latin-dominant → `en`. Script evidence is always stored with the result.
3. **Model cross-check**: the local model classifies the language among
   {english, hindi, marathi, mixed, unknown}; the final recorded language is
   the model label **validated against the script profile** — a Latin-only
   complaint labelled Hindi (or vice versa) is flagged
   `language_ambiguous` and both values are kept for the reviewer. Scripts
   outside the supported set (no Devanagari/Latin dominance) → typed
   `LANGUAGE_UNSUPPORTED` refusal, never a fabricated analysis.
4. **Translation (only when requested or required)**: runs when the
   workflow needs it (`translate=true` param or extraction on non-English
   text). Stored as its own `translation` artifact
   (`origin="llm"`): `original_locator`, `source_language`,
   `translated_text`, `prompt_version`, and a **deterministic
   material-value check** — every number, identifier (phone/account/email),
   date and negation marker found in the original must survive into the
   translation or the artifact is flagged. Original text is never rewritten.
5. **Field extraction**: local model, strict JSON schema (names,
   organizations, account references, phones, emails, amounts+currency,
   dates, event statements, referenced identifiers). Each extracted value is
   validated **deterministically against the original text**: it must occur
   verbatim or in normalized form (whitespace, punctuation, Devanagari↔ASCII
   digit folding); values that do not are recorded with
   `validation_status="flagged"` and per-value errors — never silently
   dropped or "corrected".
6. **Ambiguity flags (deterministic)**: Devanagari-digit amounts, ambiguous
   `dd/mm` vs `mm/dd` dates, transliterated-name variants (Latin and
   Devanagari forms of the same token), same-value-different-format pairs,
   currency mentions without amounts, and legal-terminology markers.
   Each flag carries the record locator.
7. **Persistence**: `translation` artifacts for translations, `extraction`
   artifacts (payload marked `multilingual: true`) for field sets —
   content-hash deduped, `pending_review`, `flagged`/`valid` recorded by the
   shared services. Review/edit/approve/reject uses the existing
   `review_artifact` route (extraction payload edits already supported).
8. **Safety**: complaint text is fenced as untrusted data; the model never
   sees case ids it is not scoped to; the job rechecks authorization and
   cancellation per unit; no external service ever receives any text.

### API
- `POST /cases/{case_id}/evidence-intelligence/multilingual` — submit run
  for one evidence file (`{evidence_file_id, translate?, force?}`), typed
  409 `MULTILINGUAL_ACTIVE` while active, 422 typed rejections
  (`UNSUPPORTED_FORMAT`, `LANGUAGE_UNSUPPORTED`, `EMPTY_EVIDENCE`,
  `OCR_REQUIRED`, `INTEGRITY_*`).
- Job status via the existing jobs endpoint (`feature=multilingual`);
  cancellation via the existing cancel route.
- Artifacts via the existing artifacts listing + review/explain routes.

### Tests & evaluation (golden fixture, `n=` documented)
Synthetic complaints: English, Hindi (Devanagari), Marathi (Devanagari),
mixed Hindi-English, transliterated Hindi in Latin script, Devanagari-digit
amounts, ambiguous dates, negation sentences, prompt-injection paragraphs,
malformed model output (simulated), unsupported script (e.g. Bengali),
empty file. Gates: language-ID correctness per fixture; extraction
precision/recall against hand-labelled spans; **material-value preservation**
(numbers/ids/dates/negation) in translations; injection fixtures never
produce fields quoting the injected instruction; unauthorized access
(anon 401, non-member 403, revoked role mid-run, cross-case id 404/403);
cancellation branch; idempotent re-run (no duplicate artifacts).

## 3. Phase 5B — Digital Forensics Triage Copilot

**Objectives.** Deterministic parsing and rule-based observations over
supported digital artifacts + local-model explanations of *the parsed
observations only*. CyberSaarthi performs **no device acquisition, no file
execution and no malware analysis** — none of that is claimed.

### Deterministic parsers (operate on source records; manifest re-hashes bytes)
- **Email headers** (records with RFC822-style key/value fields or header
  lines in text): From/To/Subject/Date/Message-ID/Received/Return-Path,
  attachment-name mentions, SPF/DKIM/DMARC results when present.
- **URLs & domains**: regex extraction from any record text; *structural*
  analysis only (scheme, userinfo trick, raw-IP host, punycode/IDN,
  nonstandard port, length, subdomain depth, query-token counts). URLs are
  **never fetched, resolved or opened** — no network call exists in this path.
- **Browser-history exports** (csv/json rows with url/title/visit fields):
  per-domain visit counts, first/last visit, top domains.
- **Hash manifests** (csv/json/txt rows containing sha256 hex + filename):
  recompute sha-256 of the case's *other* evidence files from MinIO bytes and
  compare (reuse `validation.fingerprint`), reporting match/mismatch/missing
  per entry.
- **Log lines** (txt/csv with timestamp+severity structure): severity
  counts, top sources, auth-failure bursts, first/last event.

### Rules (deterministic, only where required fields exist)
`triage.url.userinfo`, `triage.url.ip_host`, `triage.url.punycode`,
`triage.url.nonstandard_port`, `triage.email.missing_message_id`,
`triage.email.return_path_mismatch`, `triage.manifest.hash_mismatch`,
`triage.manifest.entry_missing`, `triage.history.cross_scheme_redirect_chain_hint`,
`triage.log.auth_failure_burst`, each with severity and record locator.
Observations are **observations**: no "malicious" verdict is ever emitted.

### AI interpretation
One bounded local-model explanation per run over the *recorded observations +
excerpts* (fenced untrusted), explaining what was observed and recommending
further **verification steps** (e.g. "compare Message-ID with mail server
logs") — never conclusions about intent or payload.

### Persistence / API
`triage_observation` artifact per evidence file (`pending_review`), payload:
format profile, parsed fields, indicators, observations, missing
information, recommended checks, explanation (or recorded model failure).
Submit: `POST /cases/{case_id}/evidence-intelligence/triage`; typed 409
`TRIAGE_ACTIVE`; unsupported evidence (no parseable forensic structure —
e.g. pure prose) → typed 422 `TRIAGE_UNSUPPORTED_CONTENT`, never an empty
success.

### Tests & evaluation
Fixtures: benign email headers, deceptive URLs (userinfo, raw-IP, punycode),
browser-history csv+json, hash manifest (1 match + 1 mismatch), log burst,
prompt-injection embedded in a header value, malformed JSON history,
unsupported prose, empty file, unauthorized access, cancellation. Gates:
parser field exactness, rule firing set exactness (no over-firing on
benign fixtures), locator validity, injection never becomes an observation,
manifest verdict correctness against seeded bytes, denial matrix.

## 4. Phase 6 — AI Report Auditor

**Objectives.** Audit a report *draft* for unsupported claims, invalid
citations, numerical/timeline errors and potentially missing counter-
evidence — complementing (never replacing) the drafting workflow. The
original draft is never modified.

### Scope decision (honest)
Auditable object = **draft text**: either an existing report-mode
`AIMessage` (referenced by `conversation_id`+`message_id`, authorized via
case membership) or investigator-supplied `draft_text` (the common case of
an externally edited draft). The audit pins `draft_hash = sha256(text)`.
When a message is referenced, later reads compare the hash and mark the
audit **stale** if the message changed. Deterministic `reports` exports
(JSON/CSV/PDF data dumps) contain no free-text claims and are explicitly out
of scope.

### Pipeline (job feature `report_audit`, case-scoped)
1. **Snapshot**: authorization recheck; text retrieved once; `draft_hash`
   recorded in every artifact and in `result_summary`.
2. **Claim extraction (model, then deterministic validation)**: numbered
   claims with `char_start/char_end` spans, category (from a documented
   closed set: `factual_statement`, `attribution`, `quantity`, `timeline`,
   `identity`, `causal`, `opinion_hedge`), cited source ids, and the
   required check list. Deterministic gates: spans must reproduce the draft
   text exactly; cited ids must pass `citations.preflight` (well-formed +
   known kind) — malformed or invented ids become `invalid citation`
   findings, never silently dropped.
3. **Deterministic validation** (per claim): citation existence + case
   scope via `citations.validate_citation` (cross-case citations are
   **findings**, not retrievals); quoted-value equality where a locator
   quote is given; amounts/currency consistency across claims; date parsing
   (Devanagari and ASCII digits) and chronological ordering against the
   draft's own timeline claims and case `TimelineEvent`s → `timeline
   discrepancy` findings; arithmetic rechecks where a claim states a total
   of values it also cites.
4. **Semantic support (model, then deterministic quote validation)**: for
   each claim with valid citations, the authorized source excerpts are
   supplied and the model must answer one of
   `supported|partially_supported|contradicted|not_established` with an
   explanation that **quotes the source verbatim**; quotes that do not occur
   in the supplied excerpts invalidate the assessment (flagged for human
   review instead of trusted).
5. **Counter-evidence (deterministic retrieval)**: case-scoped search of
   source records for the claim's key identifiers/amounts; matches are listed
   as *candidate* counter-evidence for the reviewer. The payload always
   records `records_searched: N` and distinguishes "no records found" from a
   verified absence — the auditor never claims counter-evidence does not
   exist.
6. **Findings**: one `report_claim_review` artifact per audit run
   (`origin="llm"`, `validation_status="flagged"`, `pending_review`),
   payload: draft source + hash, per-claim findings with documented
   categories, deterministic severities (`high`: invalid citation /
   contradicted / numeric mismatch / timeline discrepancy; `medium`:
   partially supported / not established; `info`: candidate counter-evidence
   listed), model-assessment validity flags, `records_searched`,
   prompt+rule versions. Idempotent: identical (draft, versions) re-run
   returns the same artifact via content-hash dedupe.
7. **Corrections are proposals only**: suggested corrections live in the
   payload; applying one uses the existing report-drafting flow to create a
   *new* draft (no report-editing workflow exists — documented limitation,
   the original message is immutable in this system).

### API
`POST /cases/{case_id}/report-audits` (submit: `{conversation_id?,
message_id?, draft_text?}`), `GET /cases/{case_id}/report-audits` (list),
`GET .../{audit_id}` (detail incl. staleness vs current message hash),
cancel via the shared cancel route; permission = case access for submit
(same as report drafting), existing review machine for acceptance.

### Tests & evaluation
Supported/irrelevant/invalid/cross-case citations; arithmetic and currency
mismatch; timestamp/chronology mismatch; overconfident causal claims;
prompt injection inside draft text and inside cited evidence (model must not
obey; injected text must never become an "observation"); stale draft;
permission revocation mid-run; idempotent repeat; original-draft byte
preservation (assert the `AIMessage` row is unchanged); auditor does **not**
pass vacuously (fixtures contain supported claims that must come back
`supported` — marking everything unsupported fails the gate).

## 5. Phase 7 — Integration, Security, Evaluation, Delivery

1. **Feature inventory**: truthful 10-feature matrix in
   `docs/ai/FEATURE_STATUS.md` (backend service+API, frontend entry, data
   sources, authorization, review behavior, tests, live status, limitations).
2. **Regression**: full backend hermetic + integration suites, frontend
   tests/lint/typecheck/**production build**, `eval_phase3`/`eval_phase4`
   golden re-runs, chatbot/Think-mode/analysis/hypotheses/report-draft smoke
   via the existing API tests (extended where 5/6 changed contracts).
3. **Security audit tests**: anonymous/unauthorized/cross-case/IDOR for every
   new endpoint; permission revocation during jobs; prompt-injection fixtures
   in all three features; invalid model-generated identifiers; stale results;
   unauthorized review attempts; no sensitive data in audit metadata; diff
   secret scan.
4. **Combined evaluation** (`scripts/ai/eval_final.sh` +
   `backend/scripts/eval_final.py`): one report over all ten features with
   **individual metrics kept separate** — golden harness results
   (phase 3/4/5-6-7 fixtures, each with its own precision/recall/FPR and
   `n=`), deterministic unit-test inventory, live-model sections marked
   separately, anti-vacuous checks (every intended operation observed to
   run), and explicit "not measured here" labels for anything unmeasured.
5. **Operational reliability**: migration state verification
   (`alembic heads` unchanged), cancel/timeout branches re-probed live,
   model-unavailable behavior (jobs → honest `partial`/`failed`),
   error-shape consistency, startup/verification commands documented.
6. **Docs**: this file's §7 outcomes; `FEATURE_STATUS.md`,
   `IMPLEMENTATION_PROGRESS.md`, `EVALUATION.md` updated to verified state.

## 6. Acceptance criteria (per subphase, gates before commit)

- 5A: backend suite green (new unit+API tests), ruff/mypy clean, frontend
  tests green, golden multilingual eval exit 0, live probe of a real
  Devanagari complaint against local Qwen3 recorded (honest translation
  verdict included).
- 5B: same gates; live probe with a seeded deceptive-URL/history/manifest
  fixture recorded.
- 6: same gates; live audit of a real drafted report recorded (claim
  categories + findings observed end-to-end); draft-immutability asserted.
- 7: all suites + production build + combined eval exit 0; security tests
  green; docs updated; final report with real numbers.

## 7. Outcomes (filled in as phases complete)

All numbers below were re-verified in the Phase-7 combined run
(`./scripts/ai/eval_final.sh --report …` → **147/147 gates, exit 0**, 2026-10-19)
unless stated otherwise.

- **5A — `feat(ai): add multilingual complaint intelligence` (`2188527`)**:
  golden `n=7` complaints → 20 extracted values (15 real / 5 planted
  fabrication), 0 false accepts; profile/language/flags/negation/injection
  categories re-computed with 0 problems. Live vs local Qwen3: Hindi
  auto-detect 4.05 s (7/7 values verified, 1 translation recorded), explicit
  translation 4.05 s (7/7), English 8/8; unsupported script refused with 0
  artifacts; anonymous 401 / non-member 403 / records IDOR 404 live-checked;
  cancel contract covered.
- **5B — `feat(ai): add digital forensics triage` (`4447609`)**: golden `n=9`
  (3 benign, 1 refusal, 1 injection, 1 manifest, 3 burst) with 0 problems and
  bit-exact determinism. Live: 3 seeded URLs → 4 observations (3.04 s),
  manifest → 3/3 entries re-hashed + verified (2.03 s), unsupported format
  refused (expected `failed`, 0 artifacts); explanations never fail silently
  (`explanation_failed=0`).
- **6 — `feat(ai): add AI report auditing` (`bfa3171`)**: golden `n=19`
  across dates/amounts/arithmetic/chronology/currency with 0 problems,
  determinism exact. Live: 273-char draft → 6 claims, findings 6 high / 0
  medium / 1 info, 3 counter-evidence matches; artifact always
  `pending_review` + `flagged` with standing `model_claims_unreviewed`; 19
  audit metadata rows content-free; raw draft never persisted (sha256 only).
  Security tests added: anonymous 401 (submit/list/detail), mid-run
  revocation fails closed with `CASE_ACCESS_DENIED` and no artifact,
  injection-in-draft cannot approve or suppress findings (23/23 in suite).
- **7 — `test(ai): complete final AI integration and evaluation` +
  `docs(ai): finalize AI expansion status and delivery`**: combined harness
  `scripts/ai/eval_final.sh` → **147 gates, 0 failed, exit 0** (golden + live,
  213 s post-fix) covering all 10 features with per-feature `n=` kept separate.
  Cross-cutting gates: all five phase harnesses ran clean (5/3/16/47/64
  harness gates), test inventory ≥ 1000 (1048 collected at delivery),
  alembic head unchanged (`c5e2b8f4d9a3`), anonymous error-shape probe → 401
  `{"error": {code, message}}` on the Phase-6 submit route. Full backend
  suite **1048 passed**; frontend **216/216** + lint + typecheck + production
  build; `ruff check .` / `ruff format --check .` (290 files) / `mypy` (177
  files) clean; diff secret scan clean.
  - *Evaluation finding (Phase 7's own deliverable):* intermediate delivery
    runs failed `p1_analysis_all_pass` and root-caused **two distinct
    truncation walls** behind a stochastic-looking symptom — the retained
    per-slot KV prefix (→ per-slot ctx 8192 → 16384 in `run_server.sh`) and
    the analysis output floor (→ `ANALYSIS_MIN_MAX_TOKENS` 1024 → 2048 in
    `service.py`). Both were real product defects (truncated five-section
    reports reach users); the gate was never weakened and correctly failed
    the defective runs. Full narrative in `EVALUATION.md` §5.

## 8. Pre-stated limitations (decided before implementation)

- **No OCR**: scanned/image-only PDFs are refused (`OCR_REQUIRED`), as in
  Phases 1–4.
- **No `.eml`/MIME parsing**: email triage operates on header fields present
  in already-supported formats (csv/json/txt), not on raw MIME binaries.
- **Hindi vs Marathi** cannot be separated by deterministic script analysis
  (both are Devanagari); the local model's label is used and *any* disagreement
  with script evidence is flagged for human review rather than hidden.
- **Translation quality** is only measured as material-value preservation
  (numbers, identifiers, dates, negation) on synthetic fixtures — no BLEU or
  human-quality claim is made.
- **Triage makes no malware/phishing verdicts**: structural observations
  only; URLs are never fetched; nothing is executed.
- **Report auditor scope**: draft text only (chat drafts or pasted text);
  deterministic export files are out of scope; there is no authoritative
  report-editing workflow, so corrections create new drafts through the
  existing drafting flow.
- **Soup fine-tuning** remains a separate optional activity requiring
  explicit user authorization — untouched here.

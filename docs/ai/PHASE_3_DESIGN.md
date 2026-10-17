# Phase 3 Design — Entity Resolution, Timeline Reconstruction, Contradiction Detection

Status: implemented (Phase 3 of `docs/ai/EVIDENCE_INTELLIGENCE_AUDIT.md`).
Audit performed against HEAD `34e59db` (Phase 2 delivery), 2026-10-17.

## 0. Verified ground truth at start of Phase 3

`git log`: `009c9ce` (Phase 0 audit) → `656d157` (Phase 1) → `c725b74`, `7fe004d`,
`a0cb520`, `34e59db` (Phase 2). Working tree clean. Alembic head `c5e2b8f4d9a3`.

## 1. What already exists (reused, not duplicated)

### Feature A — entity resolution
| Piece | Where |
|---|---|
| `Entity` (case-scoped, 8 types, canonical/display/blocking_key/context/merged_into_id, unique `(case,type,canonical)`) | `app/models/entity.py` |
| `EntityAlias` (entity_id, alias_value, alias_type, source_record_id) | `app/models/entity_alias.py` |
| `EntityCandidate` / `EntityMatch` (mention-resolution tables) | `app/models/entity_{candidate,match}.py` |
| Normalizers + `blocking_key()` (phone/person/org/vehicle/…) | `app/services/normalization.py` |
| Blocking → `fuzz.ratio` (rapidfuzz) + context Jaccard → thresholds `92.0/78.0` | `app/services/resolution.py`, ADR-006 |
| Review queue + accept/reject + `POST /entities/merge` (`entity.merge`) | `app/services/resolve_review.py`, `app/api/routes/entities.py` |
| Per-type review UI (accept/reject), merge dialog | `frontend/src/app/pages/entities.tsx` |

Existing `resolution.py` resolves **mentions → entities during ingestion**. It does
**not** compare two already-resolved entities with each other; that pair-wise,
feature-transparent, reviewable workflow is Phase 3 Feature A.

### Feature B — timeline
| Piece | Where |
|---|---|
| `TimelineEvent` (occurred_at, 18-kind CHECK incl. `case_event`, payload JSONB, evidence/entity refs) | `app/models/timeline_event.py` |
| `record_event()` (flush-only, no validation) + `list_events()` | `app/services/timeline.py` |
| POST/GET `/cases/{id}/timeline` (POST = `case.update` + mutable case, audit) | `app/api/routes/timeline.py` |
| Structured date parsing `as_date`, exact `values_equal`, locator conventions | `app/services/structured_extraction.py` |
| Phase 2 extraction artifacts (`fields.transaction_dates`, `fields.events`, `record_no` locators) | `app/models/derived_artifact.py` |
| Read-only timeline page | `frontend/src/app/pages/timeline.tsx` |

### Feature C — contradictions
| Piece | Where |
|---|---|
| `SourceRecord.raw_data` JSONB (all record values), `entity_mentions` | `app/models/source_record.py` |
| `as_decimal` / `as_date` / `values_equal` (exact Decimal/date compare) | `app/services/structured_extraction.py` |
| Citation validation (`validate_citation`, case scope, locator + value equality) | `app/services/citations.py` |
| Findings status workflow (`NEW→REVIEWED/CONFIRMED/DISMISSED`, per-status perms) | `app/services/findings_service.py` |
| Deterministic rule-engine precedent (custody rules v1, artifact write) | `app/services/custody.py` |

### Shared (Phase 1/2) infrastructure — reused verbatim
- `AnalysisJob`: features **already include** `entity_resolution`, `timeline`,
  `contradiction`; idempotent `create_job`, transitions, cancel flag, timeout,
  `should_stop`; runner pattern `run_*_job(app, job_id)` + `execute_*(session, …)`
  with per-batch `still_authorized_for_case` recheck.
- `DerivedArtifact`: kinds **already include** `entity_resolution`,
  `timeline_proposal`, `contradiction`; content-hash idempotency, one-shot review
  (`pending_review → approved|rejected`, `findings.review`), provenance columns
  (case, source_record_id, source_locator, parser/prompt/model versions, job id,
  validation_errors, parent_artifact_id).
- `services/authorization.still_authorized_for_case`, `services/audit`,
  `services/timeline.record_event`, `services/artifacts.record_artifact`.
- Generic endpoints: `GET …/evidence-intelligence/artifacts?kind=…`,
  `GET …/evidence-intelligence/jobs?feature=…`, `POST …/artifacts/{id}/review`.

**Conclusion: no new tables and no alembic migration are required.** All three
features fit the reserved vocabularies; proposals are artifacts; committed
timeline events go through the existing timeline service.

## 2. What must be added

| # | Addition | Where |
|---|---|---|
| 1 | `entity_matching.py` — pair generation, transparent features, conflicts, job runner | `app/services/` |
| 2 | `timeline_reconstruction.py` — timestamp parsing (original preserved), proposal extraction, duplicate/conflict detection, commit | `app/services/` |
| 3 | `contradiction_detection.py` — deterministic claim comparison + bounded LLM semantic pass, alternatives, review-state notes | `app/services/` |
| 4 | Resolution/comparison prompts (versioned, fenced untrusted data) | `app/ai/prompts.py` |
| 5 | 3 submit routes + commit/resolve routes; cancel feature list extended | `app/api/routes/case_intelligence.py` (new), edit `evidence_intelligence.py` |
| 6 | Budget settings | `app/core/config.py` |
| 7 | Fixture sets + unit/API tests + live eval harness | `tests/`, `scripts/eval_phase3.py` |
| 8 | Candidate Matches panel, timeline reconstruction UI, Contradictions panel + contract/mock/hooks | `frontend/` |

## 3. Feature A — AI entity resolution and deduplication

### Candidate generation (deterministic, indexed, bounded)
Pairs are generated **between already-resolved entities of the same type** in one
case, by three indexed probes only (no all-pairs scan):

1. **Blocking buckets** — `find_by_blocking_key`-style query grouped by
   `(entity_type, blocking_key)`; all pairs inside a bucket (bucket cap
   `RESOLUTION_MAX_PER_BUCKET`, run cap `RESOLUTION_MAX_PAIRS`).
2. **Alias ↔ canonical exact** — `entity_aliases.alias_value` joined to another
   entity's `canonical_value` of the same type (exact identifier match).
3. **Alias ↔ alias** exact equality between two entities.

Same-type + same-canonical pairs cannot exist (unique constraint), so exact
matches surface only through aliases — never fabricated. Cross-type pairs are
never generated (merge refuses `TYPE_MISMATCH`, so a cross-type "match" would be
meaningless).

### Feature-level signals (transparent; no probability claims)
Per pair, computed from real fields only:

| feature | meaning |
|---|---|
| `name_similarity` | `fuzz.ratio(canon_a, canon_b)` (rapidfuzz, 0–100) |
| `alias_exact` | A's alias == B's canonical (or vice versa) |
| `shared_identifiers` | context signals of A ∩ signals of B, where the signal resolves to another entity of identifier type (`phone/account/vehicle/document`) |
| `conflicting_identifiers` | identifier signals of A and of B both non-empty and **disjoint** |
| `shared_source_records` | count of common `entity_candidates.source_record_id` |

`matching_fields` and `conflicting_fields` are stored as separate payload lists.
`method` is one of `exact_alias` / `exact_identifier` / `name_similarity` /
`context_overlap`. `score` is a 0–100 band label (`strong ≥ 92`, `ambiguous
78–91.99`, mirrors ADR-006 thresholds) and is presented as *score semantics,
not a probability*.

**Guard:** a pair with only `name_similarity` above the band, or a pair whose
identifiers conflict, is stored with `validation_errors`
`no_identifier_evidence` / `conflicting_identifiers` and `validation_status
"flagged"`. Name/location similarity alone never yields an exact-identity claim.

### LLM usage (ambiguous pairs only)
Only pairs in the ambiguous band **without** exact identifier evidence are sent to
the local Qwen3 (`AI_FEATURE_RESOLUTION`, bounded by `RESOLUTION_MAX_LLM_PAIRS`,
default 10). The prompt receives only the two display values + transparent
feature summary, fenced as untrusted; it returns
`{"verdict": "same|different|unclear", "reason": str}`. Verdicts must parse and
are stored under `payload.llm` with prompt/model versions; any artifact that
contains an LLM contribution is `validation_status "flagged"` with an
`ai_unverified` error — the model never certifies identity. Returned ids: the
model is never given ids to echo; if a response contains an `id` key it is
dropped before storage (validated against the candidate set = empty by
construction).

### Storage and approval
- One artifact per pair: `kind="entity_resolution"`, `origin="deterministic"`
  (`"llm"` when the LLM verdict was included), `status="pending_review"`,
  payload = `{type:"entity_candidate", entity_a, entity_b, display values,
  method, score, score_band, matching_fields, conflicting_fields,
  source_record_ids, llm?}`. Content-hash idempotency makes retries free.
- **Approval does not merge.** `merge_entities` exists but has no rollback (no
  unmerge, candidates/matches not re-pointed), so per the Phase 3 rules the
  approval flow reuses only the audited, reversible parts: one-shot
  `review_artifact(approved|rejected)` via the generic review endpoint, and on
  approval an additive `EntityAlias(duplicate.canonical → primary.entity)` with
  `alias_type="resolution"` plus audit `derived_artifact.approved` +
  `resolution.candidate_approved`. Entity rows, statuses, `merged_into_id` and
  relationships are untouched → measured false-merge rate is 0 by construction.
  Canonical merging stays available as its own explicit `entity.merge` action
  (existing, preserved).
- Approve/reject = `findings.review` (ANALYST/INVESTIGATOR/ADMIN) through the
  existing review route; defer = leave `pending_review` (no state is invented).

## 4. Feature B — automatic timeline reconstruction

### Event extraction (deterministic first; no LLM pass in Phase 3)
Sources, in order, all re-authorized (`evidence.read`) before read:
1. **Structured source records** — every `raw_data` value under a date-like field
   name (`date|time|timestamp|occurred|incident|created|updated|posted|txn_date|…`)
   parsed by `parse_timestamp`.
2. **Phase 2 extraction artifacts** — `payload.fields.transaction_dates` (exact,
   already source-validated) and `payload.fields.events` entries that contain an
   explicit date token (regex), each with locator `{record_no, field, index}`.

LLM extraction from free text is deferred (documented limitation): the data model
supports deterministic timestamp extraction, and quote-grounded free-text event
extraction is not yet implemented — better than ungrounded model dates.

### Timestamp semantics (all distinctions required by the spec)
`payload.time_semantics` is one of `record_occurs_on | statement_refers_to_event |
document_created | uploaded | extraction`. `payload.original_timestamp` always
retains the source string; `payload.tz` records the original offset/zone
(`"UTC"` when explicitly UTC, `"+05:30"`, or `null` when naive). Normalisation to
a UTC `occurred_at` for comparison **never overwrites** the original. Flags:
- date-only → `time_granularity: "date"`, midnight UTC assumed (documented);
- naive local timestamp → `tz_assumed: true`, `validation_errors:
  ["ambiguous_timezone"]`, `validation_status "flagged"`;
- unparseable / absent → **no datetime is invented**: a proposal is stored with
  `payload.missing_timestamp: true`, original value preserved, `flagged`, and the
  commit endpoint refuses it (`TIMELINE_TIMESTAMP_MISSING`).

### Reconstruction workflow
1. Route: `POST …/evidence-intelligence/timeline-reconstruction` (`ingestion.run`,
   mutable case) → job `feature="timeline"`, attempt-keyed idempotency.
2. `execute_timeline_reconstruction`: authz → running → bounded load of records
   (`TIMELINE_MAX_RECORDS`) + extraction artifacts (`TIMELINE_MAX_ARTIFACTS`) →
   per-batch `should_stop` + authz recheck + `advance` → proposals recorded as
   `kind="timeline_proposal"` artifacts (`origin="deterministic"`,
   `source_record_id` + `source_locator`, prompt/parser versions).
3. **Duplicates/conflicts** (deterministic): two proposals with the same
   normalised timestamp + same source record + same title → duplicate (the later
   one is flagged `duplicate_proposal` and links `duplicate_of`); proposals from
   the same record with different dates → both flagged `conflicting_timestamp`;
   proposals whose (`evidence_file_id`, UTC day, title) matches an existing
   timeline event → flagged `matches_existing_event`.
4. Compare with the authoritative timeline (existing events are read-only
   context, never replaced).
5. UI review → approve via generic artifact review → `POST
   …/timeline-proposals/{id}/commit` (`case.update`, mutable case, authz recheck)
   → `timeline.record_event(kind="case_event", payload={proposal_artifact_id,
   source_record_id, source_locator, time_semantics, original_timestamp, tz})`.
   Double commit is idempotent (an event already carrying the proposal id is
   returned instead of a second row). Existing events are never modified.

## 5. Feature C — contradiction detection

### Deterministic candidate generation (subject-anchored; never "same entity ⇒ compare")
Claims are extracted from `SourceRecord.raw_data` with field classification
(`amount|currency|date|status|identifier`) reusing `as_decimal`/`as_date`
parsers. Pairs are only generated inside one of these rules (each is a named,
versioned rule, `CONTRADICTION_RULES_VERSION = "1.0.0"`):

| rule | condition (both records, same case) |
|---|---|
| `amount_disagreement` | share an exact transaction/reference identifier value; normalised amounts differ (`Decimal` !=) |
| `currency_disagreement` | same anchor; currency codes differ |
| `date_disagreement` | same anchor; normalised dates differ |
| `status_disagreement` | both mention the same identifier entity; same status-like field name; values differ |
| `identifier_disagreement` | same anchor; identifier field values differ |

Anchors are exact identifier values (transaction/reference ids) or identifier
entities present in **both** records — records are never compared merely for
mentioning the same entity with unrelated fields. Pair evaluation is bounded
(`CONTRADICTION_MAX_PAIR_EVALS`).

### LLM pass (semantic text only, bounded)
Two structured statements/excerpts sharing an anchor and a field name are
eligible; at most `CONTRADICTION_MAX_LLM_PAIRS` (default 10) go to the local
model with fenced untrusted text and a strict JSON answer
`{"contradicts": true|false, "explanation": str}`. Non-boolean answers are
discarded (counted `llm_invalid`). Only `true` yields a candidate, always
`origin="llm"`, `validation_status="flagged"` + `ai_unverified` — never confirmed
by fiat. If the AI is disabled the run completes deterministic-only
(`llm_skipped` in the summary).

### Output (required fields, where the model supports them)
Artifact `kind="contradiction"`, `origin` deterministic/llm,
`status="pending_review"`, payload:
```
{type:"contradiction", category, rule, rule_version, priority,
 first:{source_record_id, evidence_file_id, field, value, original, locator},
 second:{…}, conflicting_values:[…], explanation,
 alternatives:[…], missing:[…],
 llm?:{contradicts, explanation, prompt_version}}
```
`priority` is a transparent rule mapping (`amount/status = high`,
`date/identifier/currency = medium`, semantic = `low`), documented in code.
`alternatives` are rule-generated (timezone_difference, document_revision,
time_window, transaction_reversal, reporting_window) — plausible readings, not
findings. `missing` lists absent anchors/fields honestly.

### Review lifecycle (states are records, payload stays immutable)
States: `unresolved` (default = `pending_review`), `confirmed` (artifact
`approved`), `false_positive` (artifact `rejected`) — both via the generic
one-shot review endpoint. `explained`, `requires_evidence`, `deferred` are
recorded by `POST …/artifacts/{id}/resolve {state, note}` → a **child artifact**
`kind="contradiction"`, `origin="deterministic"`,
`payload={type:"contradiction_review", state, note, for_artifact_id}`,
`status="recorded"`, `parent_artifact_id` set, audit written (the Phase 2
explain-artifact precedent: corrective/review actions are new auditable records,
never rewrites of the proposal or the evidence).

## 6. Shared rules

- Idempotency: attempt-numbered job keys with `IntegrityError` fallback;
  artifact `content_hash` dedupe; commit idempotent by proposal id.
- Canceled jobs can never succeed (Phase 1 transition table; `_stop_job`/`_fail_job`).
- Authz: route gate → `still_authorized_for_case` before context assembly and
  every bounded batch → recheck before commit/resolve writes. Reviewer perms:
  submit/cancel = `ingestion.run`; review/resolve = `findings.review`; commit =
  `case.update`; reads = `case.read`/`evidence.read`.
- Untrusted content: record strings and artifact payloads are fenced in every
  prompt (`fence_data`); prompts forbid acting on instructions inside data.
- Logging: ids and counts only — no evidence content, no prompt bodies, no keys.
- Provenance on every proposal: case, source ids, locators, parser/prompt/model
  versions, job id, created/processed timestamps, validation + review status,
  rule/algorithm version.

## 7. Evaluation

New deterministic fixture sets under `tests/fixtures/evidence_intelligence/`:
`entity_resolution_checks.json`, `timeline_checks.json`,
`contradiction_checks.json` (+ `phase3_live_checks.json` for the live run), each
with positive, negative, ambiguous and empty-result cases, consumed by
anti-vacuous runner tests (a suite that returns no findings must fail).

Measured separately, each with `n=` and limitations:
entity-match precision/recall/FP-rate, **false-merge rate (must be 0** — entity
rows unchanged after approval), timeline event precision/recall, timestamp
correctness + locator validity, contradiction precision/FP-rate, citation/case
consistency, authorization + prompt-injection behaviour, retry idempotency +
cancellation, latency.

Harness: `scripts/eval_phase3.py` (`0` pass / `1` gate fail / `2` setup fail),
wrapper `scripts/ai/eval_phase3.sh`. Live flow on a dedicated synthetic case:
upload synthetic CSV → ingest → entity-resolution / reconstruction /
detection jobs → verify artifacts, approve → assert aliases added but **no entity
merged** → commit one proposal → assert timeline event provenance → cleanup
(case + objects + rows, as fixed in Phase 2).

## 8. Frontend

- `entities.tsx`: Candidate Matches panel (pair ids + display values, matching /
  conflicting fields, source records, method + score-band semantics, review
  state, approve/reject/defer, name-only warning badge, submit action + job
  status).
- `timeline.tsx`: reconstruction action + proposed-events section visually
  distinct from accepted events; original timestamp + tz, locators, duplicate /
  conflict / missing-timestamp flags, approve + commit controls, cancel.
- `analytics.tsx`: Contradictions card — side-by-side values + locators,
  explanation, alternatives, rule priority, review controls incl. resolve states.
- Contract/real/mock/parity + hooks (`useSubmitResolution`,
  `useSubmitReconstruction`, `useSubmitContradiction`, `useResolveContradiction`,
  `useCommitTimelineProposal`; candidates reuse `useArtifacts(kind=…)` and
  `useIntelJobs(feature=…)`); panel tests following `evidence-panels.test.tsx`.

## 9. Limitations (documented, not hidden)

- No LLM free-text event extraction yet (deterministic structured extraction only).
- No OCR; only ingested text-layer/structured data can be analysed.
- Merge rollback does not exist → Phase 3 never merges; canonical merge remains
  the pre-existing explicit `entity.merge` action with its current semantics.
- Fixture sets are small and synthetic; metrics describe this set only.
- Graph (Neo4j) projection is not re-synced by approval (aliases are read-side).

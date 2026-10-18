# Phase 4 Design — Financial Flow Intelligence + Cross-Case Pattern Discovery

Status: audit complete, design frozen before coding.
Baseline HEAD: `3065dc9` (end of Phase 3). Alembic head: `c5e2b8f4d9a3`.

## 1. Scope and constraints

Phase 4 adds two features on top of the Phase 1–3 evidence-intelligence layer:

- **Feature A — Financial Flow Intelligence**: deterministic analysis of fund
  flows from authorized transaction-bearing records inside one case, with
  reviewable pattern candidates and an optional local-model explanation of the
  deterministic results.
- **Feature B — Cross-Case Pattern Discovery**: permission-scoped, indexed
  discovery of shared indicators across several cases, producing reviewable
  candidate links that never become authoritative without explicit approval.

Non-negotiables carried forward: local llama.cpp/Qwen3 only; no Ollama/cloud;
original evidence and transactions never mutated; deterministic code owns all
amounts, timestamps, graph traversal and access decisions; the LLM only
interprets deterministic results; every AI-influenced proposal is reviewable;
no accuracy claims beyond measured fixtures.

## 2. Audit findings (verified, not assumed)

### 2.1 Repository state

- HEAD `3065dc9`, working tree clean; alembic head `c5e2b8f4d9a3` (no pending
  migrations); Phase 2 baseline `34e59db`.
- Phase 3 delivered: entity resolution, timeline reconstruction, contradiction
  detection; all gates green (853 backend / 8 integration / 153 frontend /
  16/16 phase-3 eval gates).

### 2.2 Transaction data availability (A1 — the critical finding)

**There is no `transactions` table and no account master table.** Full table
inventory (migrations `e308a313166d`, `081a88d02574`, `a9b8c7d6e5f4`,
`a4b9c7e16d20`, `c5e2b8f4d9a3`) contains no payments/ledger/transfer tables.

> **A1 verification note (corrects an earlier draft of this section).** This
> section previously assumed `source_records` carried financial *columns*
> (`transaction_id`, `transaction_amount`, `currency`, `occurred_at`,
> `source_locator`). Inspecting `information_schema.columns` shows **none of
> those columns exist**. The complete `source_records` schema is exactly:
> `evidence_file_id, record_no, raw_data (JSONB), normalized_data (JSONB),
> entity_mentions (JSONB), relationships_data (JSONB), status, error, id,
> created_at, updated_at`. Every fact below was measured over **all 1000**
> rows in the dev database (the `42` distinct `raw_data` keys were enumerated),
> not assumed.

**Verified inventory of financial facts:**

| source | what actually exists | measured `n` (of 1000 records / 9 victims) |
|---|---|---|
| `source_records.raw_data.amount` | JSON **string** amounts (`"4500.00"`, `"12000.00"`) — parseable to exact `Decimal` losslessly | 6 rows carrying amounts = **2 distinct amounts** (each repeated across files); 1 junk value (`"b"`) rejected |
| `raw_data.transaction_id` | `TXN-SIH-001`, `TXN-SIH-002` | 2 |
| `raw_data.beneficiary_name` / `beneficiary_phone` | **payee side only** | 4 |
| `raw_data.merchant` | `PhonePe Merchant`, `Paytm Merchant` | 2 |
| `raw_data.account` / `account_no` / `account_number` | free-form account refs (`ACC-SIH-001`, `1100220011`) | 207 |
| `raw_data.bank_name` | `TechSecure`, `SecureMart`, … | 204 |
| **payer / sender side** | — | **0** (no `payer`/`sender`/`from`/`debited` key exists anywhere) |
| **transaction timestamps** | — | **0** (no `date`/`time`/`occurred_at` key exists anywhere) |
| `victims` (case-scoped, `case_id` on all 9) | `reported_amount`, `amount_lost`, `recovery_amount` are `double precision` (**Float → precision warning**); `currency` = `INR`; `incident_date` timestamptz | `reported_amount` 6, `amount_lost` 1, `currency` 5, `incident_date` 5; `digital_accounts` / `wallet_addresses` **0 populated** |
| `relationships` edge types | `works_for`, `located_at`, `owns`, `called`, `visited`, `associated_with` | **no transfer / payment / debit edge type exists** |

**Blockers (reported, not worked around):**

- **A3 multi-hop directional fund-flow paths are not derivable.** A flow path
  needs two linked accounts and a direction. There are no transfer edges in
  `relationships`, no payer side in any record, and at most one account per
  record. Nothing in the schema asserts "X moved money to Y".
- **A4 temporal movement patterns are not derivable.** No transaction carries
  a timestamp, so structuring/rapid-layering/velocity rules have no time
  dimension. (Victim `incident_date` gives one timestamp per victim, not per
  movement.)
- **Currency attribution for record-level amounts is absent.** Sums are
  therefore grouped under an explicit `currency: null` bucket flagged
  `currency_unknown`, never silently labelled INR.

**Supported portions (implemented):**

1. A "transaction fact" in Phase 4 is a **derived, deterministic extraction**
   from an authorized `SourceRecord.raw_data`, exactly as Phase 3 timeline
   events were derived extractions. Originals are never rewritten; missing
   fields are marked `null` + counted, never invented.
2. Account references are free-form strings. Normalization is documented and
   lossless; there is no account entity registry to validate against.
3. Victim loss totals (Float columns) are converted through
   `Decimal(str(value))` and carry an explicit `precision: "float_source"`
   limitation on the fact.
4. Structure analysis is an **association network** (account ↔ bank ↔ merchant
   ↔ beneficiary ↔ vehicle/city co-occurrence, plus `owns` edges), explicitly
   typed `association` vs `transfer`, with `confirmed_transfer_edges: 0`
   reported honestly rather than implied.

### 2.3 Entity and relationship model

- `entities` are **case-scoped** (`case_id` FK; unique
  `(case_id, entity_type, canonical_value)`). The same real-world account in two
  cases is two rows — exactly what cross-case discovery must surface, and the
  reason cross-case links cannot silently merge entities.
- `entity_type` includes `account` and `organization` — flows can anchor to
  entities, but flow analysis keys on extracted account *references*, not on
  entity rows (entity extraction is heuristic; references are complete).
- `relationships` are case-scoped with a fixed type vocabulary (no `transfer`
  type); Phase 4 does **not** invent relationship types or write edges into
  `relationships`/Neo4j for flows. Flow edges live in the deterministic result
  payload (see §4).
- Phase 3 approval writes additive `EntityAlias` rows (`alias_type
  = "resolution"`) and never merges — reused unchanged in Phase 4.

### 2.4 Reusable infrastructure

- `AnalysisJob` (+`submit_case_feature_job`, cooperative cancel, idempotency
  keys, one active job per (case, feature)); `ANALYSIS_JOB_FEATURES` **already
  contains `financial_flow` and `cross_case`** (model constant + DB check
  constraint — no migration needed for job vocabulary).
- `DerivedArtifact` (+`record_artifact`, content-hash dedupe, parent/child
  chains, validation status/errors, parser/prompt/model versions).
- Review: `resolve_review.resolve_artifact_decision` state machine
  (pending_review → recorded/…, note-gated refusals) + generic review route.
- Authorization: `app/core/rbac.py` (roles, 17 permissions, code-derived from
  role **name** — the `roles` table has no permissions column, so extending the
  vocabulary is a code change, **no data migration**), case-access helpers
  (`accessible_case_ids`, implicit admin), `require_permission`,
  `assert_case_mutable`.
- Audit: `audit_service.record_audit` (Phase 3 action vocabulary pattern).
- Local model: `app/ai/service.py` `AIService` implements small Protocol
  resolvers (`compare_entity_pair`, `compare_statements`) with bounded,
  schema-checked, advisory-only calls; failures degrade to deterministic.
  Phase 4 adds two sibling resolvers.
- Citation validation: `app/services/citations.py` (quote checks, substring
  guards, bounded claims) — reused for all model text.
- Frontend: `ApiEvidenceService` + five Phase-3 panels + hooks + mock adapter
  with parity tests; Analytics page mounts panels; design-system components.

### 2.5 Existing Analytics / graph services

- `analytics/`: deterministic priorities, patterns, strength scores, path
  finding over the **PG `relationships`** table, community detection; bounded
  and case-scoped; none of it understands transactions (nothing to reuse for
  amounts, everything to reuse for bounded-query discipline).
- Neo4j projection (`app/services/graph_sync.py`): single write path; MERGE on
  entity id / relationship id; per-case scoping via `case_id` property;
  read-back via `case_graph`. Consistency gaps: §3.

### 2.6 Cross-case surface today

- No cross-case endpoint exists. `GET /cases` lists only accessible cases.
- Status codes: 401 anon, 403 wrong-role, 404 non-member/non-admin (no case
  existence leak); 409 for state conflicts (read-only case, duplicate entity,
  one-active-job).
- No permission-filtered response caching exists (no Redis read path), so
  caching cannot bypass changed permissions; Phase 4 adds none.
- Idempotency keys are globally unique — key guessing across cases cannot leak
  existence (404 before lookup).

## 3. Mandatory graph consistency audit

### 3.1 What is actually consistent today

| canonical change | projection update? | evidence |
|---|---|---|
| entity/relationship creation via ingest | **yes**, end-of-file `sync_case` (also on the async path); failures recorded per file, retry endpoint exists | `ingestion.py:246,312-332`, `evidence.py:639-684` |
| full-case re-ingest retry | **yes**, `sync_case` is idempotent MERGE + duplicate-edge prune | `graph_sync.py:190-210` |
| entity merge (Phase 2) | **no** — Neo4j node keeps `status='active'`; PG `merged`/`merged_into_id` invisible | `resolution.py` merge path, no graph call |
| Phase 3 alias approval | **no** — aliases are PG-only; graph nodes never carry alias data (not in node payload) | `graph_sync.py:70-110` node props |
| case deletion | handled by `delete_case` in cleanup tooling | `graph_sync.py:212` |

So the Phase 3 report is confirmed: **approved aliases and merges are invisible
to Neo4j, and merged nodes remain queryable as active.** Any Neo4j-based
traversal today can (a) miss alias-established identity and (b) traverse
through merged-away entities.

### 3.2 Targeted correction (no redesign)

The projection is keyed by immutable PG ids and MERGE-idempotent — the
mechanism is sound; only the *trigger coverage* and *alias payload* are
missing. Targeted change, reusing `sync_nodes`:

1. `GraphSyncService.sync_entity(session-independent, entity, aliases)` —
   single-entity MERGE extending the existing payload with an `aliases`
   property (list of alias strings from `entity_aliases`, including Phase 3
   `resolution` aliases). Idempotent by construction.
2. Call sites (same transaction boundary discipline as Phase 3's
   `apply_approved_match` — PG commit first, projection best-effort second):
   - Phase 3 `apply_approved_match`: after alias insert → sync both entities
     with aliases.
   - Phase 2 merge path: sync the surviving entity and mark the absorbed
     node `status='merged'` in Neo4j (never delete silently; keeps provenance
     and matches PG).
3. Failure handling: projection errors are caught, logged, and surfaced —
   `record_audit("graph.sync_failed", …)` plus a `graph_synced: false` flag in
   the mutation's response. **Stale graph state is never presented as current**:
   the graph read path already exposes `graph_synced` freshness
   (`entity_service.graph_synced`); the cross-case feature (§5) does not read
   Neo4j at all in Phase 4, so discovery correctness never depends on
   projection freshness.
4. Tests: integration tests (real Neo4j, as all existing graph tests) assert
   (a) alias approval → `case_graph` shows the alias on both nodes, (b) merge →
   absorbed node `status='merged'`, (c) double sync idempotency (node/edge
   counts stable), (d) `graph.sync_failed` audit on a broken driver. Unit tests
   with a recording fake driver assert call-site wiring.

### 3.3 Why cross-case discovery does not use Neo4j in Phase 4

Cross-case candidate generation is **exact indicator equality over extracted
values** (§5.2) — a PostgreSQL/in-memory operation on authorized rows. Neo4j
traversal across cases would add projection-freshness risk for zero analytical
gain at this stage. The design doc records this as a deliberate boundary, not
an oversight: Neo4j re-enters cross-case work only after the corrected
projection is proven (tests in §3.2) *and* a case-scoped multi-case query need
is demonstrated.

## 4. Feature A — Financial Flow Intelligence

### 4.1 Deterministic transaction extraction (`app/services/financial_flow.py`)

Pure, versioned rules (`FLOW_RULES_VERSION = "flow-rules/1.0.0"`). For every
`SourceRecord` in the authorized case scope:

1. **Transaction id**: no `transaction_id` column exists — read the first
   documented alias hit in `raw_data` (`transaction_id`, `txn_id`,
   `upi_txn_id`, `utr`, `reference_no`, …; only `transaction_id` is observed in
   current data). Preserved verbatim as `txn_ref_original`; a normalized form
   (trimmed, uppercased) is derived for grouping only.
2. **Amount**: no `transaction_amount` column exists — read the `raw_data` alias
   (`amount`, `transaction_amount`, `txn_amount`, `value`) parsed via
   `Decimal(str(v))` (JSON strings like `"4500.00"` parse exactly). Victim
   amounts come from `double precision` columns and carry a
   `precision: "float_source"` limitation. Amounts are `Decimal` end-to-end; no
   float arithmetic; no cross-currency arithmetic ever. Non-numeric junk (e.g.
   `"b"`) is rejected and counted, never coerced.
3. **Currency**: no `currency` column on `source_records`; only `victims.currency`
   (observed `INR`). Record-level amounts therefore land in an explicit
   `currency: null` bucket flagged `currency_unknown`, counted separately.
   No conversion; a mixed-currency aggregate is split per currency and a
   limitation records the unconverted currencies.
4. **Accounts**: receiver side exists (`beneficiary_name`, `beneficiary_phone`,
   `account`, `account_no`, `account_number`); **no sender-side key
   (`from_account`, `payer`, `debit_account`, …) occurs anywhere in current
   data**, so facts are routinely one-sided. Documented normalization for
   comparison only: trim, upper-case, strip separators. Originals always
   preserved. A one-sided fact is retained and marked `incomplete` with
   `missing: source` — the source is **never invented**.
5. **Time**: no `occurred_at` column and no `date`/`time` key in `raw_data`
   (measured: 0 of 1000), so record-level facts are marked
   `missing_timestamp` and excluded from time-windowed rules (mirrors Phase 3;
   never invents a time). `victims.incident_date` is the only populated
   timestamp (5 of 9) and applies only to victim-level facts.
6. **Status**: no status-ish key occurs in current `raw_data`, so facts default
   to `unknown` unless a documented keyword set matches a real field. Facts with
   non-completed status are retained and clearly marked; aggregates separate
   them (a reversed transfer never counts as completed flow).
7. **Provenance**: every fact carries `source_record_id` +
   `source_locator: {record_no, field}` (Phase 3 locator discipline) and the
   evidence-file id. Facts are stored **only inside the artifact payload** —
   source records are never mutated.

Output: `TransactionFact` list + `extraction_warnings` summary. Facts failing
provenance validation (record not in case, missing locator) are dropped and
counted.

### 4.2 Deterministic analysis

All bounded: `FLOW_MAX_RECORDS` (default 5 000 records), `FLOW_MAX_EDGES`
(default 2 000), `FLOW_TRACE_MAX_DEPTH` (default 4), `FLOW_TRACE_MAX_PATHS`
(default 50), execution deadline checked between steps; cancel-requested jobs
abort with the Phase 3 typed refusal.

1. **Structure network (association, not transfer)**: nodes = normalized
   account refs + banks + merchants + beneficiaries; edges are derived from
   **co-occurrence within one source record** and from existing `owns`
   relationships. Every edge carries an explicit `edge_kind`:
   `"association"` (derived co-occurrence, always `suspected`) or
   `"transfer"` (schema-asserted money movement). Measured today:
   `confirmed_transfer_edges = 0`, because no record states a two-sided
   movement — the payload reports that number rather than implying flows.
2. **Aggregates** — exact `Decimal`, split per `currency` bucket (record-level
   amounts fall under `currency: null` → flagged `currency_unknown`): total,
   count, distinct count, min, max, and per account / bank / merchant groupings,
   each carrying the exact supporting `source_record_id` list (bounded; overflow
   marker when capped). **`inflow`/`outflow`/`net` are not computed** — they
   require direction, which the ingest does not supply; the payload records
   `net_flow: not_computable_no_direction` instead of a fabricated zero.
3. **Path tracing** (`trace_flows`): bounded DFS (depth ≤ `FLOW_TRACE_MAX_DEPTH`,
   paths ≤ `FLOW_TRACE_MAX_PATHS`, records ≤ `FLOW_MAX_RECORDS`, deadline
   checked between steps) over **association** edges, so a trace answers "what
   else is documented about this account", with every hop typed `association`.
   A `transfer`-kind trace is accepted as an API capability but returns
   `status: "insufficient_data"` with `reason: "no_transfer_edges_in_ingest"`
   — the trail is reported as absent, never guessed. Cycles are detected and
   reported as such.
4. **Pattern rules** (`FLOW_PATTERN_RULES_VERSION = "flow-patterns/1.0.0"`).
   Every rule is declared up front; each either **fires** with exact evidence or
   is returned **`not_evaluable` with the specific missing input** — a rule is
   never silently dropped, and never fires on absent data:
   - `duplicate_amount` — same exact `Decimal` amount in ≥2 distinct source
     records (evidence: the repeated `4500.00` / `12000.00` records).
   - `amount_threshold` — amount ≥ configurable investigation default
     (constant, not a universality claim).
   - `missing_currency` — amount present without currency attribution.
   - `missing_timestamp` — amount present without a time (excludes it from
     any windowed rule).
   - `victim_loss_unmatched` — a victim `reported_amount` exists while the
     case has no transaction-level facts covering it (cross-source gap).
   - `not_evaluable` (registered, reported, never fired): `rapid_succession`,
     `repeated_pair`, `circular_path`, `amount_splitting`, `concentration` —
     each carrying `reason` ∈ {`missing_timestamp`, `missing_direction`,
     `no_transfer_edges`} so the limitation is visible in the API/UI.
   Each candidate carries: rule id + version, input source-record ids,
   numeric evidence as exact strings, currency scope, missing-data
   limitations, source references, review status (`pending_review`). The
   payload states `pattern ≠ intent` for every firing rule.
5. **Result payload** (one `DerivedArtifact`, `kind="financial_finding"`,
   `origin="deterministic"`, `parser_version=FLOW_RULES_VERSION`): facts,
   aggregates, edges, patterns, limitations, and a `calculation_definitions`
   block explaining every derived number (mirrors Phase 3's
   `score_semantics` honesty). Content-hash dedupe makes resubmission
   idempotent (Phase 3 `record_artifact` semantics: canceled → no artifact).

### 4.3 AI explanation (advisory)

After the deterministic artifact exists and only if the local model is
configured: `AIService.explain_financial_flow(deterministic_summary)` — bounded
prompt containing only authorized deterministic facts (txn ids, amounts as
strings, times, statuses), instructed to: summarize the observed path, say why
each rule triggered, cite record ids, offer ≥1 alternative explanation, list
missing information, recommend verification steps. Server-side validation of
the response: every cited transaction id must exist in the deterministic
result; every quoted number must appear verbatim in the supplied facts
(citation service substring guard); schema-checked fields; on any failure the
explanation is **dropped and the failure surfaced** in the job summary
(`explanation_invalid`/`explanation_failed` counters) — a false result is never
asserted. Success stores a child artifact
(`kind="financial_finding"`, `origin="llm"`, `parent_artifact_id`, flagged
`ai_unverified`, `validation_status="flagged"`) exactly like Phase 3's
`pairs_llm`. The deterministic artifact is never modified.

### 4.4 API

- `POST /cases/{id}/evidence-intelligence/financial-flow` — submit the job
  (`ingestion.run`, read-only-case 409, one-active-job 409, idempotent key
  `financial_flow:{case}:a{N}`) — reuses `submit_case_feature_job`.
- `GET /cases/{id}/evidence-intelligence/financial-flow` — latest artifacts +
  job status (existing artifact/job listing with `feature` filter).
- `POST /cases/{id}/evidence-intelligence/financial-flow/trace` — read-only
  bounded trace for a selected account/txn (`case.read` + `evidence.read`);
  recomputes deterministically from authorized records; returns paths +
  limitations. No LLM on this path.
- `POST .../artifacts/{id}/review` — existing generic review route handles
  pattern approve/dismiss with the Phase 3 HTTP map + audit
  `derived_artifact.{decision}`.

### 4.5 Frontend

Financial Flow panel on the Analytics page (case-scoped, mirroring Phase 3
panel structure: loading/error/empty/retry/cancel states, a11y labels):

- scope + submit controls; run history with statuses;
- account selector (from computed aggregates); per-account per-currency
  totals with the calculation definition tooltips;
- edges/transactions table (time, amount + currency, status, from→to, source
  locator link navigating to the record);
- pattern cards (rule + version, evidence txn ids, limitations, review
  actions, visually distinct deterministic vs LLM blocks);
- path view with incomplete-link warnings;
- AI explanation block marked advisory with limitations; export note pointing
  at the existing artifacts/reports flow (payload is citation-complete).
Mock adapter mirrors the contract (deterministic sums computed in the mock
from seeded fixture rows — same arithmetic discipline).

## 5. Feature B — Cross-Case Pattern Discovery

### 5.1 Authorization scope (B1)

- New permission **`crosscase.read`** added to `app/core/rbac.py`
  (`ALL_PERMISSIONS` + INVESTIGATOR/ADMIN grants; ANALYST/VIEWER excluded).
  Because role permissions are code-derived from role names, **no data
  migration** is needed; existing DBs pick it up on deploy.
- Submission: `POST /api/v1/cross-case/discover` with an explicit bounded
  `case_ids` list (≤ `CROSSCASE_MAX_CASES`, default 25). Requires
  `crosscase.read` **and** per-case access to every listed case (404 for any
  inaccessible id — existence is never revealed; the response does not say
  which id failed, only that the scope is not fully permitted, matching the
  existing no-leak discipline). Full audit record
  (`cross_case.search_submitted`) with the authorized scope.
- The job is anchored to the requesting case (client passes the current case;
  AnalysisJob.case_id is NOT NULL — documented schema constraint). Idempotency
  key: `cross_case:{case}:h{scope-hash}:a{N}`.
- **Execution-time re-check** (delayed-job requirement): when the in-process
  runner executes, it re-verifies `crosscase.read` and every scope case for
  `actor_id`; any revocation → typed job failure `CROSS_CASE_SCOPE_REVOKED`
  (fail-closed; the job never silently shrinks scope and never returns partial
  cross-case data). `case.update` on any scope case → read-only refusal as in
  Phase 3 (the job produces no case mutation, so read-only cases remain
  searchable but unreviewable — documented).
- **Read-time re-check**: candidate reads filter per-case access again; a
  candidate referencing a case the reader cannot access is **omitted entirely**
  (no counts, no metadata, no existence hint). Audit:
  `cross_case.search_completed` with scope + candidate counts.
- No caching layer exists or is added; artifacts are authorized per request.

### 5.2 Candidate generation (B2) — deterministic, indexed, bounded

Permitted scope → for each case, load entity aliases + authorized source
records (capped) → extract **indicators** (pure functions, documented rules):

- kinds: `account_ref` (raw-data account aliases + transaction ids),
  `phone` (Phase 3 `PHONE_RE` normalization), `email`, `domain`, `url`,
  `device`, `txn_id`, `evidence_hash` (SHA-256 of evidence files), plus
  `reviewed_alias` (Phase 3-approved aliases).
- each indicator: `(kind, value_normalized, value_original, case_id,
  entity_id?, source_record_id?)`. Normalization is documented, lossless and
  kind-specific (e.g. phone digits-only with country-code preservation; email
  case-folded; domain lower-cased, `www.` stripped).
- **Indexing without all-pairs**: indicators are grouped in hash maps keyed by
  `(kind, value_normalized)` — O(n) grouping, no pairwise comparison across
  different values; cross-case pairs arise only from shared keys. Scope and
  per-kind caps bound memory (`CROSSCASE_MAX_INDICATORS` per case). *Why no
  persisted indicator table:* per-run extraction over ≤25 bounded cases needs
  no SQL-level join, avoids a migration without demonstrated need, avoids any
  stale-index state, and matches the Phase 3 in-memory-indexing precedent; a
  persisted indexed table is the documented extension path if scope grows.
- Only **completed/eligible** facts and **non-merged, active** entities
  contribute; conflicting attributes (e.g. different phone for the same email
  key's entities) are collected separately per group.
- Neo4j is not read (§3.3).

Each cross-case group (indicator shared by ≥2 distinct cases) becomes one
candidate artifact `kind="cross_case_link"` (`pending_review`, provenance =
both sides' `source_record_id`/`entity_id` + case ids, rule version
`crosscase/1.0.0`, caps on listed evidence per side with overflow markers).

### 5.3 Classification (B3)

`classification` is computed deterministically from the signal set:

- `exact_identifier` — raw values identical (e.g. same transaction id, same
  evidence hash).
- `normalized_identifier` — differ only by documented normalization (phone
  `+91 98765-43210` vs `9876543210`, VPA case, domain `www.`).
- `reviewed_alias` — at least one side carries a Phase 3-approved alias for
  the value (previously reviewed relationship reused as a signal).
- `similarity_name_only` — name similarity without any shared identifier.
  **Surfaced only as an informational category with review disabled** (server
  refuses approve with `NOT_REVIEWABLE`); it can never become an authoritative
  link. Name similarity alone is never a verified shared identity.
- `conflicting_attributes` (orthogonal flag) — both sides carry the same
  indicator *and* disjoint identifiers (e.g. different phones); shown as
  conflicting evidence on the candidate, never hidden.

Score, if shown, is a documented 0–100 **signal-strength band** (inputs: signal
kinds and counts), explicitly labeled not a probability.

### 5.4 AI explanation (B4)

`AIService.explain_cross_case_candidate(candidate_facts)` — only authorized,
already-retrieved facts from both sides; must explain the matching signal,
cite the actual supporting record ids per case, describe conflicts, state what
is *not* established, suggest verification steps. Server-side validation:
every cited id must exist on the candidate's own provenance lists (both sides
checked independently); schema check; failure → dropped + surfaced
(`explanation_invalid`), stored child artifact flagged `ai_unverified`. The
model cannot create, merge or promote anything.

### 5.5 Review workflow (B5)

Reuse Phase 3 review verbatim: generic artifact review route, typed HTTP map,
note-gated decisions, audit `derived_artifact.{decision}`. **Approval records a
reviewed cross-case relationship — it never merges entities, never writes
canonical relationships and never touches Neo4j** (no safe cross-case merge
workflow exists; Phase 3's additive-alias mechanism is per-case and stays
that way). The approved state is the artifact status + audit trail; the
resolution decision is appended as a child artifact (Phase 3 pattern). If a
future safe merge workflow lands, this artifact is its provenance source.

### 5.6 API + Frontend

- `POST /api/v1/cross-case/discover` (submit, §5.1);
  `GET /api/v1/cross-case/candidates?anchor_case_id=…` (read-time filtered);
  existing artifact review route for decisions.
- Cross-Case Intelligence panel on Analytics: scope selector ("my permitted
  cases", bounded), candidate list showing only permitted case references,
  indicator kind + original values from each side, source-record links per
  side, classification + score semantics string, conflict flags, graph-freshness
  note (stating discovery does not depend on the Neo4j projection), review
  actions and audit history. Inaccessible cases never rendered — not as names,
  ids, counts or badges.

## 6. Database and migration policy

**No schema migration is required for Phase 4.** Justification:

- `financial_flow`/`cross_case` job features already exist in
  `ANALYSIS_JOB_FEATURES` and the DB check constraint.
- `crosscase.read` is a code-level permission (roles table stores names only).
- Flow facts, aggregates, patterns and cross-case candidates live in
  `DerivedArtifact` payloads (JSONB, provenance-linked, reviewable) — same
  justification as Phase 3's three features.
- Indicator grouping is in-memory per run (§5.2); no queried indicator column
  needs an index because no cross-run indicator query exists.

Alembic head must remain `c5e2b8f4d9a3`; verified by gate.

## 7. Evaluation design (`scripts/eval_phase4.py`, `scripts/ai/eval_phase4.sh`)

Two sections like Phase 3: **golden (offline, always runs)** and **live
(end-to-end against the running stack; exit 2 on setup failure)**;
`--skip-live` runs golden only. Anti-vacuous by construction: every golden gate
requires a non-empty expected set, and a "no results for everything" build
fails the gates.

Financial golden fixture (synthetic, documented `n=` + limitations):
transfers across two currencies, a reversal, a pending/rejected pair, a
3-hop path, a cycle, a split pattern, a rapid-succession cluster, a one-sided
transfer, an unparseable-timestamp record, duplicate-looking records with
distinct txn ids. Independently hand-computed expectations embedded in the
fixture (`n=23` records, 2 victims, 1 schema-asserted `owns` edge).
Gates: exact-decimal totals per currency (independent recount),
currency segregation (no cross-currency sum ever emitted), status separation
(reversed/pending excluded from completed totals), path correctness + exact
supporting txn ids, source-locator validity for every cited record, pattern
precision/recall per rule (all five rules have ≥1 positive; negatives prove no
over-firing), incomplete-path marking (missing side never invented), limits
(depth/path caps enforced), determinism (identical replay byte-for-byte).

Cross-case golden fixture (synthetic, 3 cases, documented `n=`): exact-id
match, normalized phone match, VPA case match, reviewed-alias reuse,
name-similarity-only pair (must be non-reviewable), conflicting-attribute
group, evidence-hash match, plus decoy near-misses. Gates: candidate
precision/recall, classification correctness per candidate, name-only never
reviewable (payload carries `reviewable: false` + reason; the 409 server
refusal itself is API-tested and live-probed below), conflict flags present
where seeded, bounds (candidate / indicator / supporting-id caps),
single-case groups never emit candidates, determinism. The authorization
matrix (anon 401 / viewer 403 / analyst 403 / non-member 404 / partial-scope
refusal / revocation-after-submit typed failure / read-time omission of
inaccessible-side candidates) is enforced by the routes and covered by the
API test suite; the live section re-probes anon, viewer, scope-denied,
omission, name-only refusal and the approval audit row with real tokens
(§7.1), and scope consistency (candidate set ⊆ submitted scope) is enforced
at submit and read time by the routes.

Live section (real API + llama-server, synthetic data, cleanup after):
run both jobs end-to-end; verify flow totals against fixture-embedded expected
values via API + direct DB read; verify a cross-case candidate between two
cases, its approval trail, and unauthorized denial with a real viewer token;
verify explanation blocks (deterministic citation validation pass/fail paths);
measure and report per-feature latency with sample sizes. No accuracy claims
beyond fixture sizes.

### 7.1 Verified results (recorded by `eval_phase4.sh`, exit 0)

Measured on the live stack (local Qwen3 via llama.cpp, PostgreSQL-backed
API): **47/47 gates pass — 22 golden (offline) + 25 live** — over one full
run; the golden section alone passes offline with `--skip-live` (22/22).

Golden (deterministic replay over the frozen fixtures): financial — 22 facts
extracted from 23 records (the invalid amount counted and dropped, never
coerced), 3 currency buckets with exact totals `INR 13086.00 / USD 1424.99 /
currency_unknown 450.00`, 5 statuses separated, 10 declared rules = 5 firing
with the expected evidence + 5 `not_evaluable` with their missing input, 0
fired direction claims, network 21 nodes / 13 edges / 0 confirmed transfers,
and the bounded trace returning exactly the documented 5 maximal simple paths
(+3 at the depth cap, [] for an isolated node) — 0 aggregate, pattern,
locator, network or trace discrepancies. Cross-case — 17 groups / 6 shared →
6 candidates, 6 TP / 0 FP / 0 FN, every classification, score, conflict-flag
and per-side provenance byte-equal to the hand-computed expectation, name-only
non-reviewable, all 11 single-case decoys suppressed, bounds and determinism
hold.

Live (fresh cases per run, deleted afterwards): financial — job succeeded;
payload aggregates equal the golden fixture exactly (ids excluded — verified
by an independent PostgreSQL recompute over the same rows, byte-exact
including warnings); patterns match the golden set with the victim rule
honestly `not_fired` (a real case has no seeded victims); trace answers
`ok` for the association path (including the ACCU2 → Coastal Trust hop),
`insufficient_data{no_transfer_edges_in_ingest}` for `edge_kind=transfer`,
`not_found` for an unknown account; the cancellation probe landed
(accepted → `canceled` with **zero** artifacts → identical resubmission
succeeded); explain returned `422 AI_EXPLANATION_INVALID` (the model's reply
failed deterministic citation validation — the documented correct fallback,
reported, never gated); latency ≈1.0 s (1 s poll granularity). Cross-case —
scope {X,Y} yields exactly the 3 expected candidates (`account_ref`/`phone`
`normalized_identifier` score 56, `name/txn` `similarity_name_only` score 15
with `reviewable: false`); approving the name-only candidate is refused
live with `409 ARTIFACT_NOT_REVIEWABLE`; scope {X,Z} as admin shows Z-side
candidates while the investigator's re-read omits every Z id (3 items,
zero occurrences of case Z's id in any payload); scope-denied →
`404 CROSS_CASE_SCOPE_DENIED`, anon → 401, viewer → 403 at the permission
dependency (discover/candidates) and 403 `CASE_ACCESS_DENIED` on existing
cases the viewer cannot read (404 on a missing case — the documented
404-missing/403-IDOR split, no case content in either response); approval
leaves the parent's `content_hash` untouched, records a `recorded`
`reviewed_cross_case_link` child with a matching
`derived_artifact.approved` audit row (`reviewed_child_artifact_id`),
adds no entity aliases, and the generic artifact listing never returns
`cross_case_link` rows; latency ≈1.0 s. Cleanup verified in-report: all 4
synthetic cases + storage objects deleted, temporary VIEWER suspended.

## 8. Implementation sequence and commits

1. `docs(ai): add phase 4 design and graph consistency audit` — this document.
2. `fix(ai): project aliases and merges into the graph on approval` — §3.2
   targeted sync + call sites + integration/unit tests.
3. `feat(ai): add deterministic financial flow analysis` — extraction,
   aggregates, paths, patterns, job integration, backend tests.
4. `feat(ai): add financial flow api and analytics panel` — routes, trace
   endpoint, frontend panel + mock + tests.
5. `feat(ai): add permission-scoped cross-case discovery` — permission,
   submit/execute/read re-checks, indicator extraction, candidates,
   classification, backend tests.
6. `feat(ai): add cross-case review workflow and panel` — review wiring,
   explanation resolvers (both features), frontend panel + mock + tests.
7. `test(ai): add phase 4 evaluation harness` — golden + live, gates.
8. `feat(ai): add financial flow and cross-case intelligence` — final docs
   (verified results, limitations), remaining polish.

Every commit passes its gates before the next starts; failures are
investigated, never weakened.

As executed (`3065dc9..`), the numbered sequence held, with four
documented additions found by gates and live verification rather than
planned: `0a917c7 docs(ai): verify phase 4 transaction schema and narrow
feature a scope` (after step 1 — the A1 audit measurement narrowed A3/A4
before any code), step 6 shipped as two commits (`98180c0` review
workflow + explanations, `169282d` frontend panel), `bb946ed feat(ai):
add per-status flow totals` and `1615982 fix(ai): normalize evidence
hashes as cross-case keys` (findings surfaced by the phase-4 test suite
while steps 3–6 landed), and `607ef2a test(ai): verify phase 4 harness
against the live stack` after step 7 (live-section harness corrections
— §7.1 records what they revealed; every affected behavior was
re-verified correct in the product, not the harness).

## 9. Known limitations and blockers (pre-stated)

- No transaction table: facts are derived extractions from ingested records;
  coverage equals ingestion coverage (documented, not fabricated). Verified A1
  measurement over all 1000 dev records: **2 distinct amount-bearing
  transactions**, 207 account references, 0 transaction timestamps.
- **Directional fund-flow paths (A3) and time-windowed movement patterns (A4
  temporal half) are blocked**: `source_records` carries no financial columns,
  no payer-side key exists anywhere, and `relationships` has no transfer edge
  type — so nothing asserts "X moved money to Y" or "when". Implemented instead:
  association-structure analysis, exact aggregates, and pattern rules that
  report `not_evaluable{missing_direction|missing_timestamp|no_transfer_edges}`
  rather than firing or disappearing.
- Record-level amounts have **no currency attribution** (only
  `victims.currency` exists); sums are bucketed under `currency: null` with
  `currency_unknown` and are never labelled INR.
- Victim amounts (`reported_amount`, `amount_lost`, `recovery_amount`) are
  `double precision`; converted via `Decimal(str(value))` and flagged
  `precision: "float_source"` — exact-Decimal guarantees apply only to
  raw JSON string amounts.
- No reversal/refund linkage exists in the schema; cross-record reversal graphs
  are blocked and reported.
- No FX rates: multi-currency aggregates are always split; conversion refused.
- Account references are unvalidated strings; a normalized match is a
  *candidate signal*, never proof of account ownership.
- Cross-case approval records a reviewed relationship only; no canonical merge
  or graph edge (no safe workflow exists yet).
- Cross-case jobs are anchored to the requesting case (NOT NULL schema
  constraint); anchor-case deletion cascades the job row — documented.
- Neo4j is not read by Phase 4 features (§3.3); graph consistency is corrected
  at the write-trigger level (§3.2) and verified by tests.
- **Live-observed, recorded not gated**: on the live case mirroring the golden
  records the model's explanation was refused by deterministic citation
  validation (`422 AI_EXPLANATION_INVALID`) — the documented correct fallback
  (no unverified citation is ever emitted). A valid flagged explanation and
  this refusal are both acceptable outcomes; both paths are API-tested, and
  no accuracy or pass-rate claim is made about model output.
- Deterministic mention extraction derives organization mentions from
  transaction-id prefixes (e.g. `TXN-PH4-91` → organization `TXN`), so cases
  containing such ids share one short-name group. This surfaces as a
  legitimate `similarity_name_only` candidate held `reviewable: false` by
  classification and refused at approval with `409
  ARTIFACT_NOT_REVIEWABLE` (live-verified, §7.1) — informational rows in
  candidate lists are expected, not defects.
- Latency figures (§7.1) are single samples per feature per run, measured
  with 1 s job-polling granularity: they demonstrate end-to-end completion,
  not a performance envelope.
- Soup fine-tuning remains held pending explicit go-ahead.

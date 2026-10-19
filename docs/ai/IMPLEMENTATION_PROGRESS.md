# AI Implementation — Progress Checkpoint

**Repo:** `/home/xhroot/Documents/ai/CyberSaarthi` · **HEAD at prior checkpoint:** `8269313`
(Hardening commit). Stages 0–5 recorded §C; the Accuracy & Performance session
(§F, Stages A–E) began from a clean tree at `8269313`.

## A. Current state audit (this session, reverified — not trusted from docs)

| Check | Result |
|---|---|
| Git | clean at `9c17007`; no unstaged/staged changes at session start |
| llama-server | running, `/health` **200** |
| Completion | `content = 'pong'` (real, thinking-disabled) |
| Unauthenticated completion | **401** (API-key enforcement real) |
| UDS bridge | socket present, socat running |
| Backend container | healthy, `/api/v1/health` 200 |
| `docs/ai/` | RECOVERY_AUDIT, FEATURE_STATUS, LOCAL_MODEL_SETUP, ARCHITECTURE, SECURITY_AND_ISOLATION, API, EVALUATION, TROUBLESHOOTING, IMPLEMENTATION_AUDIT all exist |
| `docs/ai/IMPLEMENTATION_PROGRESS.md` | **was missing — created now (this file)** |

The three screenshot observations are genuine and re-confirmed.

## B. Honest gap list (what is NOT done, from FEATURE_STATUS 🟡 + code inspection)

1. **Retention purge never runs** ✅ done (Stage 1) — `AI_CONVERSATION_RETENTION_DAYS=90` is read
   into settings but no code deletes expired conversations (FEATURE_STATUS #44 🟡).
2. **No live integration test for the AI path** ✅ done (Stage 2) — the full backend run deselects
   1 integration test (readiness); no integration test exercises AI against the
   real llama-server.
3. **No automated eval harness** ✅ done (Stage 3) — EVALUATION.md §5 is design-only.
4. **`POST /ai/conversations` (empty thread) may lack a test** ✅ done (Stage 4) — verify.
5. **Soup** — blocked: host has Python 3.14.7 only, no 3.10–3.12 interpreter,
   no `soup-cli`, no instruction dataset. Instruction #10 says implement only
   after format+deps are verified → re-verify, do not implement.
6. Stream `tool` events carry no `ok`/`error` (frontend hardcodes `ok:true` for
   the transient chip; final truth comes from `done.tool_events`) — cosmetic.
   ✅ done (Stage 4).

## C. Work performed this session (stages, each saved + tested)

- **Stage 0** — audit + this checkpoint. ✅
- **Stage 1** — retention purge. ✅
  - Found `AIService.purge_expired()` already existed but **nothing called it**
    (FEATURE_STATUS #44 🟡 was accurate).
  - Fixed a real bug in my own first draft: `async with database.session_factory()`
    is invalid — an `async_sessionmaker` must be *called* (`factory()`) before
    use as a context manager (verified: `hasattr(async_sessionmaker,'__aenter__') == False`).
  - Wired into `main.py` lifespan: sweep once at startup + daily background
    `asyncio` task, cancelled on shutdown; both failure paths logged, never fatal.
  - Test: `test_retention_purge_removes_only_expired_threads` (ages a thread
    past the window, asserts purge count, survivor kept, FK-cascaded messages
    deleted) — **1 passed**.
  - Ruff + mypy clean on changed files.
  - **Live-verified**: inserted a 120-day-old conversation via psql, restarted
    the backend, log shows `AI retention sweep removed conversations` and the
    row is gone (`count=0`).
- **Stage 2** — live integration test `backend/tests/integration/test_ai_live.py`. ✅
  - 7 tests marked `integration`, all against the **real** llama-server with a
    real `AIService` (no monkeypatching): completion roundtrip (`pong`),
    grounded case chat (real sources + `grounded=True`), SSE token→done stream,
    outsider 403 on case chat, outsider 404 on foreign thread read/rename,
    message persistence (user+assistant rows), API-key header contract.
  - Fixed before first run: reachability probe hits `/health` directly (a fresh
    runtime's `ensure_ready()` can never succeed — its client is `None`);
    fixture forces `AI_MANAGE_SERVER=False` via `settings.model_copy` so tests
    can never spawn a second llama-server; API key loaded from repo-root `.env`
    (test venv doesn't see it); dropped `CaseMember(role="owner")` — violates
    the CHECK constraint (only collaborator/viewer), owner access comes from
    `owner_id`.
  - First run then **failed 6/7**: `app.state.database` never set —
    ASGITransport doesn't run the lifespan. Fixed by wiring
    database/graph_store/cache/storage/settings onto `app.state` in the fixture
    (same pattern as `tests/api/conftest.py`).
  - **Evidence: `7 passed in 5.31s`** with the server up (GPU-backed:
    llama-server holds 5986 MiB); `7 deselected` under `-m "not integration"`
    (default suite stays hermetic); skips with an actionable message when the
    server is down; teardown leaves **0** `liv%` users / **0** `LIVE-%` cases.
  - **Restart recovery this session:** host restarted mid-stage → llama-server
    dead + stale socket + orphaned socat. Restored with `rm -f
    ai_runtime/llama.sock`, `setsid -f scripts/ai/run_server.sh`, killed the
    orphan socat **by PID** (never `pkill -f` — the pattern matched my own
    shell once), `setsid -f scripts/ai/socket_bridge.sh`; end-to-end chat
    returns `pong` again.
- **Stage 3** — eval harness, implemented + run. ✅
  - Golden set `backend/tests/fixtures/ai_golden.jsonl`: **33 entries**
    (29 grounded across all 5 showcase cases incl. 2 graph-mode, 3
    foreign-case abstention→403, 1 unknown-case→404).
  - Runner `backend/scripts/eval_model.py` (venv + SQLAlchemy): real login,
    throttled `/ai/chat` (3.5 s, one 429-retry), citation validation against
    the DB **scoped to the evaluated case** (knowledge docs via allowlist),
    fact recall, abstention scoring, JSON report, exit 0/1/2. Entry point
    `scripts/ai/eval_model.sh`.
  - Guard test `tests/unit/test_ai_golden_fixture.py` — 10 tests pin counts,
    kinds, statuses, modes, showcase case numbers.
  - Fixed during bring-up (runner bugs, not test weakening): `CaseMember` has
    a composite PK (no `.id` → probe `case_id`); `vars()` invalid on
    `slots=True` dataclass → `asdict()`; `async_sessionmaker` misuse →
    `database.ping()`; `await` on non-async `_resolve_source`.
  - **Caught a real runtime bug**: showcase-case DATA blocks (~4350 tokens)
    exceeded the per-slot context — server ran `--ctx-size 8192 --parallel 2`
    and llama.cpp splits that to **4096/slot**, so every large-case chat
    failed `503 AI_UNAVAILABLE`. Fixed `scripts/ai/run_server.sh` to pass
    `--ctx-size $((CTX * PARALLEL))`; restart verified `n_ctx_slot = 8192`.
  - **Evidence (live run 2026-10-15): 33/33 PASS** — gates
    `{abstention_100pct, zero_ungrounded_answers, zero_invalid_sources}` all
    true; groundedness 1033/1033 cited sources resolve to the correct case;
    abstention 4/4; fact recall 49/53 (0.925); latency avg 741 ms / max
    2035 ms. Report: `ai_runtime/eval_report.json` (gitignored).
  - Honest misses recorded in EVALUATION.md §5: model misread the sorted
    entity digest on 2 top-entity questions (Delhi/59 → "Gaurav Joshi/13",
    Dehradun/67 → "Ludhiana/32"); 1 brittle-substring paraphrase
    ("registered" vs "registration"). Fact recall reported, never gated.
- **Stage 4** — test-gap pass. ✅
  - Verified: **no test hit `POST /ai/conversations`** (all 21 conversation
    references were GET/PATCH/DELETE). Endpoint exists (`routes/ai.py:91`,
    201 + case access check via `get_case_or_404`).
  - Added 6 API tests: empty-thread create (defaults: mode/title/status/
    prompt_version; thread readable and empty), owned-case binding
    (mode=case + case_id echoed), 401 unauthenticated, **403 foreign case**,
    **404 unknown case**, owner scoping (stranger gets 404 on read/rename/
    delete and sees no listing entry). **7 passed** (incl. pre-existing).
  - Closed audit gap 6: the stream `tool` event for a **fabricated/unknown
    tool** now carries `ok:false` + `error` (pre-execution events for valid
    tools stay ok-less — the result is genuinely unknown then); the frontend
    passes `event.ok`/`event.error` through instead of hardcoding `ok:true`
    (`api/real/index.ts`, `AiStreamEvent` extended).
  - New test `test_stream_unknown_tool_event_reports_failure_immediately`
    pins it: transient event ok:false + "unknown tool", final
    `done.tool_events` ok:false, no successful tool event anywhere.
  - Evidence: `tests/api/test_ai_api.py` **39 passed**; ruff + mypy clean on
    changed files; frontend `tsc -b --noEmit` + eslint clean.
- **Stage 5** — full re-runs + docs + commit. ✅
  - Backend hermetic: **542 passed, 8 deselected** (`-m "not integration"`,
    111 s). Integration (live llama-server): **8 passed** (7 AI live +
    1 readiness). Frontend: **110 passed / 18 files**, `tsc -b --noEmit` +
    eslint clean. Ruff over the whole backend: clean. Mypy `app/`: 140 files
    clean.
  - Eval re-run after the Stage-4 service change: **33/33 PASS**, gates all
    true; groundedness 1033/1033 (1.0); abstention 4/4; fact recall 0.9434
    (50/53 — natural variance vs 0.9245 on the first run, model is not
    seed-controlled); latency avg 629 ms / max 2400 ms. Report regenerated at
    `ai_runtime/eval_report.json`.
  - `docs/ai/FEATURE_STATUS.md` #44 🟡→✅ with the lifespan-sweep evidence;
    totals line corrected (was stale: real counts 42 ✅ · 2 🟡).
  - `docs/ai/EVALUATION.md` §5 rewritten: design → implemented + run evidence
    + honest misses + the ctx-per-slot bug the harness caught.

---

## F. Accuracy & performance session (2026-10-15, this session) — Stages A–E

New work: `docs/ai/ACCURACY_PERFORMANCE_PLAN.md` created with measured baselines.

### Stage A — deterministic entity ranking (accuracy fix). ✅ DONE
- **Root cause found:** `app/analytics` (`compute_centrality`, `pagerank`,
  `build_graph`) was **never imported by `app/ai/`** — the model was the only
  thing doing ranking, reading a sorted digest by eye. All 5 `*-top-entity`
  golden questions failed.
- **Fix:** new `app/ai/ranking.py` (authoritative, case-scoped; explicit metrics
  `relationship_count` / `distinct_neighbors` / `pagerank` / `degree`; typed
  record; deterministic tie-break value-desc/id-asc). New read-only
  `rank_entities` tool (`_authorize_case` re-checks access; returns typed record
  + entity-id sources). Prompt steers ranking questions to the tool and says
  report output verbatim. `service.py` pops `rank_entities` when no case.
- **Bugs caught in my own code:** `.items()` applied to the `_relationship_counts`
  coroutine before `await`; unused `ranking` import; unused `ids`; `case.id`
  (UUID) passed where `str` expected. All fixed; ruff + mypy clean.
- **Semantics finding:** PageRank on an all-outbound star ranks the *sinks*
  highest — a poor "most connected" proxy. Pinned by
  `test_pagerank_on_directed_sink_is_not_a_degree_proxy`. `relationship_count`
  counts relationship *rows* (matches digest's "59" and golden fact s001);
  model told to use `distinct_neighbors` only when the question says "distinct".
- **Regression tests** (`tests/unit/ai/test_ranking.py`, 11 tests): correct top,
  top-N order, deterministic ties, empty set, missing metric (raises, not
  substituted), unauthorized id (empty, no leak), non-active excluded, PageRank,
  sink semantics. Tool-registry test updated.
- **Verified live** (both metrics agree on all 5): 001 Delhi, 002 NDA Consultants,
  003 Nashik, 004 Vijayawada, 005 Dehradun. s001 `relationship_count` = Delhi(59) ✓
- **Live eval (model actually calls the tool):**
  fact recall **0.9434 → 1.0 (53/53)**; top-entity **0/5 → 5/5**; groundedness
  1.0 (held); abstention 4/4 (held); gates pass (held); avg latency 629→1017ms
  (+388ms, ranking questions only). Correctness-over-speed, only where a
  ranking is requested.
- **Suite:** backend hermetic **553 passed** (was 542, +11 new), integration
  **8 passed**, ruff clean, mypy clean (141 files). Frontend unchanged (110).

## D. Next task at this checkpoint

Stage 5: full re-runs and commit (see §C). Commands:

```bash
cd /home/xhroot/Documents/ai/CyberSaarthi
git log --oneline -1                      # expect 9c17007 or later
cd backend && .venv/bin/python -m pytest -m "not integration" -q   # hermetic
cd backend && .venv/bin/python -m pytest -m integration -q          # needs runtime
cd frontend && npm run test && npm run typecheck && npm run lint
./scripts/ai/eval_model.sh                # eval gates (exit 0 = pass)
```

Then: update `docs/ai/FEATURE_STATUS.md` #44 with evidence, `git add` the
session's files, commit (weights/secrets never staged).

Continue prompt: "Continue CyberSaarthi AI work from docs/ai/IMPLEMENTATION_PROGRESS.md,
next task = Stage 5 full re-runs + commit. Verify HEAD and runtime first."

## E. Session log

(append below as stages complete)

---

### Session: AI case-retrieval failure — root-cause audit and fix (2026-10-15)

**Task:** chatbot claimed a case "does not exist" when asked to summarize it by
case ID/name; appeared to see only a couple of empty cases. Production-blocking.

**Confirmed root cause** (proven by execution, NOT the LLM/DB/env/scoping — see
`docs/ai/CASE_RETRIEVAL_DIAGNOSIS.md`): four compounding defects in
`backend/app/ai/`:
1. `search_cases` read only `query` while the model emitted `case_id` → the
   user's filter was **silently dropped** → an unfiltered default window (10
   recent empty `heartbeat` cases for admin) → the requested case never
   returned. *This is where records disappeared.*
2. `_authorize_case` was UUID-only — a case number or name raised ValueError.
3. `get_case_summary` was disabled in general mode (`unknown tool`).
4. Tool results couldn't distinguish not-found / empty / error, so the model
   collapsed all three into "the case does not exist."

Environment ruled out: API total (117) == DB count (117); UI and AI share the
backend, DB, JWT principal and visibility predicate. Data ruled out: 0 orphaned
evidence/entities; SHOW-2026-001 fully populated (5 evidence / 247 entities /
6 timeline) and summarized correctly when bound by UUID.

**Fix** (smallest correct change, existing architecture):
- `search_cases` accepts `query|case_id|case_number|case_name|q|name|title`.
- New `resolve_case_reference()` + `_visibility_condition()` (single source of
  truth shared with the normal case API); `_lookup_case()` in tools re-runs
  `assert_case_access` as defense in depth.
- Case tools enabled in general mode (each resolves+authorizes its own ref).
- Structured `status` on `ToolExecutionResult`, surfaced to client (schema +
  route) and model; `get_case_summary` distinguishes empty vs missing via counts;
  DB failure → `lookup_error`. Honest general-mode prompt.
- `ai_service` fixture moved to `tests/api/conftest.py`.

**Tests:** new `tests/api/test_ai_case_resolution.py` (14 tests). Backend
hermetic **576 passed** (562+14), integration **8 passed**, frontend **110
passed** + tsc + eslint clean, ruff + mypy clean (141 files). **Eval 33/33 exit
0** (fact recall 1.0, groundedness 1.0, abstention 4/4).

**Live proof** (after `docker compose restart backend` — uvicorn runs without
`--reload`, so restart is mandatory for code changes):
- "Summarize case SHOW-2026-001" (admin) → real summary, both tools
  `case_found_with_data`, source SHOW-2026-001. Was: "does not exist".
- "Summarize case SHOW-2026-003" (investigator) → real summary (243 entities).
- "Which cases do I have access to?" (investigator) → lists 5 showcase cases.
  Was: "you have no cases".
- Cross-tenant probe (investigator → CS-CF503AE6) →
  `case_not_found_or_not_accessible`, honest "not accessible to your account…
  does not prove it does not exist." **No leak.**

**Flagged for ingestion owner (outside AI tool path):** the 104 `CS-*`
NULL-owner cases are empty shells (`owner_id` NULL → invisible to non-admins,
never populated).


---

## 2026-10-16 — AI Expansion Phase 0 + Phase 1 (Think mode)

**Phase 0 audit** recorded in `docs/ai/AI_EXPANSION_AUDIT.md` (HEAD `f983883`).
Key reconciliations: the "Analysis page" is the `/analytics` route; Think maps
onto the existing `deep` profile (Stage B budget machinery reused, not
duplicated); hypothesis confidence is an explicit heuristic
(`0.35 + 0.15*neighbors`) that must never be relabelled as a probability.

**Phase 1 — Quick/Think mode:**
- `AiProfile` gains `think`: same budget as `deep` (`AI_PROFILE_DEEP_*`, one
  source of truth) plus `AnswerProfile.structured`.
- Think structured-response contract (`prompts.THINK_STRUCTURE`): Rationale /
  Facts (cited) / Uncertainty / Alternative explanations / Open questions —
  explicitly a presentation contract, never hidden chain-of-thought, never a
  widening of tools or record scope.
- New SSE `progress` events (`retrieving` | `synthesizing`, profile + iteration
  counters) streamed to the client; frontend shows live status instead of a
  bare spinner.
- Context-budget enforcement: `_clamp_history_to_budget()` drops oldest
  history turns first when prompt + max_tokens would exceed the per-slot
  `AI_CONTEXT_LENGTH`; system prompt, case data and current question are never
  truncated.
- Cancellation: client Stop/disconnect closes the SSE generator, whose
  `finally` cancels and awaits the in-flight generation (contract now tested).
- Frontend: Quick/Think segmented toggle in the floating assistant, `profile`
  on every request, `onProgress` callback wired through contract → real adapter.
- **Tool-loop defect found and fixed (pre-existing since Stage B):** if the
  model emitted a tool fence on its last allowed round, the raw fence was
  returned verbatim as the answer (live-confirmed: quick "summarize
  SHOW-2026-001" answered with JSON). Now the last in-budget round still
  executes the authorized tool and forces one answer round
  (`FINAL_ROUND_NUDGE`); if the model fences again the API fails closed with an
  honest 503 instead of leaking the fence. Bounded: at most
  `tool_iterations + 1` completions.

**Tests:** backend hermetic **595 passed** (591+4 tool-loop + cancellation test
in unit), integration **8 passed**, frontend **110 passed** (18 files) + tsc +
eslint clean, ruff + mypy clean (141 files).

**Eval:** `./scripts/ai/eval_model.sh` → **33/33, exit 0**; gates
`abstention_100pct`, `zero_ungrounded_answers`, `zero_invalid_sources` all
true; fact recall **1.0** (53/53), groundedness **1.0** (1043/1043),
abstention 4/4; latency avg **1011 ms**, max 3196 ms over 29 completions.

**Live (after `docker compose restart backend`, llama-server 200):**
- quick "Summarize case SHOW-2026-001" → grounded 506-char answer, 2 tool
  calls, no fence, wall 2349 ms (was: raw tool fence).
- think same question → structured Rationale/Facts answer, 1434 chars,
  grounded, wall 4057 ms.
- Both streams emitted `progress: retrieving → synthesizing`.
- Server config unchanged: `--ctx-size 16384 --parallel 2` (8192/slot); no
  context, parallelism or model changes.

**Known limitations:** Think wall time is ~1.7× quick on showcase questions
(measured, n=1 per mode — not a statistical claim); progress phases are coarse
(two states); the forced-answer round adds at most one extra completion when a
model refuses to stop calling tools.

---

## 2026-10-16 — AI Expansion Phase 2 (Analysis-page AI panel)

**Backend — `analysis` mode in the existing gateway (no second gateway):**
- `AiMode` gains `analysis`; DB check constraint extended via migration
  `b4f1c2d3e4a5` (applied; downgrade demotes analysis threads to `general`).
- Prompt contract (`SPECIALIZED["analysis"]`): five sections — observed facts /
  deterministically computed metrics / AI interpretations / hypotheses &
  uncertainty / missing evidence & next steps. The model interprets only;
  every number must be a verbatim echo of DATA, failures must be reported as
  failures, absent analytics must be stated as not computed. Think's generic
  structure is suppressed for this mode (the mode owns its structure).
- Context: analysis mode adds evidence + graph + analytics digests (existing
  `build_case_context`, existing caps).
- **Server-side claim validation** (`retrieval.validate_cited_claims`), run on
  the final answer and returned as `citation_check` on `/ai/chat` and the SSE
  `done` event: (a) every UUID in the answer must appear in the shown DATA or
  the response sources → `unverified_ids`; (b) each quoted metric
  (`metric=<name> entity_id=<id> value=<v>` DATA-echo form, strict
  `@`-grammar also accepted) is looked up in `metric_results` for the case —
  unknown pair or value off the stored raw (tol 1e-5 relative / 0.005 floor)
  or normalized score (tol 0.01) → `metric_claims_mismatched`. Advisory
  metadata: never raises, never fakes a pass.
- Output floor: analysis mode `max(max_tokens, 1024)` — measured: deep's 768
  truncated live runs after section 3 of 5. Context size/parallelism/model
  untouched. Prompt also caps quotes at five metrics (all stated numbers stay
  machine-checkable).

**Frontend — Analysis panel on `/analytics`:**
- `AnalysisPanel` card (no new route): six preset questions (interpret metrics,
  anomalies, timeline & entities, contradictions & gaps, alternative
  explanations, next steps) + a Report-draft action reusing the existing
  `reportDraft` endpoint. Requests `mode: "analysis"`, `profile: "think"`,
  streams with progress states, Stop button aborts (cancels server-side).
- Renders: answer (Markdown), source chips, tool statuses, grounded warning
  when no authorized sources were retrieved, and the `citation_check` strip —
  pass line only when the server actually checked and found no issues;
  otherwise unverified ids and metric mismatches listed as warnings; check
  absent → "not available" (never a fake pass). Every run resets prior output
  so a failed run can never display a stale answer as its own result.
- Contract: `AiChatInput.mode += analysis`, `AiCitationCheck`,
  `AiChatResult.citation_check`, `onDone.citation_check`;
  `AiToolEvent.status` now also forwarded on transient `tool` events (was
  dropped by the adapter).

**Tests:** backend hermetic **611 passed** (11 analysis-mode API + 3 prompt/budget
incl. fixture consolidation of `_owned_case`/`_stranger_case` into
`tests/api/conftest.py`), integration **8 passed**, frontend **119 passed**
(19 files, 9 new panel tests) + tsc + eslint, ruff + mypy clean.

**Eval:** 33/33, exit 0; gates all true; fact recall 1.0 (53/53),
groundedness 1.0 (1053/1053), abstention 4/4; latency avg **807 ms**, max 1909.

**Live (backend restarted; llama-server + UDS bridge restarted after stack
restart — ctx 16384 / parallel 2 confirmed, VRAM 7295/12288 MiB):**
- analysis + think on SHOW-2026-001: all 5 sections present, 2357 chars,
  grounded, 48 sources, `citation_check` = 4/4 ids verified, 4 metric claims
  checked, 0 mismatches; wall ~9.8 s (single run, not a statistical claim).
- First live iteration exposed two gaps that were then fixed and re-tested:
  models echo DATA's field syntax rather than the synthetic `@` grammar (0
  claims checked) → validator now accepts the echo form; 768-token budget
  truncated the contract → 1024 output floor.

**Known limitations:** claim check is advisory (ids from tool results not
re-holding can be flagged unverified for review); numeric validation covers
the mandated metric grammar, not free-prose numbers (eval gates handle the
golden set); no aggregate stats on panel latency (n=1 per observation).

---

## 2026-10-16 — AI Expansion Phase 3 (Hypotheses-page AI, honest confidence semantics)

**Backend — `hypothesize` mode in the existing gateway:**
- `AiMode` + conversation constraint gain `hypothesize` (migration `c8e2f4a6b1d3`,
  applied; downgrade demotes such threads to `general`).
- Prompt contract (`SPECIALIZED["hypothesize"]`): up to three falsifiable,
  non-committal candidates, each a fenced `hypothesis` block of strict JSON
  (title / statement / evidence_ids / refutation / missing). Evidence ids may
  only come verbatim from DATA or tool results; **numeric confidence,
  percentages and odds are forbidden** — uncertainty is expressed in words.
- Context: evidence + graph + victims + entities/findings/timeline —
  **analytics deliberately excluded** so heuristic/graph scores can never be
  laundered into a draft's "confidence".
- Strict parsing (`app/ai/drafts.py`): invalid blocks are counted, never
  repaired; ids are UUID-validated, deduped, capped (MAX_DRAFTS=5,
  title 255, statement 4000). Each draft's ids are diffed against the
  machine-verified known set (`known_uuids` = shown DATA ∪ response sources)
  → `unverified_ids` per draft. `hypothesis_draft_errors` counts every
  rejected/over-cap block so a partial tray is never silent.
- Response/SSE carry `hypothesis_drafts` + `hypothesis_draft_errors`;
  `citation_check` (id verification) now also runs for this mode.

**Honest-semantics guarantees (pinned by tests, verified live):**
- A suggestion run **writes zero rows** — drafts are proposals only; nothing
  becomes a stored hypothesis without a human clicking Record and submitting
  the normal form (status starts at `proposed`, submitted_by = the human).
- No numeric confidence is produced anywhere (prompt-forbidden, parser never
  extracts one, UI never renders one).
- AI drafts cannot become findings: the findings pipeline is untouched and
  the hypothesis status machine remains human-driven.

**Frontend — `HypothesisSuggest` tray on `/hypotheses`:**
- "Suggest hypotheses" runs `mode: "hypothesize"`, `profile: "think"`, with
  progress, Stop, error state, grounded warning, and a full reset per run.
- Tray cards show title, statement, cited-record chips (each marked
  "retrieved" or "⚠ unverified" per server verification), the refutation
  test, and the records missing to test. Per-draft "Record…" (reviewers only)
  pre-fills the editable create form with an AI-provenance note — nothing is
  written until the human submits.
- Partial trays are labelled with the rejected-block count; the raw model
  output is always inspectable (`<details>`). Header states the contract:
  unverified prompts for investigation, no probability computed, nothing
  recorded without review.

**Tests:** backend hermetic **631 passed** (8 hypothesize API + 13 parser
unit), frontend **127 passed** (20 files, 8 new), integration **8 passed**,
ruff + mypy clean (142 files), tsc + eslint clean.

**Eval:** 33/33, exit 0; gates all true; fact recall 1.0 (53/53),
groundedness 1.0 (1053/1053), abstention 4/4; latency avg **792 ms**, max 2603.

**Live (backend restarted):** hypothesize + think on SHOW-2026-001: 3 drafts,
0 parse errors, 5/5 cited ids verified, 0 unverified ids, zero
confidence/probability wording (asserted), 37 sources, wall ~5.4 s (n=1);
`hypotheses` table for the case left at 0 rows after the run.

**Known limitations:** parsed tray quality depends on the model following the
fence contract (violations are counted and shown, never silently dropped);
draft statements are model-authored prose and always require human review
before use; no aggregate latency stats (n=1 per observation).

---

## 2026-10-16 — AI Expansion Phase 4 (eval/security extension)

**Golden set (`backend/tests/fixtures/ai_golden.jsonl`): 33 → 41 entries**
(kind counts pinned in `tests/unit/test_ai_golden_fixture.py`):
- 2 `analysis` entries — five-section contract + metric-quote verification.
- 2 `hypothesize` entries — draft parsing and honesty gates.
- 1 `grounded` entry with `profile: "think"` — Phase 1's think path is now
  exercised by the eval.
- 3 cross-mode security abstentions: `analysis` on a foreign case → 403,
  `hypothesize` on a foreign case → 403, `analysis` on a nonexistent case →
  404 (fail-closed authorization verified live across the new modes).

**Harness (`backend/scripts/eval_model.py`) — new scorers + gates:**
- `_score_analysis`: sources resolve to the case (DB-verified, not
  server-reported) + all five sections present (case-insensitive) + **every
  metric quote re-verified against `metric_results`** (raw tol 1e-5 relative
  / 0.005 floor, score tol 0.01). `relationship_count` quotes — printed
  verbatim by the entities digest but not a metric_results row — are verified
  against the `relationships` table with the same count semantics as DATA
  (measured: a002 quoted 5 such values and all 5 verify; a wrong value or an
  invented metric name still fails).
- `_score_hypothesize`: fail-closed by construction — no sources fails; a
  tray that parses nothing fails (no vacuous pass); rejected fence blocks
  fail; every draft evidence id must resolve to a row of this case in one of
  the record tables (case/entity/evidence/finding/relationship/timeline/
  victim) else fail; numeric confidence / probability / odds / percent
  wording in a draft fails (qualitative hedging allowed, matching the
  prompt's ban).
- New gates, both vacuous-pass-proof (require ≥1 entry of the kind):
  `analysis_all_pass`, `hypothesis_all_pass`. Groundedness/ungrounded/
  invalid-source checks now aggregate over all answering kinds.
- Report/summary lines for sections missing, quotes verified/bad, drafts
  parsed/rejected, honesty issues.

**Backend fix found by the new gate (measured, not guessed):** the first
extended run failed `analysis_all_pass` — a002 relabeled the entities-digest
`relationships=N` count into metric grammar and was reported "no such
metric". Both validators (gateway `validate_cited_claims` + harness) now
verify `relationship_count` against the relationships table (per-claim
checking: true count passes, wrong count fails, invented names still fail);
the analysis prompt now says metric names come verbatim from DATA — an
analytics metric name or `relationship_count` — never invented.

**Tests:** backend hermetic **638 passed** (+1 relationship-count API test,
+6 golden-fixture guards: entry counts, new-mode entry shape, cross-mode
abstention coverage, think entry, quote regexes, confidence-gate wording,
fail-closed `_record_belongs_to_case`), integration **8 passed**, frontend
**127 passed** + tsc + eslint, ruff + mypy clean (`app/` 142 files +
`scripts/eval_model.py`; 4 pre-existing mypy errors in untouched
`scripts/preview_analytics.py` / `scripts/seed_showcase_cases.py` remain
outside the gate, unchanged).

**Eval (41 entries, real exit code captured): exit 0, passed True** —
gates: abstention 7/7, zero ungrounded, zero invalid sources,
`analysis_all_pass` 2/2 (9 metric quotes re-verified, 0 bad, 0 sections
missing), `hypothesis_all_pass` (4 drafts, 0 rejected, 0 honesty issues);
fact recall 0.9815 (53/54 — one think-entry miss, reported not gated);
groundedness 1.0 (1260/1260); latency avg 1561 ms, max 11189 over 34
completions (includes the two think/analysis runs; n per entry = 1).

**Known limitations:** fact recall is substring-based (reported only, as
before); draft-id verification is DB membership, not content relevance;
`relationship_count` is the only non-metric_results name accepted — any
other relabeled name fails by design (prevents heuristic-score laundering);
single-run latency figures are not statistical claims.

---

## 2026-10-16 — AI Expansion Phase 5 (quality gates & delivery)

**Delivery:** phases 1–5 complete, one commit per phase, on base `f983883`:
`6becdf4` (think mode) → `45a8767` (analysis panel + claim checks) →
`b156f87` (hypothesis drafts, honest confidence) → `3591005` (eval/security
extension) → this commit (gates + docs). Phase 0 audit:
`docs/ai/AI_EXPANSION_AUDIT.md`.

**Final gate battery (all after the last code change; backend container
restarted with the final code before the eval ran through it):**
- Backend hermetic: **638 passed**, 8 deselected; integration: **8 passed**
  (llama-server + UDS bridge up: ctx 16384 / parallel 2).
- Frontend: **127 passed / 20 files** + `tsc` + `eslint` clean.
- ruff clean (`app/`, `scripts/eval_model.py`, `tests/`); mypy clean
  (`app/` 142 files + `scripts/eval_model.py`; 4 pre-existing errors in
  untouched `scripts/preview_analytics.py` / `scripts/seed_showcase_cases.py`
  remain outside the gate, unchanged by this work).
- Eval (delivery run, real exit code): **41/41, exit 0, all 5 gates true** —
  abstention 7/7, groundedness 1.0 (1260/1260), analysis 2/2 (9 metric quotes
  re-verified, 0 bad), hypothesis 4 drafts / 0 rejected / 0 issues; fact
  recall 0.9815 (53/54, reported not gated); latency avg 1633 ms, max 9195
  over 34 completions (n=1 per entry).

**Docs refreshed for delivery:** `docs/ai/EVALUATION.md` §5 now documents the
41-entry golden set, both new scorers, the five-gate contract and the
2026-10-16 run evidence (the 2026-10-15 three-gate run kept as history); the
revert row lists the actual phase/migration commits. Dated baseline docs
(`ACCURACY_PERFORMANCE_PLAN.md`, `CASE_RETRIEVAL_DIAGNOSIS.md`) left anchored
to their stated dates by design.

**Artifact hygiene (verified at commit):** no `*.gguf`, `.env`,
`ai_runtime/`, weights or secrets tracked (only the `.env.example` template);
eval report and runtime stay gitignored.

**Carried-forward items (outside AI scope, unchanged):** Soup fine-tuning
remains blocked (no Python 3.10–3.12 interpreter, no dataset, multi-GB
downloads) and awaits an explicit go-ahead; 104 `CS-*` `owner_id=NULL`
empty-shell cases remain flagged for the ingestion owner.

**Known limitations standing after delivery:** claim check and draft
verification are advisory machine checks, not proofs — unverifiable ids are
surfaced for human review, never silently passed; fact recall is substring
matching (reported only); no numeric confidence exists anywhere in the AI
path by design; all latency/eval figures are single-run measurements, not
statistical claims.

## 2026-10-19 — AI Expansion Phases 5A/5B/6/7 (multilingual, triage, report audit, final integration)

Commits (chain from `6a128cf`): `2188527` multilingual complaint
intelligence → `4447609` digital forensics triage → `bfa3171` AI report
auditing → `test(ai): complete final AI integration and evaluation` →
`docs(ai): finalize AI expansion status and delivery`.

Verified at delivery (numbers, not adjectives):

- **Combined eval** `scripts/ai/eval_final.sh`: **147/147 gates, exit 0**
  (golden + live, 215 s); per-harness gates 5 / 3 / 16 / 47 / 64 + 12
  cross-cutting; all 10 features measured (golden `n=` or live run);
  alembic head unchanged (`c5e2b8f4d9a3`); anonymous error-shape probe 401
  `{"error": {code, message}}`.
- **Backend:** 1048 tests passed (hermetic + integration); `ruff check .` /
  `ruff format --check .` (290 files) / `mypy` (177 files) clean.
- **Frontend:** 216/216 tests, lint, typecheck and production build green.
- **Security added this phase (report audit):** anonymous 401 on
  submit/list/detail with nothing queued; mid-run permission revocation
  fails closed (`CASE_ACCESS_DENIED`, extraction ran but no assessment call
  and no artifact); prompt-injection draft cannot approve the artifact or
  suppress deterministic findings.
- **Docs:** `FEATURE_STATUS.md` §F (10-feature matrix with evidence),
  `PHASE_5_6_7_PLAN.md` §7 outcomes, `EVALUATION.md` §5 extension.
- **Live-gate incident, root-caused and fixed (2026-10-19):** the first two
  delivery runs of `eval_final.sh` failed `p1_analysis_all_pass` (145/147):
  `a001-analysis-interpret` was cut mid-sentence, missing 2/5 then 1/5
  required sections. It looked stochastic (answers differed per run), but the
  llama-server slot logs exposed **two distinct truncation walls**, and the
  same gate caught both:
  1. *Retained-prefix context wall* — failing runs ended at slot
     `n_tokens = 8191, truncated = 1` with **exactly 963 generated tokens**;
     the one passing run finished at 8142 (49 tokens of headroom). A reused
     slot retains a shared KV prefix (~4.6k tokens), shrinking headroom below
     the 1024-token analysis budget. Fixed in `scripts/ai/run_server.sh`:
     per-slot context doubled (`--ctx-size $((CTX * 2 * PARALLEL))`,
     `n_ctx_slot = 8192 → 16384`, VRAM 9 837 MiB / 12 GiB).
  2. *Output-budget truncation* — a third run still failed after the ctx fix,
     but at `n_tokens = 8252, truncated = 0` (no context wall): a verbose,
     UUID-heavy answer hit exactly `max_tokens = 1024` and was cut
     mid-section-3, dropping sections 4–5. `ANALYSIS_MIN_MAX_TOKENS` in
     `app/ai/service.py` (already raised once, 768 → 1024, for this reason)
     raised 1024 → 2048 — only the output allowance changes; context, model
     and parallelism untouched.
  After both fixes: phase-1 5/5, slot usage ≤ 7 956, zero truncation; combined
  eval **147/147, exit 0**. The evaluation gate was never weakened — it
  correctly failed all defective runs. Known limitation standing: the AI
  client does not surface `finish_reason`, so a future hit would again present
  as a short answer rather than an explicit truncation error.
- **Stochastic observation (honest):** one frontend test failed in a single
  run that executed concurrently with the full 1048-test backend suite;
  three subsequent standalone runs were green (216/216). The failing test
  name was lost to output truncation and did not reproduce.
- **Unchanged:** Soup fine-tuning not attempted — still awaits an explicit
  go-ahead; no model re-downloads; no migrations added in 5A/5B/6/7.

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

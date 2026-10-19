# AI Feature Status Matrix

**Date:** 2026-10-15 · **AI expansion (Phases 3–7) verified:** 2026-10-19 ·
**Evidence basis:** live stack + automated tests run this
day. Every "✅" below maps to a reproducible check (command or test name); nothing
is marked done on assertion alone.

Legend: ✅ verified working · 🟡 works with a documented limitation ·
⚪ not implemented · 🔴 blocker

## A. Inference runtime (local, no cloud)

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | Local llama.cpp server, CUDA build, existing `Qwen3-8B-Q4_K_M.gguf` (no re-download, no Ollama) | ✅ | `verify_model.sh` step 1–3; `ai_runtime/llama.cpp/llama-server` from release `b11617`; model file 5 027 783 488 B at repo root, never re-fetched |
| 2 | GPU offload on the RTX 3080 12 GB, verified for real | ✅ | `nvidia-smi --query-compute-apps` → llama-server pid 43961 @ 5986 MiB; `nvidia-smi` → 96 % util during generation |
| 3 | Throughput / latency measured on real completions | ✅ | 178.8 tok/s, first_token_ms 23 (`verify_model.sh` §4); grounded API turn 1 161 ms |
| 4 | Qwen3 thinking-mode disabled (answers land in `content`) | ✅ | `chat_template_kwargs: {"enable_thinking": false}` in client + verify script; "pong" returns real content |
| 5 | Inference server reachable from the Dockerized backend | ✅ | `socat` UDS bridge `ai_runtime/llama.sock`; container health probe `ready: True` |
| 6 | Runtime supervision from the app (managed mode) | 🟡 | `AI_MANAGE_SERVER` + spawn/health code exist and are unit-tested; in this deployment the server is a host process (compose sets `AI_MANAGE_SERVER=false`) because the container has no GPU. Managed mode is code-verified, not the live path |
| 7 | VRAM/GPU metrics in `/ai/status` | 🟡 | Host: full stats. Container: `null` (no `nvidia-smi` inside) — documented limitation, never fabricated |

## B. Gateway API (`/api/v1/ai/*`, browser→backend only)

| # | Feature | Status | Evidence |
|---|---|---|---|
| 8 | `GET /ai/status` — runtime readiness, tools, feature flags | ✅ | live 200 with token; **401 without** (was a real gap, fixed this session) |
| 9 | `POST /ai/chat` — grounded completion, creates + persists a conversation | ✅ | live: 346 ms general turn; case turn 1 161 ms / 39 sources (24 case-scoped) |
| 10 | `POST /ai/chat/stream` — SSE `token → sources → done` | ✅ | live: 26 token events, first_token_ms 364, `done` carries answer + conversation_id |
| 11 | Multi-turn conversations (`conversation_id` threading, history reload) | ✅ | live follow-up reused the thread; history endpoint returned 4 messages `user/assistant/user/assistant` |
| 12 | Conversation management: list, get, rename, delete | ✅ | live rename 200; `test_list_and_delete_owned_conversations`, `test_rename_conversation_is_owner_scoped` |
| 13 | `POST /ai/report-draft` — grounded draft | ✅ | `test_report_draft_owner_ok_stranger_denied` + live E2E in the lost session (53 sources) |
| 14 | Tool loop (≤3 iterations, unknown tools refused, errors fed back to the model) | ✅ | live tool turn: fence → `search_cases` ok → answer; `test_tool_loop_executes_and_reports_events`, `test_unknown_tool_from_model_is_reported_not_executed` |
| 14b | Knowledge-mode requires `search_knowledge` before answering (no memory-guessing) | ✅ | **fixed this session** after a live-found hallucinated citation; `test_knowledge_mode_requires_tool_lookup_before_answering`; re-ask live → tool called, 4 real docs cited |
| 15 | Per-user rate limit (Redis fixed window, scoped per user) | ✅ | `test_rate_limit_returns_429`, `test_rate_limit_counters_are_scoped_per_user` |
| 16 | Graceful degradation: disabled → 503 `AI_DISABLED`, runtime down → 503 `AI_UNAVAILABLE` | ✅ | `test_disabled_ai_returns_503`, `test_model_failure_returns_503`, `test_stream_model_failure_emits_error_event` |
| 17 | Mid-stream client cancellation safety | ✅ | live: aborted SSE after 64 B → server healthy, next request 200 |

## C. Security & isolation (the 12 Stage-6 categories, all real tests)

| # | Category | Status | Test (in `tests/api/test_ai_api.py`) |
|---|---|---|---|
| 18 | AI status requires authentication | ✅ | `test_status_requires_authentication` |
| 19 | Malformed/forged token rejected | ✅ | `test_malformed_token_is_rejected` |
| 20 | Rename is owner-scoped (stranger → 404) | ✅ | `test_rename_conversation_is_owner_scoped` |
| 21 | Model/runtime failure ≠ 500 leak (maps to 503) | ✅ | `test_model_failure_returns_503` |
| 22 | Stream errors surface as `error` events, never raw exceptions | ✅ | `test_stream_model_failure_emits_error_event` |
| 23 | Prompt injection inside case data stays fenced (DATA block) | ✅ | `test_prompt_injection_in_case_data_stays_fenced` |
| 24 | User-input injection cannot bypass case authz | ✅ | `test_prompt_injection_user_input_cannot_bypass_case_authz` |
| 25 | Model-forged tool call for foreign evidence fails closed | ✅ | `test_unauthorized_evidence_tool_call_is_denied` |
| 26 | Session switching between accounts stays isolated | ✅ | `test_session_switching_between_users_is_isolated` |
| 27 | Concurrent requests from different accounts stay isolated | ✅ | `test_concurrent_requests_from_different_accounts_stay_isolated` |
| 28 | Case access re-checked after permission change | ✅ | `test_case_access_is_rechecked_after_permission_change` |
| 29 | Rate-limit counters scoped per user | ✅ | `test_rate_limit_counters_are_scoped_per_user` |
| 30 | Case-scoped chat denies non-members (403) | ✅ | `test_outsider_case_chat_is_denied` + live E2E |
| 31 | Foreign conversations hidden (404 on read/rename/delete) | ✅ | `test_conversation_ownership_is_isolated` + live E2E |
| 32 | Read-only tools only (no writes/deletes exposed to the model) | ✅ | `tools.py` registry: `search_cases`, `get_case_summary`, `list_evidence`, `get_entity`, `get_timeline`, `get_analytics_summary`, `search_knowledge` — all read-only; `test_tool_loop_executes_and_reports_events` |

## D. Frontend (floating chatbot)

| # | Feature | Status | Evidence |
|---|---|---|---|
| 33 | Floating assistant mounted in the app shell (all routes) | ✅ | `app-shell.tsx` mount; `assistant.test.tsx` |
| 34 | Streams tokens live; `tool` events clear the raw fence (no JSON leak) | ✅ | **fixed this session** — mock reproduces the fence; `never renders the raw tool fence…` test; live fence capture in `RECOVERY_AUDIT.md` §4 |
| 35 | Multi-turn (passes `conversation_id`; uses `done.conversation_id`) | ✅ | `reuses the conversation id for follow-up messages` test; live follow-up |
| 36 | History view: list, load thread, case filter, rename, delete w/ confirm | ✅ | `history`/`rename`/`delete…` tests (19 in `assistant.test.tsx`) |
| 37 | Markdown + fenced code rendering with copy button (no `dangerouslySetInnerHTML`) | ✅ | `markdown.tsx` + 5 tests in `markdown.test.tsx` |
| 38 | Copy answer, regenerate, stop/abort, per-message retry on error | ✅ | `copies an answer…`, `regenerates…`, `stops an in-flight generation`, `shows stream errors inline…` tests |
| 39 | Offline/unreachable-runtime banner with re-probe | ✅ | `shows the offline banner and re-probes status on retry` test |
| 40 | Accessibility: labelled buttons, `aria-live` answer region, Esc closes | ✅ | component attributes + Esc/focus test |
| 41 | Mock adapter parity (full AI surface for demo mode) | ✅ | deterministic thread store incl. tool-loop stream; 110 frontend tests green with `VITE_USE_MOCK_API=true` |

## E. Data layer

| # | Feature | Status | Evidence |
|---|---|---|---|
| 42 | `ai_conversations` / `ai_messages` models + Alembic migration `36e5ad8fd75e` | ✅ | migration applied on the live DB (`alembic_version` + `\d ai_conversations` verified in the lost session; live persistence re-verified this session) |
| 43 | Prompt/answer persisted per turn with sources, tool events, timings | ✅ | `_persist()`; history endpoint returns them |
| 44 | Conversation retention policy (`AI_CONVERSATION_RETENTION_DAYS`) | ✅ | lifespan sweep in `app/main.py`: purge once at startup + daily asyncio task (cancelled on shutdown, never fatal); `test_retention_purge_removes_only_expired_threads` (expired purged, survivor kept, messages FK-cascaded); live-verified: a 120-day-old thread deleted on backend restart with log `AI retention sweep removed conversations` |

## F. AI expansion — ten-feature matrix (Phases 3–7)

**Evidence basis (2026-10-19):** `./scripts/ai/eval_final.sh --report …` →
**147/147 combined gates, exit 0** (golden + live, 213 s, post-fix run) with per-feature
`n=` kept separate; backend suite **1048 passed**; frontend **216/216** +
lint + typecheck + production build; `ruff check .` / `ruff format --check .`
(290 files) / `mypy` (177 files) clean; alembic head unchanged
(`c5e2b8f4d9a3`). `n=` is the golden sample size re-checked on every run;
"live" cells were exercised end-to-end against the local Qwen3 server.

| # | Feature | Backend service → API | Frontend | Data sources | Authorization / review | Verified evidence (n=, live) |
|---|---|---|---|---|---|---|
| 45 | Grounded AI assistant (chat, stream, report draft, tools) | `app/ai/*` → `POST /ai/chat`, `/ai/chat/stream`, `/ai/report-draft`, conversation CRUD under `/ai/*` | floating assistant + history (`assistant`/`history` tests) | case records + knowledge docs, read-only tool calls only | per-user auth + rate limit; owner-scoped threads; case chat needs membership; answers stay chat, never evidence | phase-1 live harness **5/5 gates**: 41 golden entries, fact recall 51/54, groundedness 1.0, sources 1282/1282 valid, abstention 7/7, 0 ungrounded answers, 0 invalid sources |
| 46 | Evidence intelligence (ingestion copilot + chain-of-custody) | `evidence_intelligence` + `evidence_integrity` → `/cases/{id}/evidence-intelligence/extract`, `…/evidence-integrity/verify`, `…/custody-audit` | `extraction-panel.tsx` | uploaded files, custody events, content hashes | membership + IDOR probes; derived artifacts `pending_review` | phase-2 live **3/3 gates**: ingest n=3 cases (claim recall 12/13, precision 21/22, field validation 59/60, locator violations 0), integrity 3/3 states, custody n=2 (gap rule fires, clean case 0 findings), cleanup removes all objects |
| 47 | Entity resolution | `case_intelligence` → `…/evidence-intelligence/entity-resolution` | `resolution-panel.tsx` | source records, entity/alias rows | membership; artifact `pending_review`, never auto-merged | golden **n=8**: precision 4/4, recall 4/4, false merges 0/4; live section ran |
| 48 | Timeline reconstruction | `case_intelligence` → `…/timeline-reconstruction`, `…/timeline-proposals/{id}/commit` | `reconstruction-panel.tsx` | source records | membership; proposals require human commit | golden **n=13** parse cases: precision/recall 7/7, invented timestamps 0; n=5 record cases 5/5; live section ran |
| 49 | Contradiction detection | `case_intelligence` → `…/contradiction-detection`, `…/contradictions/{id}/resolve` | `contradiction-panel.tsx` | source-record pairs | membership; findings only human-resolved | golden **n=19**: classifier 19/19, category precision/recall 7/7, 0 false positives; live section ran |
| 50 | Financial flow analysis | `case_intelligence` → `…/financial-flow`, `…/financial-flow/trace` | `financial-flow-panel.tsx` | financial fields in source records (absence stays absence) | membership; artifact `pending_review`; no unkeyed grand totals | golden **n=23** records (2 victims, 22 facts): warnings recomputed exactly, invalid amounts stay invalid; live section ran |
| 51 | Cross-case linkage | `cross_case` → `POST /cross-case/discover`, `/cross-case/candidates` | `cross-case-panel.tsx` | indicators across separate cases | discovery read-only; approval records a reviewed relationship artifact — never a case merge | golden **n=3** case pairs (4 records); live section ran |
| 52 | Multilingual complaint intelligence | `evidence_intelligence` → `…/evidence-intelligence/multilingual` (+ jobs, cancel, artifacts, review) | `multilingual-panel.tsx` | complaint text units from uploaded records | anonymous 401 / non-member 403 / records IDOR 404 (live-checked); artifact `pending_review`; unsupported script refused | golden **n=7** complaints → 20 values (15 real, 5 planted fabrication), 0 false accepts; live vs Qwen3: Hindi auto-detect 4.05 s → 7/7 values verified, explicit translation 4.05 s → 7/7, English 8/8, unsupported script refused with 0 artifacts |
| 53 | Digital forensics triage | `evidence_intelligence` → `…/evidence-intelligence/triage` | `triage-panel.tsx` | manifest bytes, URL/history/header fields (URLs never fetched, nothing executed) | same authz ladder; structural observations only — no malware/phishing verdict; artifact flagged | golden **n=9** (3 benign, 1 refusal, 1 injection, 1 manifest, 3 burst), 0 problems, deterministic re-compute; live: 3 URLs → 4 observations (3.04 s), manifest 3/3 entries re-hashed (2.03 s), unsupported format refused |
| 54 | AI report auditing | `report_audits` → `POST /cases/{id}/report-audits`, `GET …/report-audits/{audit_id}` | `report-audit-panel.tsx` | draft text kept as sha256 only (never persisted raw) + case records for citations/counter-evidence | membership + mutable case (409 read-only); artifact **always** `pending_review` + `flagged` + standing `model_claims_unreviewed`; anonymous 401 / mid-run revocation fails closed / injection fenced (new tests) | golden **n=19** (dates/amounts/arithmetic/chronology/currency), 0 problems; live: 273-char draft → 6 claims, findings 6 high / 0 medium / 1 info, 3 counter-evidence matches, 19 audit metadata rows content-free |

**Pre-stated limitations for rows 45–54** (decided before implementation, see
`PHASE_5_6_7_PLAN.md` §8): no OCR (image-only PDFs refused with
`OCR_REQUIRED`); no `.eml`/MIME parsing; Devanagari Hindi-vs-Marathi ambiguity
is flagged for review, never hidden; translation quality is measured only as
material-value preservation (no BLEU/human claim); triage never fetches URLs
and never issues malware verdicts; report auditing covers draft text only;
"Soup" fine-tuning stays an external blocker (row 57).

## G. Not part of this subsystem / blockers

| # | Item | Status | Note |
|---|---|---|---|
| 55 | Cloud/remote inference | 🔴 by design | excluded by requirement; no cloud path exists in code |
| 56 | Ollama | 🔴 by design | not used anywhere |
| 57 | "Soup" fine-tuning | 🔴 blocker | no Soup repository exists on this machine — only a mention in `docs/architecture/complete-project-status-report.md`. See `docs/ai/EVALUATION.md` |

**Totals:** 52 ✅ · 2 🟡 (all with documented, deliberate reasons) · 1 🔴 external
blocker · 2 🔴 by-design exclusions.

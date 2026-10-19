# AI Expansion — Phase 0 Audit

**Date:** 2026-10-15 · **HEAD:** `f983883` (clean tree)
**Scope:** Think mode, Analysis-page AI, Hypotheses-page AI, accuracy/eval, gates.

Audited before any code was written. Nothing here is inferred from docs alone —
each claim was verified against the running code or its source.

---

## 1. Inference runtime and generation budget

| Setting | Value | Source |
|---|---|---|
| `AI_CONTEXT_LENGTH` | 8192 (gateway prompt budget, per slot) | `config.py:195` |
| `AI_MAX_OUTPUT_TOKENS` | 512 | `config.py:121` |
| `AI_MAX_CONCURRENT_GENERATIONS` | 2 | `config.py:124` |
| `AI_REQUEST_TIMEOUT_SECONDS` | 180 | `config.py:123` |
| `AI_SERVER_PARALLEL` | 2 | `run_server.sh` |
| Server args | `--ctx-size $((CTX*2*PARALLEL)) --parallel 2 --jinja --no-webui` (per-slot 16384) | `run_server.sh` |
| Temperature | **fixed 0.2** | `client.py` (both chat + stream) |
| Qwen3 thinking | **disabled** (`chat_template_kwargs.enable_thinking=false`) | `client.py` |
| Timeout | `connect=5, read=f(max_tokens), write=10, pool=5` | `client.py:86` |

The per-slot context fix (`--ctx-size = CTX * PARALLEL`) is intact and must be
preserved: llama.cpp divides `--ctx-size` evenly across `--parallel` slots.
The `2x` factor added 2026-10-19 is also load-bearing: llama-server retains a
shared KV prefix in a reused slot, which otherwise steals the generation room
the gateway reserved (observed cutting analysis answers at
`n_tokens = 8191, truncated = 1`) — one full prompt budget of slack absorbs
it (`n_ctx_slot = 16384`, VRAM ~9.8/12 GiB measured).

**Consequence for Phase 1:** because `enable_thinking=false`, the model emits no
hidden reasoning. "Think" can therefore only mean *more budget + more bounded
retrieval + a structured rationale section*, never a private chain-of-thought.
This matches the requirement not to expose internal CoT.

## 2. Existing profile machinery (Stage B) — reused, not rebuilt

`AiProfile = Literal["quick","standard","deep"]` (`schemas/ai.py:16`) resolves
through `_profile_for()` (`service.py:85`) to an `AnswerProfile(name,
max_tokens, tool_iterations)`:

| profile | max_tokens | tool_iterations |
|---|---|---|
| quick | 160 | 2 |
| standard | 384 | 3 |
| deep | 768 | 4 |

Unknown profiles **fall back** to the default rather than raising. Profiles are
budget-only: they never disable grounding, citations or authorization.

**Design decision (user-approved):** Think maps onto the existing `deep`
profile. `think` is added as a public alias so the profile machinery stays the
single source of budget truth. No parallel system is introduced.

## 3. Streaming and cancellation contract

SSE types emitted today (`service.py`): `token`, `tool`, `sources`, `done`,
`error`. There is **no `progress` type**, and the frontend switch
(`api/real/index.ts:787-817`) handles exactly those five plus `error`.

Cancellation exists only as `task.cancel()` inside a timeout path
(`service.py:415`). There is **no client-initiated cancel** endpoint.

## 4. Tool registry and authorization

8 read-only tools: `search_cases`, `get_case_summary`, `list_evidence`,
`get_entity`, `get_timeline`, `get_analytics_summary`, `rank_entities`,
`search_knowledge`. Every case tool resolves its own reference (UUID / case
number / exact name) through `_lookup_case()`, which applies the shared
visibility predicate and re-runs `assert_case_access` as defense in depth.
`ToolExecutionResult.status` distinguishes `case_not_found_or_not_accessible` /
`case_found_but_empty` / `case_found_with_data` / `case_ambiguous` /
`lookup_error` (added in `f983883`).

## 5. Deterministic analytics engine (`backend/app/analytics/`, 2479 LOC)

Already computes, with no LLM involvement: centrality (degree/betweenness/
closeness/pagerank), communities, patterns, relationship strength, network DNA,
paths, priority, findings, and **candidate hypotheses**.

### Confidence semantics — critical for Phase 3
Scores are **explicit structural heuristics**, not calibrated probabilities:

- `analytics/hypotheses.py:132` — `confidence = min(1.0, 0.35 + 0.15 * len(neighbors))`
- `analytics/hypotheses.py` — `score = 0.55*shared_score + 0.30*same_community + 0.15`
- `analytics/patterns.py:77` — `0.5 + 0.1*(count-threshold)/threshold`
- `analytics/strength.py` — weighted sum of file-independence + resolution confidence

Each candidate already carries a `signals[]` array
(`name`, `value`, `weight`, `description`) — an existing explainability surface
the AI can cite. The frontend (`hypotheses.tsx:249`) currently renders
`Math.round(confidence*100)` with a `%`, which reads as a probability. Phase 3
must explain the true meaning without silently relabelling it.

## 6. Hypothesis workflow (`models/hypothesis.py`, `services/hypotheses.py`)

Already present and authoritative:
- **kind ladder:** `fact → observation → inference → hypothesis`
- **status lifecycle:** `proposed → under_review → supported | contradicted |
  dismissed | concluded` (state machine enforced in the service)
- `supporting_evidence` / `contradicting_evidence` (JSONB), `related_entities`,
  `related_relationships`, `evidence_weight`, `confidence`, `submitted_by`
- routes: create / list / get / **status transition** / link-evidence / delete

**Consequence for Phase 3:** investigator disposition already exists. AI output
must land as `proposed` only and must never auto-transition to
`supported`/`concluded`.

## 7. Evaluation harness

`backend/scripts/eval_model.py` + `scripts/ai/eval_model.sh`, golden set of
**33** entries keyed by `case_number`. Current hard gates (exit 1 on failure):
`abstention_100pct`, `zero_ungrounded_answers`, `zero_invalid_sources`.
Reported metrics: groundedness (citation resolution), fact recall (normalised
substring), abstention, latency. Exit 2 = setup failure.

**Gaps for Phase 4:** citation-vs-case consistency, numeric/timestamp
correctness, hypothesis support/counter-evidence, Quick-vs-Think completeness,
prompt-injection and tool-misuse.

## 8. Frontend surfaces

- `/analytics` (`pages/analytics.tsx`, 352 LOC) — deterministic panels only:
  summary, network DNA, communities, centrality (metric switcher), priorities,
  strength, patterns, runs. **No AI today.** → Phase 2 target (user-approved).
- `/hypotheses` (`pages/hypotheses.tsx`, 274 LOC) — two sections: *Investigation
  hypotheses* (CRUD + status transition) and *Analytics hypotheses* (read-only
  candidates with confidence %). **No AI today.** → Phase 3 target.

## 9. Reconciliation with the task's assumptions

| Task assumes | Reality |
|---|---|
| "Analysis page" | Is the `/analytics` route (titled "Analytics") |
| Quick/Think modes are absent | `quick`/`standard`/`deep` already exist; Think maps to `deep` |
| Hypothesis confidence scoring to inspect | Heuristic, already present, already explained via `signals[]` |
| Candidate generation to build | Exists in `analytics/hypotheses.py` |

## 10. Non-negotiables carried forward

No Ollama, no cloud LLM, no second gateway, no replacement of the inference
runtime. Authorization before context assembly and on every tool call. Never
expose unauthorized record existence. No fabricated success. Weights, secrets
and `ai_runtime/` never committed.

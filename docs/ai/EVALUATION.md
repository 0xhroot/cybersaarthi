# AI Evaluation, Rollback and the Soup Question

**Date:** 2026-10-15 · Rules of this document: measured numbers only, skipped
work is labelled as skipped, and nothing is claimed that wasn't run.

## 1. What was measured (real runtime, this machine)

All figures come from `scripts/ai/verify_model.sh` and the live API walkthrough
on 2026-10-15 (RTX 3080 12 GB, `Qwen3-8B-Q4_K_M.gguf`, llama.cpp `b11617`,
`--ctx-size 8192 --parallel 2 --n-gpu-layers -1`).

| Metric | Value | How |
|---|---|---|
| Model load (server start → healthy) | ~5 s (cold), 0.02 s (warm mmap) | server log, `/health` polling |
| Short completion ("pong") | 2 completion tokens, 17 prompt tokens (16 cached) | verify §3 |
| First token latency (streaming, short prompt) | **23 ms** | verify §4 |
| Sustained throughput | **~179 tok/s** (1 107 chars ≈ 276 tokens in 1.54 s) | verify §4 |
| Throughput (llama-server's own accounting, small prompt) | 124–126 tok/s eval | server log `print_timing` |
| Prompt eval | ~830–850 tok/s | server log `print_timing` |
| GPU utilisation during generation | 96 % | `nvidia-smi` |
| VRAM | 6 428 / 12 288 MiB (llama-server process: 5 986 MiB) | `nvidia-smi` |
| End-to-end general chat via API | 346–678 ms | E2E script |
| End-to-end grounded case chat via API | **1 161 ms**, 39 sources (24 case-scoped), 340-char answer | E2E script |
| Streamed grounded turn | first_token_ms 364 (through the gateway), 26 token events | E2E script |
| Tool-loop turn (`search_cases`) | 722 ms / 689 ms over two runs | timed `POST /ai/chat` |
| Grounded answer quality (spot check) | Cited the real case ("Ponzi investment racket"), real entity/evidence counts, real victim name | E2E + lost-session check |

**GPU acceleration claim:** verified, not inferred —
`nvidia-smi --query-compute-apps` shows the llama-server PID resident at
**5 986 MiB** and GPU utilisation **96 %** while generating. With
`--n-gpu-layers -1` all layers are offloaded.

## 2. What was *not* measured (skipped, and why)

| Item | Status | Reason |
|---|---|---|
| Quantitative answer-quality benchmark (RAGAS/BEIR-style, held-out QA set) | **skipped** | No labelled QA dataset for this domain exists in the repo; inventing one would produce meaningless scores. A harness is proposed in §5 instead |
| Model-vs-model comparison (e.g. Qwen3-8B vs 14B) | **skipped** | Only one model is present; downloading others was out of scope |
| Load/soak testing (concurrent users, hours-long uptime) | **skipped** | Not requested; the semaphore (2) and rate limiter (20/min/user) bound worst case by design |
| Context-length stress at the 4 096-token-per-slot ceiling | **partially observed** | An oversized retrieval prompt did fail once (HTTP 400 from the server) — root cause fixed (context raised to 8 192, retrieval budgets trimmed); not re-run as a systematic sweep |
| Multi-GPU / quantisation-aware training | **not applicable** | Single consumer GPU; inference-only deployment |

## 3. Quality observations (qualitative, honestly labelled)

- Grounded answers **cite real, DB-verified records** (evidence filenames,
  entity counts, timeline entries) because citations come from the retrieval
  `SourceRef` list, not from the model's memory.
- The model sometimes invents odd citation *formatting* (e.g.
  `[evidence:case_summary]`); the underlying source chips rendered by the UI are
  correct, so this is cosmetic model behaviour, not a data-integrity issue.
- Thinking mode is disabled (`enable_thinking: false`), so latency numbers
  reflect answer-only generation; re-enabling it would add reasoning tokens and
  change every latency figure in §1.
- A tool-loop turn costs one extra round trip (~0.7 s measured twice for a
  `search_cases` turn: 722 ms and 689 ms end-to-end) — acceptable for
  investigative queries, visible to the user as a tool chip in the chat UI.
- **A real hallucination was found and fixed.** Asking the knowledge-mode
  assistant "what port does the inference server listen on?" produced
  *"port 8080 … specified in inference-server-configuration.md"* — a port
  that is wrong (it's 8081) and a filename that does not exist, with **zero**
  sources attached, because knowledge mode has no DATA block and the model
  answered from memory instead of calling `search_knowledge`. The prompt now
  requires the tool lookup when no excerpts are present and forbids guessing
  filenames/ports/paths (`prompts.py`, covered by
  `test_knowledge_mode_requires_tool_lookup_before_answering`). Re-asked after
  the fix: the model called `search_knowledge`, cited 4 real documents, and
  correctly described the UDS/socket setup. This is exactly why §5's
  groundedness gate matters — and why this class of failure needs the harness,
  not just spot checks.

## 4. Rollback and kill-switches (all tested paths)

The AI layer is **additive**: nothing outside `app/ai/`, `routes/ai.py`, the two
AI models/migration and the frontend assistant depends on it. Rollback options,
cheapest first:

| Level | Action | Effect | Verified by |
|---|---|---|---|
| Kill switch | `AI_ENABLED=false` in `.env` + restart backend | every `/ai/*` route → 503 `AI_DISABLED`; assistant shows offline banner; rest of app unaffected | `test_disabled_ai_returns_503` |
| Runtime down | stop `llama-server` | `/ai/*` → 503 `AI_UNAVAILABLE`; platform unaffected | live: E2E script's cancellation check + `test_model_failure_returns_503` |
| Feature flag | `AI_FEATURE_CASE=false` etc. | that tool/mode disappears from `/ai/status` and prompts | `AIService.status()` feature_flags |
| UI removal | unmount `<Assistant />` in `app-shell.tsx` | chatbot gone, zero backend impact | mount is a 2-line diff |
| Full revert | `git revert` of the AI commits (once committed) | schema/migration included; `alembic downgrade` for `36e5ad8fd75e` | migration is reversible (`down_revision` set, standard `drop_table`) |

The migration `36e5ad8fd75e_add_ai_conversations_and_messages.py` only **adds**
two tables; downgrading drops them and touches no existing table — no destructive
migration exists anywhere in this work.

## 5. Evaluation harness (implemented, run 2026-10-15)

So a model swap (including a fine-tune) can be judged instead of guessed:

1. **Golden set** — 33 frozen entries in `backend/tests/fixtures/ai_golden.jsonl`:
   29 grounded questions across all five showcase cases (incl. 2 graph-mode),
   3 foreign-case abstentions (must return 403), 1 unknown-case (must return
   404). Guarded by `backend/tests/unit/test_ai_golden_fixture.py` (10 tests
   pinning counts, kinds, statuses, modes and case numbers).
2. **Scoring** — deterministic, no LLM judge, in
   `backend/scripts/eval_model.py`:
   - *groundedness*: every cited `SourceRef` must exist in the DB **and** belong
     to the evaluated case (hard gate);
   - *recall of expected facts*: case/underscore-insensitive substring match;
   - *abstention*: questions about cases the caller can't access must produce
     the exact refusal status (hard gate);
   - *latency*: per-request duration (reported).
3. **Runner** — `scripts/ai/eval_model.sh` → `python -m scripts.eval_model`,
   posting to `/ai/chat` over real HTTP with real auth (3.5 s pacing to stay
     under the rate limit; the API has no seed/temperature parameter — the
     gateway fixes `temperature=0.2` server-side). Report written to
     `ai_runtime/eval_report.json` (gitignored).
4. **Gate** — exit 0 only if abstention = 100 %, zero ungrounded answers and
   zero invalid/cross-case sources; exit 1 on gate failure, 2 on setup failure.

**Run evidence (2026-10-15, Qwen3-8B-Q4_K_M on the local llama-server):**
33/33 entries pass all three gates; groundedness 1033/1033 cited sources
resolve to the correct case (1.000); abstention 4/4; fact recall 49/53
(0.925); latency avg 741 ms, max 2035 ms. The three gates are hard; fact
recall is reported, not gated.

**Honest misses from that run** (the point of measuring):
- `s001-top-entity` expected Delhi/59 relationships, model answered
  "Gaurav Joshi, 13"; `s005-top-entity` expected Dehradun/67, model answered
  "Ludhiana, 32" — Qwen3-8B twice misread its own sorted entity digest.
- `s001-timeline` fact "registered" missed because the model paraphrased to
  "registration" (brittle substring, not a data error).

The harness also caught a real runtime bug before any model swap could: the
server was started with `--ctx-size 8192 --parallel 2`, so llama.cpp divided
the context to 4096 tokens per slot while showcase-case DATA blocks need
~4350 — every large-case chat failed 503. Fixed in `scripts/ai/run_server.sh`
(`--ctx-size $((CTX * PARALLEL))`, verified `n_ctx_slot = 8192`).

## 6. "Soup" — status, blocker, and safe prep only

**What Soup is** (verified from the upstream repository today,
`github.com/MakazhanAlpamys/Soup`, Apache-2.0): a CLI ("fine-tune LLMs from one
YAML") offering QLoRA/SFT fine-tuning with a `tool-calling` template, LoRA
adapters, GGUF export for llama.cpp, an OpenAI-compatible `soup serve`, and eval
tooling (`soup eval`, `soup bench`, `soup ab`). It can export a trained adapter
to GGUF for exactly the runtime this project uses.

**Local reality — audited, not assumed:**

| Check | Result |
|---|---|
| Local checkout of Soup anywhere on disk | **none** (the only `*soup*` files are `libsoup-3.0`, the unrelated GNOME HTTP library) |
| `soup`/`soup-cli` installed in any env | **no** |
| Reference in repo code | **none** — the name appears only in `docs/architecture/complete-project-status-report.md` (greenfield item F47, "verified empty") |
| Host Python | **3.14.7** — Soup supports **3.10–3.12 only** (3.13+ resolves untested PyTorch wheels) |
| `python3.10/3.11/3.12` interpreter available | **no** |
| Fine-tuning dataset for CyberSaarthi in repo | **none** (only evidence fixtures, not instruction-tuning data) |

**Blocker statement:** Soup fine-tuning cannot proceed on this machine today
without (a) installing a 3.10–3.12 interpreter, (b) `pip install
"soup-cli[train]"` (a multi-GB PyTorch download), and (c) a curated, annotated
instruction dataset — none of which exists in the repo. None of those were done:
installing an ML training stack and downloading models was out of scope for this
audit, and fabricating a training dataset would be worse than doing nothing.

**Safe prep work done / recommended (no training run):**

- Done: the serving side is already Soup-compatible in the direction that
  matters — any GGUF produced by `soup export --format gguf` can be dropped in as
  `AI_MODEL_PATH` with **zero code changes** (the client speaks plain
  OpenAI-compatible HTTP).
- Recommended when unblocked: (1) provision Python 3.12 (pyenv/uv), (2)
  `pip install "soup-cli[train]"`, (3) define the instruction dataset schema
  (question → tool-call trace → grounded answer, exportable from the seeded
  showcase cases + audit logs), (4) LoRA fine-tune with the `tool-calling`
  template, (5) `soup export` → new GGUF → `AI_MODEL_PATH` swap → run the §5
  harness → keep or roll back by pointing `AI_MODEL_PATH` back at the stock
  model (a one-line, instant rollback).

## 7. Bottom line

- The current model is **fast and honestly measured**: ~179 tok/s, ~23 ms first
  token, real CUDA offload confirmed by `nvidia-smi`.
- Every AI failure mode has a tested, non-destructive rollback path.
- Quality beyond spot-checks is **not yet quantified** — the harness to do it is
  designed in §5 and explicitly not claimed as done.
- Soup is a genuine upstream tool that fits this architecture, but the local
  preconditions (interpreter version, training stack, dataset) are absent; it is
  recorded as a **blocker with a concrete unblock plan**, not as progress.

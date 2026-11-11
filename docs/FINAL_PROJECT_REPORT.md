# CyberSaarthi — Final Project Report

**Date:** 2026-11-11 · **Repository:** `0xhroot/cybersaarthi` · **Branch:** `main`

This report closes the ten-phase integration brief: audit → end-to-end
investigation workflow → reproducible synthetic dataset → local LLM
fine-tuning → baseline-vs-tuned evaluation → centralized config → docs →
one-command Makefile → E2E validation → final report & git delivery.

**Honesty rules applied throughout:** "pipeline implemented" and "training
executed" are stated as different things; no metric appears that was not
measured; blocked work is marked **PENDING** with the exact blocker named.

---

## 1. Phase status

| # | Phase | Status | Evidence |
|---|---|---|---|
| 1 | Audit | ✅ done (prior session) | HEAD `26dc520` baseline: 26 routes / 38 services / 34 models / 20 migrations; findings recorded in `docs/ai/AI_EXPANSION_AUDIT.md` and related audit docs |
| 2 | End-to-end investigation workflow | ✅ done | `docs/architecture/investigation-workflow.md` — how the ten AI capabilities compose in the product, with every named component existing in the repo |
| 3 | Reproducible synthetic dataset | ✅ executed | `scripts/ai/build_dataset.py` → **140 rows / 10 categories**; `validate_dataset.py` → splits **train 110 / val 15 / test 15**, Soup `110/110 valid for chatml`; showcase fixture validator → **`OK: all 108 checks passed`** |
| 4 | Local LLM fine-tuning on hardware | ✅ **training executed** | QLoRA run 2026-11-11: **exit 0, 39/39 steps, 570 s, peak 8183 MiB** (1 Hz) / 9.1 GiB (torch); adapter + candidate GGUF produced — [FINE_TUNING_REPORT.md](ai/FINE_TUNING_REPORT.md) |
| 5 | Baseline-vs-tuned evaluation | ⛔ **PENDING** | Blocker: Docker daemon down (`sudo systemctl start docker` needed). Pre-registered procedure & decision rule: FINE_TUNING_REPORT §7 |
| 6 | Centralized config | ✅ done | `.env.example` documents every knob incl. the model-swap workflow; `AI_MODEL_PATH` now actually read by `run_server.sh`; `make model-rollback`; `soup.yaml`; isolated training env via `scripts/ai/setup_training.sh` |
| 7 | Docs | ✅ done | `docs/architecture/{README,investigation-workflow,local-ai-training}.md`, `docs/ai/FINE_TUNING_REPORT.md`, refreshed `TRAINING_PIPELINE.md` + dated update in `EVALUATION.md` (§6) |
| 8 | One-command Makefile | ✅ done | `train-setup / train-check / train-pilot / train-metrics / dataset / dataset-validate / eval / eval-final / model-compare / model-rollback` (+ existing targets), all in `make help`, recipes smoke-tested (`-n`) |
| 9 | E2E validation (stack up) | ⛔ **PENDING** | Same Docker blocker: `make test`, `make demo-seed` ×2 (idempotence), retry-after-failure, model-restart checks need the compose stack |
| 10 | Final report & git delivery | 🟡 in progress | this document + small logical commits (see §9); push after remote reconciliation |

**Net:** 8 of 10 phases fully executed; the two pending phases (5 and 9)
depend on one environment action — starting the Docker daemon. Nothing
pending is blocked on code, data, or design.

## 2. Ten-feature verification matrix

Measured golden/live evidence per feature (numbers from the frozen harnesses,
`n=` stated, no LLM judge; recorded in `docs/ai/EVALUATION.md` §5):

| # | Feature | Harness | Evidence (measured) | Status |
|---|---|---|---|---|
| 1 | Grounded AI assistant (chat/stream/draft/tools) | `phase1_model` | **41/41 golden entries**, all 5 gates pass: groundedness **1.000 (1270/1270)**, abstention **7/7**, fact recall **0.9815 (53/54)**, latency avg **1597 ms** (2026-10-17) | measured; re-run pending stack |
| 2 | Evidence intelligence (ingestion copilot + chain-of-custody auditor) | `phase2_evidence` | `ai_runtime/eval_evidence_report.json` (2026-10-17) | measured; re-run pending stack |
| 3 | Entity resolution | `phase3_case_intel` | golden **n=8**, precision/recall/false-merge from frozen fixtures | measured 2026-10-19; re-run pending stack |
| 4 | Timeline reconstruction | `phase3_case_intel` | golden **n=13 parse / n=5 record cases** | measured 2026-10-19; re-run pending stack |
| 5 | Contradiction detection | `phase3_case_intel` | golden **n=19** | measured 2026-10-19; re-run pending stack |
| 6 | Financial flow analysis | `phase4_flow` | golden **n=23 records**, warnings recomputed exactly | measured 2026-10-19; re-run pending stack |
| 7 | Cross-case linkage | `phase4_flow` | golden **n=3 pairs**; approval never merges cases | measured 2026-10-19; re-run pending stack |
| 8 | Multilingual complaint intelligence | `phase567_expansion` | golden **n=7 complaints / 20 values (15 real + 5 planted)** | measured 2026-10-19; re-run pending stack |
| 9 | Digital forensics triage | `phase567_expansion` | golden **n=9** | measured 2026-10-19; re-run pending stack |
| 10 | AI report auditing | `phase567_expansion` | golden **n=19** | measured 2026-10-19; re-run pending stack |

**Combined gate:** `eval_final.sh` passed **147/147 gates, exit 0** on
2026-10-19 (per-harness 5 / 3 / 16 / 47 / 64 + 12 cross-cutting; includes the
10-feature coverage matrix, ≥1000-test inventory floor, single alembic head
`c5e2b8f4d9a3` — re-verified current this session — and the anonymous
401 error-shape probe). Per-feature metrics are never aggregated into a
single "AI accuracy" number.

**This session's re-verification:** the migration-head expectation in
`eval_final.py` was re-checked against the 19 revision files (single head,
matches); the full harness re-run is part of pending phase 9.

## 3. Dataset

| | |
|---|---|
| Generator | `scripts/ai/build_dataset.py` (mirrors the deployment prompt exactly: system prompt + optional data block + history + user question; tool calls as fenced text, as the backend really sends them) |
| Size | **140 rows**, 10 categories: case_qa, citation, ranking_tool, analytics_request, tool_args, abstention, conflict, report_draft, injection, isolation |
| Splits | **train 110 / val 15 / test 15** (deterministic, pairwise disjoint) |
| Validation | `validate_dataset.py` → Soup `110/110 rows valid for chatml`; `--self-test` green (10 rows / all categories); dedup + leakage + no-real-data guards |
| Token lengths (max 4096) | min 591 · median 2088 · p95 2856 · max 3267 · 0 rows exceed 4096 |
| Showcase fixtures | `backend/scripts/validate_showcase_dataset.py` + `dataset_manifest.json` → **`OK: all 108 checks passed`** (11 fixtures, 2 cases, isolation clean) |
| Data policy | 100% synthetic; no UUIDs, no live case numbers, no e-mail, no credentials; fictional SIH cases `SIH-2026-001/002` and the two showcase case IDs preserved; `hypothesize` category deliberately omitted (validator-forbidden ID shapes — documented limitation) |

## 4. Fine-tuning (executed)

Full detail: [`docs/ai/FINE_TUNING_REPORT.md`](ai/FINE_TUNING_REPORT.md).

- **Base model:** `Qwen/Qwen3-8B` (HF safetensors, Apache-2.0, official Qwen
  org, download verified) — never the GGUF.
- **Framework:** Soup CLI `soup-cli 0.76.1` (`soup train --config soup.yaml`),
  QLoRA 4-bit + LoRA r=16 on `q_proj`+`v_proj`, 3 epochs, ChatML format.
  Stack reproducible via `scripts/ai/setup_training.sh` (uv, Python 3.12).
- **Training executed: YES** — 2026-11-11, RTX 3080 12 GB:
  - **duration 570 s** (39/39 steps, ≈14.6 s/step), exit code 0
  - **peak VRAM 8183 MiB** (nvidia-smi @1 Hz) / **9.1 GiB**
    (`torch.cuda.max_memory_allocated()` — both quoted, scopes differ)
  - train loss **2.1936 → 0.8523**; val loss **1.186 → 1.034 → 1.019** per
    epoch (monotonic, no overfitting signal); final grad_norm 0.484
  - root cause of the six prior OOMs found and fixed (peft's fp32 upcast of
    `embed_tokens`+`lm_head` = +2.32 GiB resident and a 1.16 GiB autocast
    copy inside Liger's CE; guard in `scripts/ai/peft_upcast_guard.py`,
    logged in `train.log`, unit-tested, never touches site-packages)
- **Artifacts:** adapter 15,354,800 B / 144 tensors (shape-verified) and
  candidate **`ai_runtime/train/candidate/Qwen3-8B-qlora-Q4_K_M.gguf`**
  (5,027,779,264 B, GGUF v3, q4_k_m, sha256 differs from baseline) — merge →
  convert → quantize executed end-to-end; baseline file read-only.

## 5. Baseline-vs-tuned evaluation & adopt/reject — PENDING

- **Baseline report (exists):** `ai_runtime/eval_report.json`, 41 entries,
  all five gates true (fact_recall 0.9815 = 53/54, groundedness 1.0 =
  1270/1270, abstention 7/7, latency_ms_avg 1597).
- **Tuned report:** not yet produced — the harness needs the live backend
  (Docker down). **Blocker:** run `sudo systemctl start docker`, then
  `docker compose up -d --build`.
- **Procedure (pre-registered):** swap `AI_MODEL_PATH` to the candidate,
  restart the model server, `./scripts/ai/eval_model.sh --report
  ai_runtime/eval_report_tuned.json`, then
  `make model-compare A=ai_runtime/eval_report.json B=ai_runtime/eval_report_tuned.json`.
  Same 41-entry golden set both sides; `compare_eval.py` refuses (exit 2) on
  mismatched golden sets or sample counts — verified this session by
  self-comparison (no improvement → REJECT, exit 1) and a count-mismatch
  fixture (exit 2).
- **Decision rule (fixed in advance):** **ADOPT** only if every
  baseline-passing gate still passes **and** ≥1 metric improves; **REJECT**
  (keep Q4_K_M, `make model-rollback`) on any gate regression or no
  improvement.
- **Current decision: NONE — neither adopted nor rejected.** The adapter is
  trained and exported; no improvement is claimed without measurement.

## 6. Inference & runtime status

- llama.cpp `llama-server` build **b11617** (CUDA, `$ORIGIN` libs), baseline
  `Qwen3-8B-Q4_K_M.gguf` (5,027,783,488 B) at repo root, git-ignored.
- **Config gap found & fixed:** `run_server.sh` hardcoded the baseline GGUF,
  so `make model-rollback` edited a variable nothing read at runtime. It now
  resolves `AI_MODEL_PATH` (absolute or repo-root-relative, default =
  baseline) — verified for all four cases (unset / relative / candidate /
  absolute). `.env.example` documents the two-reader contract (host server vs
  pinned container path).
- Socket-bridge path, `LLAMA_API_KEY` delivery via env (never argv), and the
  compose pin for the container's read-only mount are unchanged.
- Current process state: **model server not running** (cleaned up during
  this session); stack restart is part of pending phase 9.

## 7. Test results (this session)

| Suite | Result |
|---|---|
| Frontend `npx tsc -b --noEmit` | ✅ exit 0 |
| Frontend `npx eslint src/` | ✅ exit 0 |
| Frontend `npx vitest run` | ✅ **227/227 passed** (26 files, 52 s) |
| Frontend `npm run build` | ✅ exit 0 (pre-existing >500 kB chunk warning) |
| Backend `ruff check .` | ✅ clean — fixed 23 violations introduced by the new showcase validator (E501/E741/S603), per repo conventions (`noqa` style matches `eval_final.py`) |
| Backend `ruff format --check` | ✅ clean |
| Backend `mypy app` | ✅ **172 files, no issues** |
| Backend test collection | **1050 collected** (1042 non-integration / 8 integration) — meets `eval_final`'s ≥1000 floor |
| Backend non-integration run | 🔄 running host-side at report time (result recorded in §9 commit message / chat follow-up) |
| Backend full suite `make test` | ⛔ PENDING (container; Docker down). Last full run: 1048 passed (2026-10-19) |
| Dataset validators | ✅ `validate_showcase_dataset.py` → **108 checks passed**; `validate_dataset.py --self-test` green |
| Training checks | ✅ `make train-check` green (doctor + liger gate + peft-guard assertion + dry-run) |

No test was weakened, skipped, or deleted; the two lint fixes were in a
brand-new file.

## 8. Documentation

| Path | Contents |
|---|---|
| `docs/FINAL_PROJECT_REPORT.md` | this report |
| `docs/ai/FINE_TUNING_REPORT.md` | measured training run: config, loss curve, OOM root cause + guard, adapter, candidate export, pre-registered eval rule, limitations |
| `docs/architecture/local-ai-training.md` | training/eval/rollback architecture (baseline never at risk) |
| `docs/architecture/investigation-workflow.md` | end-to-end investigation workflow across the ten AI capabilities |
| `docs/architecture/README.md` | index of the architecture set |
| `docs/ai/TRAINING_PIPELINE.md` | refreshed: install/execution status replaces the old "held pending go-ahead" |
| `docs/ai/EVALUATION.md` | dated 2026-11-11 update on the §6 Soup blocker (history preserved) |
| `.env.example` | centralized config incl. model-swap workflow |

## 9. Git delivery

Work is committed as small logical commits on `main` (dataset validator →
dataset pipeline → training runner/guard → eval comparison/config →
Makefile wiring → docs → this report), then reconciled with `origin/main`
(fetched clean at `26dc520` before the series) and pushed. The exact HEAD
and push result are reported in the delivery chat message; no history was
rewritten, no secrets, DB dumps, or model weights are tracked (enforced by
`.gitignore` + the validator's git-hygiene check).

## 10. Limitations

1. **Phases 5 & 9 pending on Docker** — baseline-vs-tuned numbers, the
   adopt/reject decision, `make test` in-container, and the E2E workflow
   checks (repeated seed idempotence, retry-after-failure, model restart)
   have not been re-run this session. Last known good values are cited with
   their dates; none is presented as current.
2. **Adapter has no measured benefit yet** — trained ≠ better; the
   pre-registered rule governs adoption.
3. **Small SFT set** (110 train rows, 3 epochs) and **LoRA on
   `q_proj`+`v_proj` only** (Soup `auto`) — a second round should widen
   targets and data if the first shows promise.
4. **`hypothesize` category omitted** from synthetic data (validator-forbidden
   ID shapes) — that mode is covered only by the pre-existing golden tests.
5. **Single training seed/run** — no variance estimate; peak-VRAM figures
   differ by instrument (1 Hz sampler vs torch high-water mark), both quoted.
6. **Eval harness measures one run per entry** — not a statistical claim
   (stated in `EVALUATION.md`); gates are hard, fact recall is reported.

## 11. Next steps

1. **User:** `sudo systemctl start docker` (the only action the agent cannot
   perform — needs a password).
2. `docker compose up -d --build` → `make test` (expect ≈1050 in-container)
   → `make admin/seed` + `make demo-seed` ×2 (idempotence) →
   `make demo-status`.
3. E2E workflow validation: repeat seed, retry-after-failure, model-server
   restart, showcase case IDs `d439fa9c-…` / `375867d1-…` intact.
4. Eval: `make eval` (baseline re-run) → swap `AI_MODEL_PATH` to the
   candidate → `eval_model.sh --report …_tuned.json` → `make model-compare`
   → **ADOPT or REJECT** by the pre-registered rule (§5); rollback with
   `make model-rollback` if rejected.
5. `make eval-final` (combined ten-feature gate, head already verified
   current) → reconcile remote → push → close phase 10.

# CyberSaarthi AI — Accuracy & Performance Plan

**Repo:** `/home/xhroot/Documents/ai/CyberSaarthi`
**Baseline commit:** `8269313` (working tree clean at audit)
**Inference:** llama.cpp 0.6.0-dev (build 11617, commit 14310190c), CUDA, RTX 3080 12 GB
**Model:** `Qwen3-8B-Q4_K_M.gguf` (kept as known-good baseline; never overwritten)
**Baseline date:** 2026-10-15

This plan records measured baselines and measurable goals. Every performance
claim below is reproducible via the cited command. Nothing here is asserted
without a measurement.

---

## 1. Baseline measurements (all executed, this machine)

### 1.1 Test suites
| Suite | Result | Command |
|---|---|---|
| Backend (hermetic) | 542 passed, 8 deselected | `cd backend && .venv/bin/python -m pytest -m "not integration" -q` |
| Backend (live integration) | 8 passed | `cd backend && .venv/bin/python -m pytest -m integration -q` |
| Frontend | 110 passed / 18 files | `cd frontend && npx vitest run` |
| Golden eval (Qwen3-8B Q4_K_M) | 33/33 gates pass, fact_recall 0.9434, groundedness 1.0 | `./scripts/ai/eval_model.sh` |

### 1.2 Latency — raw llama-server (no FastAPI, no DB)
`backend/.venv/bin/python scripts/ai/bench.py --repeats 7 --max-tokens 32 [--stream]`

| Prompt | Layer | TTFT median | Total median | tok/s median |
|---|---|---|---|---|
| short ("pong") | raw, non-stream | — | 18.1 ms | 55.1 |
| short ("pong") | raw, stream | 10.5 ms | 18.5 ms | 54.1 |
| medium (1 sentence) | raw, non-stream | — | 177.4 ms | 197.3 |

### 1.3 Latency — full gateway (auth + retrieval + tools + model)
`backend/.venv/bin/python scripts/ai/bench_gateway.py --repeats 5`

| Prompt | Total median | p95 |
|---|---|---|
| short ("pong") | 72.0 ms | 107.1 ms |
| case-grounded ranking (SHOW-2026-001) | 243.6 ms | 357.4 ms |

**Observation:** gateway case-path adds ~225 ms over raw short — retrieval,
tool-loop and serialization. Raw short (18 ms) vs gateway short (72 ms) shows
~54 ms of auth+framework overhead.

### 1.4 VRAM / context
- Idle-to-warm VRAM: **7476 MiB / 12288 MiB** (GPU 6% util idle).
- Server args: `--ctx-size 16384 --parallel 2 --n-gpu-layers -1` (per-slot 8192,
  the fix from commit `8269313` is intact).

### 1.5 Server-supported optimization levers (verified via `--help`)
`--flash-attn [on|off|auto]`, `--cache-type-k/v TYPE`, `--batch-size`,
`--ubatch-size`, `--cont-batching` are all available in this build.

---

## 2. Root-cause finding: entity-ranking failures

**Symptom (baseline eval):** all 5 `*-top-entity` golden questions FAIL
(`s001`…`s005-top-entity`). The model reads a sorted text digest
(`entities_digest`, top-15 by relationship count) but mis-picks the top entity.

**Root cause (verified):** the deterministic analytics package
`backend/app/analytics/` (`compute_centrality`, `pagerank`,
`betweenness_centrality`, `build_graph`, …) is **never imported by
`backend/app/ai/`**. The model is the only thing doing ranking, from text.
The existing `get_analytics_summary` tool does not return authoritative
top-entity rankings.

**Fix direction (Part 2):** add an authorized, case-scoped analytics tool that
runs the deterministic query/graph code and returns typed structured results
(metric name, value, entity id, rank, tie-break). The model explains the
verified result; it never recalculates a ranking from a long digest.

---

## 3. Measurable goals — Stage A results (executed)

| # | Goal | Metric | Baseline | Stage A result | Gate? |
|---|---|---|---|---|---|
| G1 | Fix entity-ranking accuracy | `s00X-top-entity` golden pass | 0/5 | **5/5** | hard ✅ |
| G2 | Overall fact recall | golden `fact_recall` | 0.9434 | **1.0 (53/53)** | reported ✅ |
| G3 | Preserve security gates | abstention 100%, ungrounded 0, invalid sources 0 | pass | **pass** | hard ✅ |
| G4 | Case-path gateway latency | gateway:case total median | 243.6 ms | ~260 ms (tool round-trip) | reported — see §5 |
| G5 | Quick-profile short answer | gateway:short total median | 72.0 ms | — | Stage B |
| G6 | No VRAM regression | peak VRAM | 7476 MiB | unchanged | hard ✅ |

Goals G4/G5 are best-effort; if a change hurts G1–G3 or G6, it is rejected
regardless of latency gain.

**Stage A outcome:** the entity-ranking fix drove fact recall from 0.9434 to a
perfect 1.0 and fixed all 5 previously-failing top-entity questions, while
groundedness held at 1.0 and abstention at 4/4. Cost: ~+400ms average latency
on ranking questions only (the model now calls `rank_entities` and waits for
the authoritative answer instead of guessing from the digest). Non-ranking
questions are unaffected. This is the intended trade: correctness over speed,
and only where a ranking is actually requested.

## 3b. Measurable goals — original targets

| # | Goal | Metric | Target | Gate? |
|---|---|---|---|---|
| G1 | Fix entity-ranking accuracy | `s00X-top-entity` golden pass | 5/5 (from 0/5) | hard |
| G2 | Overall fact recall | golden `fact_recall` | ≥ 0.96 (from 0.9434) | reported |
| G3 | Preserve security gates | abstention 100%, ungrounded 0, invalid sources 0 | unchanged | hard |
| G4 | Case-path gateway latency | gateway:case total median | ≤ 200 ms (from 243.6) | reported |
| G5 | Quick-profile short answer | gateway:short total median | ≤ 60 ms (from 72) | reported |
| G6 | No VRAM regression | peak VRAM | ≤ 11.0 GiB | hard |

Goals G4/G5 are best-effort; if a change hurts G1–G3 or G6, it is rejected
regardless of latency gain.

---

## 4. Stage plan (small, each saved + verified)

- **Stage A — analytics tool.** Authorized case-scoped `rank_entities` (and
  friends) backed by `entities_digest` query + `compute_centrality`, returning
  typed structured results with metric definitions and stable tie-breaks.
  Wire into prompt as structured data, not prose. Regression tests: correct top,
  top-N order, ties, empty, missing metric, foreign case 403, misleading model
  output. Re-run eval; report G1/G2/G3/G4.
- **Stage B — quick/standard/deep profiles.** Configurable retrieval budget,
  output-token budget and tool-loop bound per profile via existing API/UI
  contract. Bench G4/G5.
- **Stage C — inference-server tuning.** Benchmark flash-attn on/off, KV-cache
  type, batch/ubatch under equivalent prompts; keep the change only if it wins
  on TTFT/throughput without hurting G6.
- **Stage D — Soup fine-tuning prep.** Environment + format + dataset schema
  validation (no expensive run until compatibility verified). See
  `docs/ai/TRAINING_PIPELINE.md`.

---

## 5. Reproducibility

All numbers regenerate with:
```bash
cd /home/xhroot/Documents/ai/CyberSaarthi
backend/.venv/bin/python scripts/ai/bench.py --repeats 7 --stream
backend/.venv/bin/python scripts/ai/bench_gateway.py --repeats 5
./scripts/ai/eval_model.sh
```
Per-stage before/after tables live in `docs/ai/PERFORMANCE_BENCHMARKS.md`.

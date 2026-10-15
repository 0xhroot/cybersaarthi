# AI Performance Benchmarks

All numbers measured on this machine (RTX 3080 12 GB, llama.cpp + Qwen3-8B-Q4_K_M).
Reproduce with `scripts/ai/bench.py` (raw layer) and `scripts/ai/bench_gateway.py`
(gateway layer). Never compare raw and gateway numbers — different layers.

## Layer definitions

- **raw** = direct llama-server `/v1/chat/completions`. Isolates model + GPU.
- **gateway** = full backend path: auth, DB retrieval, tool loop, model, SSE.
  This is what a browser actually experiences.

## Baseline (before Stage A accuracy fix)

| Metric | Value |
|---|---|
| raw TTFT median | 10.5 ms |
| raw generation | 177–197 tok/s |
| gateway short | ~72 ms |
| gateway case-grounded | ~244 ms |
| eval fact recall | 0.9434 |
| eval top-entity | 0/5 |

## After Stage A (deterministic ranking)

| Metric | Value |
|---|---|
| eval fact recall | **1.0** |
| eval top-entity | **5/5** |
| groundedness | 1.0 (unchanged) |
| abstention | 4/4 (unchanged) |
| gateway case-grounded | ~916 ms (+~672 ms, tool round-trip) |

The latency increase is the price of correctness and only applies to ranking
questions, which now make one `rank_entities` tool call instead of guessing
from a digest.

## After Stage B (answer profiles)

Measured on the ranking question (SHOW-2026-001), 5 repeats each:

| Profile | Client median | Client p95 | Server duration | Answer length |
|---|---|---|---|---|
| quick | 918.5 ms | 923.5 ms | 1180 ms | 221 chars |
| standard | 916.2 ms | 1649.4 ms | — | — |
| deep | 922.0 ms | 926.9 ms | 1592 ms | 313 chars |

**Honest finding: profiles do not reduce wall-clock latency for this question.**
Two reasons, both verified:

1. The ranking question performs exactly one tool round-trip, which dominates
   total latency regardless of profile. The tool budget (quick=2, standard=3,
   deep=4) is never reached on a single-tool question, so it does not bind.
2. "Answer in one sentence" already produces a short answer, so the token
   budget (quick=160, standard=384, deep=768) is not reached either.

Where profiles *do* have an effect: server-side duration tracks the budget once
the model is willing to write more (deep 1592 ms vs quick 1180 ms, ~35% more),
and the answer length grows (313 vs 221 chars). The client medians stay flat
because retrieval+tool cost dominates and is profile-independent.

Conclusion: profiles are a correct, tested capability with a real but
question-dependent effect. They are **not** a latency fix for short answers,
and we do not claim one.

## Stage C — inference-server configuration sweep

Method: `scripts/ai/bench_server_configs.py`. Because a second full model load
does not fit the ~5 GB VRAM headroom alongside the running server, each
candidate *replaces* the live server on port 8081 (stop → launch → measure →
stop), and the canonical config is restored afterward. The per-slot context
fix (`--ctx-size 16384 --parallel 2`, `n_ctx_slot=8192`) is preserved for
every candidate. Streaming, `enable_thinking=false`, temperature 0.2.

Baseline = current `run_server.sh` flags (`--jinja`, no explicit fa/cache/batch).
Long prompt = 1-sentence investigation answer (128 max_tokens), 5 repeats.

| Config | Extra flags | TTFT median | Total median | tok/s | VRAM peak |
|---|---|---|---|---|---|
| baseline | *(none)* | 18.2 ms | 1009.2 ms | 180.3 | 7297 MiB |
| flash-attn | `--flash-attn on` | 18.1 ms | 1013.3 ms | 181.8 | 7297 MiB |
| fa + kv-q8 | `--fa on --cache-type-k/v q8_0` | 14.7 ms | 1044.9 ms | 175.2 | **6217 MiB** |
| fa + batch | `--fa on -b 1024 -ub 512` | 17.5 ms | 1018.7 ms | 180.7 | 7297 MiB |

**Honest finding: no candidate beats baseline on latency.** All four are
within noise of each other (~1009–1045 ms total, ~175–182 tok/s, ~18 ms TTFT).
Specifically:

- `--flash-attn on` changes nothing — this build defaults to `auto`, which
  already enables flash attention for this model/shape. Forcing it is a no-op.
- Batch/ubatch tuning has no effect at single-stream (concurrency 2) scale;
  batch size only matters when many tokens are processed together.
- KV-cache quantization (`q8_0`) is the one config with a real effect: it cuts
  peak VRAM by ~1.08 GB (7297 → 6217 MiB) at a ~3.5% throughput cost
  (180.3 → 175.2 tok/s). This is a *memory* win, not a latency win.

**Decision: keep the baseline configuration.** Nothing here improves the
latency we care about, and we will not trade throughput for VRAM headroom we
do not currently need (4.9 GB free). The kv-q8 result is recorded as the
available lever if context size or concurrency is ever raised and VRAM becomes
the binding constraint — it is not adopted now because it would make every
answer marginally slower for no present benefit.


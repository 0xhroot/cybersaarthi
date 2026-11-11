# CyberSaarthi AI — Soup Fine-Tuning Pipeline

**Status: TRAINING EXECUTED (2026-11-11) — adapter trained, candidate GGUF
exported; baseline-vs-tuned evaluation pending (Docker daemon down).**
**Verified:** 2026-10-15 (compatibility) · 2026-11-11 (execution) ·
**Soup:** `soup-cli 0.76.1` · **Model family:** Qwen3-8B

This documents the *verified* path from the current working model to a
fine-tuned candidate, the tooling built to make it safe, and the exact blocker
that stops the evaluation today. Nothing here is claimed without an executed
check. Measured numbers from the run live in
[FINE_TUNING_REPORT.md](FINE_TUNING_REPORT.md).

---

## 1. Compatibility findings (all re-verified this session)

| Question | Finding | Evidence |
|---|---|---|
| Does Soup support Python 3.14 (host)? | **No.** Soup requires 3.10–3.12; on 3.13+ pip resolves untested PyTorch wheels that crash natively. | Soup README, `soup doctor` |
| Can we get a supported interpreter? | **Yes.** `uv` (0.12.13) is installed and provisions an isolated CPython **3.12.14** — no system changes. | `uv venv --python 3.12 ai_runtime/soup/.venv` |
| Does Soup install and run? | **Yes.** Light core `soup-cli 0.76.1` installs; `soup doctor` reports all required deps OK. | `ai_runtime/soup/.venv/bin/soup doctor` |
| Is Qwen3-8B supported? | **Yes.** Shipped recipe `qwen3-8b-sft` → `Qwen/Qwen3-8B` (SFT); also `qwen3-8b-tools`, `qwen3-8b-grpo`. | `soup recipes list` |
| Does the training stack resolve on our GPU? | **Yes — installed and executed.** `soup-cli[train,liger]==0.76.1` built into `ai_runtime/soup/.venv` (Python 3.12.14): torch 2.15.0+cu132, transformers 5.22.2, peft 0.21.2, trl 0.29.1, bitsandbytes 0.50.2, liger-kernel 0.8.5. Reproducible via `scripts/ai/setup_training.sh`. | `ai_runtime/soup/.venv/bin/soup doctor` |
| Can our existing GGUF be the training base? | **No.** Soup's `base:` takes a HuggingFace checkpoint (`Qwen/Qwen3-8B`). A quantized GGUF (`Qwen3-8B-Q4_K_M.gguf`) is not a valid LoRA/QLoRA source. | Soup config schema + recipes |

**The prior "blocked: host Python 3.14 only" conclusion is now resolved** — `uv`
provides the isolated 3.12 environment Soup requires, verified by an actual
install + `soup doctor`.

## 2. Blocker status (was: two downloads before any run)

Both downloads that were deliberately held in the 2026-10-15 audit have
since been **performed and verified**:

1. **Training stack** (`soup-cli[train,liger]`): installed into the isolated
   `ai_runtime/soup/.venv` — `make train-setup` rebuilds it from scratch.
2. **Base checkpoint** (`Qwen/Qwen3-8B`, HF safetensors, ~16 GB): downloaded
   from the official Qwen org (Apache-2.0), verified, and cached at
   `~/.cache/huggingface/hub/models--Qwen--Qwen3-8B`. Training runs offline
   against this cache.

VRAM/RAM budget, now measured rather than projected: the QLoRA run peaked at
**8183 MiB** (1 Hz nvidia-smi) / **9.1 GiB** (torch allocator) of the 12 GB
RTX 3080 — after the peft fp32-upcast guard removed a 2.32 GiB waste
(root cause and fix: [FINE_TUNING_REPORT.md](FINE_TUNING_REPORT.md) §4).

**Training has been executed (exit 0, 39/39 steps, 570 s).** What remains
un-executed is the baseline-vs-tuned evaluation, blocked solely by the
Docker daemon being down (the eval harness needs the live backend).

## 3. Verified path (supported base → deployed candidate)

```
Supported base checkpoint        Qwen/Qwen3-8B  (HF safetensors, NOT the GGUF)
        │
        ▼
Curated instruction dataset      JSONL, ChatML `messages` + optional `tools`/`tool_calls`
        │                        validated & split by scripts/ai/validate_dataset.py
        ▼
LoRA / QLoRA training            soup train --config soup.yaml   (task: sft)
        │                        quantization: 4bit, lora r/alpha from template
        ▼
Adapter evaluation               compare vs unchanged Q4_K_M baseline on held-out set
        │                        (fact recall, groundedness, citation validity,
        │                         abstention, tool selection/args, security gates)
        ▼
Export to GGUF                   soup merge --adapter ./output
                                 soup export --format gguf --quant q4_k_m
        ▼
Runtime smoke test               load candidate in llama.cpp on a NON-default port
        ▼
Full evaluation                  ./scripts/ai/eval_model.sh  (hard gates)
        ▼
Optional deployment              switch via AI_MODEL_PATH config — never overwrite
                                 Qwen3-8B-Q4_K_M.gguf (the known-good baseline)
```

The working Q4_K_M model is **never overwritten**; a candidate is a separate file
selected by configuration, with a one-command rollback (point `AI_MODEL_PATH`
back at the baseline).

## 4. Dataset schema & validation tooling (built this session)

`scripts/ai/validate_dataset.py` enforces the safety/quality rules before any
example reaches a run:

- **Schema:** ChatML `messages` (roles `system|user|assistant|tool`, non-empty
  content), optional top-level `tools` (JSON-schema params, `type: object`) and
  `tool_calls` (arguments must parse as JSON and reference a *declared* tool).
- **Provenance categories** (every row must carry one): `case_qa`, `citation`,
  `ranking_tool`, `analytics_request`, `tool_args`, `abstention`, `conflict`,
  `report_draft`, `injection`, `isolation`.
- **No real data:** scans and rejects anything resembling a live case number,
  UUID, e-mail, or credential — training data is synthetic and sanitized only.
- **Dedup:** exact + normalized conversation fingerprints; duplicates rejected.
- **Leakage guard:** stratified train/val/test split (deterministic seed) with a
  hard assertion that train/val/test are pairwise disjoint.
- **Soup cross-check:** when `ai_runtime/soup` is present, each split is also run
  through Soup's own `soup data validate --format chatml`.

Run `python3 scripts/ai/validate_dataset.py --self-test` to see it validate a
synthetic set covering all ten categories (Soup's validator confirms `10/10
rows valid for chatml format`).

## 5. Scope status

- **Installed:** `soup-cli[train,liger]` in the isolated venv (multi-GB) — done.
- **Downloaded:** `Qwen/Qwen3-8B` (~16 GB) base checkpoint — done, verified.
- **Executed:** a real `soup train` run (2026-11-11): adapter trained,
  candidate GGUF exported — see [FINE_TUNING_REPORT.md](FINE_TUNING_REPORT.md).
- **Pending:** baseline-vs-tuned evaluation and the adopt/reject decision —
  blocked on the Docker daemon (`sudo systemctl start docker`).
- **Never:** treating fine-tuning as a substitute for retrieval/deterministic
  analytics — the `rank_entities` tool (Stage A) is the accuracy fix for
  rankings, and the adapter is adopted only on measured golden-set
  improvement (pre-registered decision rule, FINE_TUNING_REPORT §7).

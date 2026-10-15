# CyberSaarthi AI — Soup Fine-Tuning Pipeline

**Status: safe preparation complete; no training run performed.**
**Verified:** 2026-10-15 · **Soup:** `soup-cli 0.76.1` (light core) · **Model family:** Qwen3-8B

This documents the *verified* path from the current working model to a
fine-tuned candidate, the tooling built to make it safe, and the exact blocker
that stops a run today. Nothing here is claimed without an executed check.

---

## 1. Compatibility findings (all re-verified this session)

| Question | Finding | Evidence |
|---|---|---|
| Does Soup support Python 3.14 (host)? | **No.** Soup requires 3.10–3.12; on 3.13+ pip resolves untested PyTorch wheels that crash natively. | Soup README, `soup doctor` |
| Can we get a supported interpreter? | **Yes.** `uv` (0.12.13) is installed and provisions an isolated CPython **3.12.14** — no system changes. | `uv venv --python 3.12 ai_runtime/soup/.venv` |
| Does Soup install and run? | **Yes.** Light core `soup-cli 0.76.1` installs; `soup doctor` reports all required deps OK. | `ai_runtime/soup/.venv/bin/soup doctor` |
| Is Qwen3-8B supported? | **Yes.** Shipped recipe `qwen3-8b-sft` → `Qwen/Qwen3-8B` (SFT); also `qwen3-8b-tools`, `qwen3-8b-grpo`. | `soup recipes list` |
| Does the training stack resolve on our GPU? | **Yes (dry-run).** 57 packages resolve against CUDA 13.3 / driver 610.57.04: torch 2.14.1, transformers 5.19.0, peft 0.21.2, trl 0.29.1, bitsandbytes 0.50.2. **Not installed** — this is the multi-GB download held back pending go-ahead. | `uv pip install --dry-run "soup-cli[train]"` |
| Can our existing GGUF be the training base? | **No.** Soup's `base:` takes a HuggingFace checkpoint (`Qwen/Qwen3-8B`). A quantized GGUF (`Qwen3-8B-Q4_K_M.gguf`) is not a valid LoRA/QLoRA source. | Soup config schema + recipes |

**The prior "blocked: host Python 3.14 only" conclusion is now resolved** — `uv`
provides the isolated 3.12 environment Soup requires, verified by an actual
install + `soup doctor`.

## 2. The exact remaining blocker (before any training run)

Two multi-gigabyte downloads are **deliberately not performed** yet, per the
rule "do not install a multi-gigabyte training stack without verifying the
dependency plan first." Both plans are now verified; execution needs an explicit
go-ahead and a disk/RAM budget check:

1. **Training stack** (`soup-cli[train]`): torch + CUDA 13 wheels + peft/trl/
   bitsandbytes ≈ several GB. Dry-run resolves cleanly; not installed.
2. **Base checkpoint** (`Qwen/Qwen3-8B`, HF safetensors, ~16 GB): the model
   actually used as the LoRA base. Our working model is a *quantized GGUF* and
   cannot be used directly (see §1).

VRAM/RAM budget: QLoRA 4-bit on an 8B model needs ~5–6 GB VRAM (Soup's table
says 8 GB → ~7B; we have 12 GB). RAM is 15 GB total — tight but sufficient for
the base in 4-bit with layer streaming disabled. `soup doctor` will confirm
once torch is present (GPU currently reports "unknown (torch not installed)").

**No real training run has occurred. Fine-tuning is NOT claimed.**

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

## 5. Explicitly out of scope until go-ahead

- Installing `soup-cli[train]` (multi-GB) — plan verified, install held.
- Downloading `Qwen/Qwen3-8B` (~16 GB) — required base, not fetched.
- Any `soup train` run — blocked on the two downloads above.
- Treating fine-tuning as a substitute for retrieval/deterministic analytics —
  never; the `rank_entities` tool (Stage A) is the accuracy fix for rankings.

"""Revert peft's fp32 upcast of huge frozen tensors during kbit preparation.

Why this exists — measured on the RTX 3080 (12 GB) with Qwen3-8B QLoRA
(soup.yaml, 4bit, LoRA r16, max_length 4096):

peft.prepare_model_for_kbit_training() casts every non-quantized fp16/bf16
parameter to float32 "for stability". On Qwen3-8B the affected tensors are
embed_tokens and lm_head at 622,332,416 params each (151936 x 4096):

  before peft:  5.67 GiB resident  (4bit weights + bf16 embed/lm_head)
  after  peft:  7.99 GiB resident  (+2.32 GiB — both tensors now float32)

Measured with /tmp/probe_mem.py loading the model exactly as soup does.

The upcast buys nothing for this run: LoRA leaves those two tensors frozen
(no gradient updates reach them), and the forward pass runs under torch
autocast, which already downcasts every matmul input to bf16. It actively
HURTS: autocast's cast of the fp32 lm_head inside Liger's fused cross-entropy
(`logits_chunk = _input_chunk @ weight.t()`, liger_kernel/ops/
fused_linear_cross_entropy.py:168) materialises a fresh 151936 x 4096 bf16
copy of the whole head — exactly 151936*4096*2 = 1,244,342,272 bytes =
1.16 GiB — on every loss call. Training OOM'd on precisely that allocation
with 951 MiB free (crash bundle
.soup-crashes/crash_20261111T153734Z_2960e4af.crash, traceback ends at
liger_kernel/ops/fused_linear_cross_entropy.py line 168, "Tried to allocate
1.16 GiB").

Neither peft's signature (model, use_gradient_checkpointing,
gradient_checkpointing_kwargs, auto_clear_cache) nor soup.yaml's schema
expose a switch for this, so the guard wraps peft's function instead:

  1. snapshot every parameter's dtype,
  2. call peft's original prepare_model_for_kbit_training,
  3. cast back to their original dtype any parameter peft grew to float32
     that has >= MIN_REVERT_NUMEL elements.

On Qwen3-8B step 3 reverts exactly embed_tokens and lm_head (622M each,
saving 2.32 GiB) and leaves layer norms alone (peft's upcast of a ~4k-element
norm costs a few KiB and is harmless). The guard is idempotent: a second call
sees fp32 inputs, peft's fp16/bf16 condition no longer matches, nothing
changes.

Applied by scripts/ai/sitecustomize.py, which CPython imports at start-up
when this directory is on PYTHONPATH (train_local.sh and `make train-check`
set it). No site-packages file is modified — the patch lives entirely in this
tracked file.
"""

from __future__ import annotations

import sys
from typing import Any

# Qwen3-8B's embed_tokens / lm_head are 622M params; the next-largest
# non-quantized parameters (layer norms, rotary buffers) are ~4k. 100M
# separates "the giant frozen I/O embeddings" from everything else.
MIN_REVERT_NUMEL = 100_000_000

# Set by install(): whether a live peft installation was found and wrapped.
APPLIED = False
# Human-readable record of what the guard reverted, filled at run time.
REVERTED: list[str] = []


def _snapshot(model: Any) -> dict[int, tuple[str, Any]]:
    """Map parameter id -> (name, dtype) before peft mutates dtypes."""
    return {id(p): (name, p.dtype) for name, p in model.named_parameters()}


def revert_giant_upcasts(model: Any, snapshot: dict[int, tuple[str, Any]]) -> tuple[list[str], int]:
    """Undo peft's fp32 cast on >= MIN_REVERT_NUMEL params. Returns (names, bytes_saved).

    Only parameters whose dtype actually changed to float32 are touched, so
    this is a no-op when peft did not upcast (or already saw fp32 inputs).
    """
    import torch

    reverted: list[str] = []
    bytes_saved = 0
    for param in model.parameters():
        entry = snapshot.get(id(param))
        if entry is None:
            continue
        name, original_dtype = entry
        if param.dtype == original_dtype or param.dtype != torch.float32:
            continue
        if param.numel() < MIN_REVERT_NUMEL:
            continue
        bytes_saved += param.numel() * (param.element_size() - original_dtype.itemsize)
        param.data = param.data.to(original_dtype)
        reverted.append(f"{name} ({param.numel():,} -> {original_dtype})")

    if reverted and torch.cuda.is_available():
        # peft itself clears the cache after its bulk cast; do the same after
        # ours so the freed fp32 blocks return to the driver instead of
        # lingering as reserved-but-unused memory.
        torch.cuda.empty_cache()
    return reverted, bytes_saved


def install() -> bool:
    """Wrap peft.prepare_model_for_kbit_training in-place. Returns True if wrapped."""
    global APPLIED

    try:
        import peft
    except Exception as exc:  # peft absent (system python) — nothing to guard
        print(f"[peft-upcast-guard] peft not importable ({type(exc).__name__}), guard idle", file=sys.stderr)
        return False

    original = getattr(peft, "prepare_model_for_kbit_training", None)
    if original is None:
        print("[peft-upcast-guard] peft has no prepare_model_for_kbit_training, guard idle", file=sys.stderr)
        return False
    if getattr(original, "_cybersaarthi_upcast_guard", False):
        APPLIED = True
        return True

    def guarded(model: Any, *args: Any, **kwargs: Any) -> Any:
        snapshot = _snapshot(model)
        result = original(model, *args, **kwargs)
        reverted, saved = revert_giant_upcasts(model, snapshot)
        if reverted:
            REVERTED.extend(reverted)
            gib = saved / (1 << 30)
            print(
                f"[peft-upcast-guard] reverted fp32 upcast of {len(reverted)} giant "
                f"tensor(s), saved {gib:.2f} GiB: " + ", ".join(reverted),
                flush=True,
            )
        return result

    guarded._cybersaarthi_upcast_guard = True  # type: ignore[attr-defined]
    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    guarded.__doc__ = original.__doc__

    # Patch every namespace soup or peft-internal code might import from:
    #   `from peft import prepare_model_for_kbit_training`          (soup sft.py)
    #   `from peft.utils import ...` / `from peft.utils.other import ...`
    peft.prepare_model_for_kbit_training = guarded
    for module_name in ("peft.utils", "peft.utils.other"):
        try:
            module = __import__(module_name, fromlist=["prepare_model_for_kbit_training"])
            if getattr(module, "prepare_model_for_kbit_training", None) is original:
                setattr(module, "prepare_model_for_kbit_training", guarded)
        except Exception:
            continue

    APPLIED = True
    return True

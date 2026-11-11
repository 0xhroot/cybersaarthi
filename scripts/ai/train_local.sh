#!/usr/bin/env bash
# Run the local QLoRA training job and record how long it took and how much
# GPU memory it actually needed.
#
# The numbers this writes are the ones the fine-tuning report quotes, so they
# are measured here rather than estimated afterwards: a sampler polls
# nvidia-smi every second for the whole run and keeps the maximum.
#
# Usage:
#   scripts/ai/train_local.sh                # train from soup.yaml
#   scripts/ai/train_local.sh --dry-run      # validate only
#
# `--yes` is passed so the run is non-interactive; `--no-telemetry` (a
# top-level soup option) keeps the job strictly local.
#
# Outputs (all git-ignored, under ai_runtime/train/):
#   train.log            full Soup output
#   peak_vram.txt        peak GPU memory in MiB, sampled once a second
#   metrics.json         duration_seconds, peak_vram_mib, exit_code, command
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

SOUP="ai_runtime/soup/.venv/bin/soup"
OUT_DIR="ai_runtime/train"
LOG="$OUT_DIR/train.log"
PEAK_FILE="$OUT_DIR/peak_vram.txt"
METRICS="$OUT_DIR/metrics.json"

if [[ ! -x "$SOUP" ]]; then
  echo "error: $SOUP not found — run 'make train-check' first" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
: >"$LOG"
: >"$PEAK_FILE"

# The first real training step OOM'd on the lm_head logits allocation
# (4096 x 151936 vocab ~= 1.16 GiB) while 1.08 GiB sat reserved-but-unallocated
# — the allocator held the memory but not as one contiguous block. This hint
# lets segments grow in place instead. It is read once, at CUDA context
# creation, so it must be exported before soup starts.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

# Root cause of the step-2 OOM (measured, see scripts/ai/peft_upcast_guard.py):
# peft's prepare_model_for_kbit_training upcasts embed_tokens + lm_head to
# fp32 (+2.32 GiB resident), and autocast then materialises a 1.16 GiB bf16
# copy of that fp32 lm_head inside Liger's fused cross-entropy — the exact
# allocation that failed with 951 MiB free. Putting scripts/ai on PYTHONPATH
# makes CPython import sitecustomize.py at start-up, which wraps peft and
# reverts the upcast for tensors >= 100M params. The venv's own
# site-packages are never modified.
export PYTHONPATH="$REPO/scripts/ai${PYTHONPATH:+:$PYTHONPATH}"

peak_mib=0
sampler_pid=""

sampler() {
  local current
  while true; do
    current="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)"
    [[ "$current" =~ ^[0-9]+$ ]] || { sleep 1; continue; }
    if (( current > peak_mib )); then
      peak_mib="$current"
      echo "$peak_mib" >"$PEAK_FILE"
    fi
    sleep 1
  done
}

cleanup() {
  [[ -n "$sampler_pid" ]] && kill "$sampler_pid" 2>/dev/null
  wait "$sampler_pid" 2>/dev/null
}
trap cleanup EXIT

sampler &
sampler_pid=$!

# `--no-telemetry` is a top-level `soup` option, so it precedes `train`.
CMD=("$SOUP" --no-telemetry train --config soup.yaml --yes "$@")
echo "command: ${CMD[*]}" | tee -a "$LOG"
started="$(date +%s)"
"${CMD[@]}" >>"$LOG" 2>&1
code=$?
finished="$(date +%s)"

cleanup
trap - EXIT

duration=$(( finished - started ))
[[ -s "$PEAK_FILE" ]] && peak_mib="$(cat "$PEAK_FILE")"

cat >"$METRICS" <<EOF
{
  "command": "${CMD[*]}",
  "duration_seconds": $duration,
  "peak_vram_mib": $peak_mib,
  "exit_code": $code
}
EOF

echo "duration_seconds=$duration peak_vram_mib=$peak_mib exit_code=$code"
echo "log: $LOG"
tail -n 25 "$LOG"
exit "$code"

"""Imported automatically by CPython at interpreter start-up (the `site` module
imports `sitecustomize` if it is importable).

Its only job: install the peft upcast guard (see peft_upcast_guard.py) so that
`soup train` runs with peft's fp32 upcast of embed_tokens/lm_head reverted.

It activates exactly when this directory is on PYTHONPATH — train_local.sh and
`make train-check` set it, nothing else in the repo does — so ordinary python
invocations (dataset generation, validation, compare_eval) are unaffected
unless they are launched from within scripts/ai, in which case the guard is a
no-op anyway: it only acts on a successful `import peft`, and it never raises.
"""

try:
    from peft_upcast_guard import install

    install()
except Exception as exc:  # never break interpreter start-up over an optional guard
    print(f"[sitecustomize] peft upcast guard not installed: {type(exc).__name__}: {exc}", flush=True)

#!/usr/bin/env python3
"""Benchmark alternative llama-server configurations on the live GPU.

A second full model load does not fit the ~5 GB VRAM headroom alongside the
running server, so each candidate is benchmarked by *replacing* the live
server: stop it, launch the candidate on the same port, measure, then stop the
candidate. The canonical server is restored at the end (or the winning config
is adopted when --adopt is passed).

The per-slot context fix (ctx = AI_CONTEXT_LENGTH * parallel) is preserved for
every candidate. Nothing here lowers context below the known-good budget.

Usage (from repo root):
  python3 scripts/ai/bench_server_configs.py                 # compare only
  python3 scripts/ai/bench_server_configs.py --adopt best    # restart as best

Safety: kills llama-server/socat by exact PID only (never pkill -f). Always
restores a running server in a finally block, even on error.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "ai_runtime" / "llama.cpp" / "llama-server"
MODEL = REPO / "Qwen3-8B-Q4_K_M.gguf"
HOST = "127.0.0.1"
PORT = int(os.environ.get("AI_SERVER_PORT", "8081"))
CTX = int(os.environ.get("AI_CONTEXT_LENGTH", "8192"))
PARALLEL = int(os.environ.get("AI_SERVER_PARALLEL", "2"))
HEALTH = f"http://{HOST}:{PORT}/health"
COMPLETIONS = f"http://{HOST}:{PORT}/v1/chat/completions"

# Reproducible prompts: one trivial (measures TTFT/generation), one that
# stresses prompt processing with a longer input.
SHORT_PROMPT = "Reply with exactly: pong"
LONG_PROMPT = (
    "You are a cybersecurity assistant. Explain, in one paragraph, how an "
    "investigator should triage a suspicious wire transfer in a fraud case. "
    "Mention evidence to collect, entities to link, and a next step."
)


def _api_key() -> str:
    key = os.environ.get("AI_SERVER_API_KEY", "")
    if key:
        return key
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("AI_SERVER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _pids(name: str) -> list[int]:
    out = subprocess.run(
        ["pgrep", "-x", name], capture_output=True, text=True, check=False
    )
    return [int(p) for p in out.stdout.split() if p.strip()]


def _stop_all(name: str) -> None:
    """Stop every process of ``name`` by exact PID (never pkill -f)."""
    for pid in _pids(name):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _pids(name):
        time.sleep(0.3)
    for pid in _pids(name):  # force if still alive
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _vram_used_mib() -> int:
    out = subprocess.run(
        [
            "nvidia-smi", "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True, text=True, check=False,
    )
    try:
        return int(out.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def _start(extra_args: list[str]) -> None:
    """Launch llama-server directly with the canonical flags + ``extra_args``.

    Mirrors run_server.sh's policy (per-slot ctx fix, full GPU offload, jinja,
    api-key when set) so a candidate differs from baseline only by the extra
    flags being benchmarked.
    """
    env = dict(os.environ)
    args = [
        str(BIN),
        "--model", str(MODEL),
        "--host", HOST,
        "--port", str(PORT),
        # per-slot context fix: total = per-slot * parallel
        "--ctx-size", str(CTX * PARALLEL),
        "--n-gpu-layers", "-1",
        "--parallel", str(PARALLEL),
        "--no-webui",
        "--jinja",
    ]
    key = _api_key()
    if key:
        args += ["--api-key", key]
    args += extra_args
    lib_dir = REPO / "ai_runtime" / "llama.cpp"
    env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"
    log = open("/tmp/llama_candidate.log", "w")
    subprocess.Popen(
        args, stdout=log, stderr=log, start_new_session=True, cwd=str(REPO)
    )


def _wait_healthy(timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout
    key = _api_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    while time.monotonic() < deadline:
        try:
            r = httpx.get(HEALTH, headers=headers, timeout=3)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    return False


def _bench(prompt: str, repeats: int, max_tokens: int) -> dict:
    key = _api_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    ttfts: list[float] = []
    totals: list[float] = []
    tps: list[float] = []
    with httpx.Client() as client:
        for _ in range(repeats):
            payload = {
                "model": "local",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": True,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            start = time.monotonic()
            ttft = None
            chars = 0
            with client.stream(
                "POST", COMPLETIONS, json=payload, headers=headers,
                timeout=httpx.Timeout(300.0),
            ) as resp:
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    if ttft is None:
                        ttft = (time.monotonic() - start) * 1000
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    chars += len(delta.get("content") or "")
            total = (time.monotonic() - start) * 1000
            if ttft is not None:
                ttfts.append(ttft)
            totals.append(total)
            if total:
                tps.append(max(1, chars // 4) / (total / 1000))
            time.sleep(0.4)
    result = {
        "total_ms_median": round(statistics.median(totals), 1) if totals else None,
        "total_ms_p95": round(_pct(totals, 0.95), 1) if totals else None,
        "tokens_per_s_median": round(statistics.median(tps), 1) if tps else None,
    }
    if ttfts:
        result["ttft_ms_median"] = round(statistics.median(ttfts), 1)
        result["ttft_ms_p95"] = round(_pct(ttfts, 0.95), 1)
    return result


def bench_config(name: str, extra_args: list[str]) -> dict:
    print(f"\n=== [{name}] {extra_args or '(baseline flags)'} ===", flush=True)
    _stop_all("llama-server")
    _stop_all("socat")
    sock = REPO / "ai_runtime" / "llama.sock"
    if sock.exists():
        sock.unlink()
    _start(extra_args)
    if not _wait_healthy():
        with open("/tmp/llama_candidate.log") as fh:
            tail = fh.read()[-1500:]
        print(f"  FAILED to become healthy. log tail:\n{tail}", flush=True)
        _stop_all("llama-server")
        return {"name": name, "args": extra_args, "healthy": False}
    vram_idle = _vram_used_mib()
    short = _bench(SHORT_PROMPT, repeats=7, max_tokens=32)
    long_ = _bench(LONG_PROMPT, repeats=5, max_tokens=128)
    vram_peak = _vram_used_mib()
    result = {
        "name": name,
        "args": extra_args,
        "healthy": True,
        "vram_idle_mib": vram_idle,
        "vram_peak_mib": vram_peak,
        "short": short,
        "long": long_,
    }
    print(f"  vram idle={vram_idle} peak={vram_peak}", flush=True)
    print(f"  short: {short}", flush=True)
    print(f"  long : {long_}", flush=True)
    _stop_all("llama-server")
    return result


# Candidate configurations. Each entry: (name, extra llama-server args).
# flash attention and KV-cache quantization are the two safe levers that can
# cut memory and latency on this 12 GB card without touching model quality
# gates (which the golden eval guards separately).
CANDIDATES: list[tuple[str, list[str]]] = [
    ("baseline", []),
    ("flash-attn", ["--flash-attn", "on"]),
    ("fa+kv-q8", ["--flash-attn", "on", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]),
    ("fa+batch1024", ["--flash-attn", "on", "--batch-size", "1024", "--ubatch-size", "512"]),
]


def _restore_canonical() -> None:
    """Restart the normal run_server.sh + socket bridge (known-good config)."""
    _stop_all("llama-server")
    _stop_all("socat")
    sock = REPO / "ai_runtime" / "llama.sock"
    if sock.exists():
        sock.unlink()
    # run_server.sh requires AI_SERVER_API_KEY in its environment when binding
    # to 0.0.0.0; pass it explicitly so the restore can never fail on a missing
    # key (a subprocess started via setsid does not inherit a sourced .env).
    env = dict(os.environ)
    key = _api_key()
    if key:
        env["AI_SERVER_API_KEY"] = key
    subprocess.Popen(
        ["setsid", "-f", str(REPO / "scripts" / "ai" / "run_server.sh")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(REPO),
        env=env,
    )
    subprocess.Popen(
        ["setsid", "-f", str(REPO / "scripts" / "ai" / "socket_bridge.sh")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(REPO),
        env=env,
    )
    _wait_healthy()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=REPO / "ai_runtime" / "bench_configs.json")
    ap.add_argument(
        "--adopt", choices=[c[0] for c in CANDIDATES], default=None,
        help="restart the server as this config after benchmarking",
    )
    args = ap.parse_args()

    if not BIN.exists():
        print("llama-server binary missing; run scripts/ai/setup_runtime.sh", file=sys.stderr)
        return 2

    results = []
    try:
        for name, extra in CANDIDATES:
            results.append(bench_config(name, extra))
    finally:
        # Always restore a working server, even on error/interrupt.
        if args.adopt:
            winner = next(c for c in CANDIDATES if c[0] == args.adopt)
            print(f"\n=== adopting config: {args.adopt} ===", flush=True)
            _stop_all("llama-server")
            _stop_all("socat")
            sock = REPO / "ai_runtime" / "llama.sock"
            if sock.exists():
                sock.unlink()
            _start(winner[1])
            _wait_healthy()
            # Re-establish the socket bridge so the backend can reach it.
            subprocess.Popen(
                ["setsid", "-f", str(REPO / "scripts" / "ai" / "socket_bridge.sh")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(REPO),
            )
        else:
            print("\n=== restoring canonical server ===", flush=True)
            _restore_canonical()

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {args.json}", flush=True)

    # Summary table
    print("\n=== summary (long prompt) ===")
    for r in results:
        if not r.get("healthy"):
            print(f"  {r['name']:16} FAILED")
            continue
        lg = r["long"]
        print(
            f"  {r['name']:16} ttft={lg.get('ttft_ms_median')}ms "
            f"total={lg.get('total_ms_median')}ms tok/s={lg.get('tokens_per_s_median')} "
            f"vram_peak={r['vram_peak_mib']}MiB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

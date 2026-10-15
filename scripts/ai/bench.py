#!/usr/bin/env python3
"""Reproducible latency/throughput benchmark for the local AI stack.

Measures two layers separately so numbers are never compared across layers:
  1. RAW    — direct llama-server /v1/chat/completions (no FastAPI, no DB).
  2. GATEWAY — through the backend /api/v1/ai/chat (auth + retrieval + tools).

Reports median and p95 for request-to-first-token (TTFT), end-to-end latency,
and tokens/s. Usage:
  python3 scripts/ai/bench.py                      # raw, default prompts
  python3 scripts/ai/bench.py --layer gateway      # through backend
  python3 scripts/ai/bench.py --repeats 9 --stream
  python3 scripts/ai/bench.py --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LLAMA = "http://127.0.0.1:8081/v1/chat/completions"
DEFAULT_GATEWAY = "http://localhost:8000/api/v1/ai/chat"


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


def _summarise(name: str, samples: list[dict]) -> dict:
    ttft = [s["ttft_ms"] for s in samples if s.get("ttft_ms") is not None]
    total = [s["total_ms"] for s in samples]
    tps = [s["tokens_per_s"] for s in samples if s.get("tokens_per_s")]
    out = {"name": name, "n": len(samples)}
    if ttft:
        out["ttft_ms"] = {
            "median": round(statistics.median(ttft), 1),
            "p95": round(_pct(ttft, 0.95), 1),
        }
    out["total_ms"] = {
        "median": round(statistics.median(total), 1),
        "p95": round(_pct(total, 0.95), 1),
    }
    if tps:
        out["tokens_per_s"] = {
            "median": round(statistics.median(tps), 1),
            "min": round(min(tps), 1),
        }
    return out


async def bench_raw(
    client: httpx.AsyncClient, url: str, key: str, prompt: str,
    repeats: int, max_tokens: int, stream: bool,
) -> list[dict]:
    samples = []
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    for i in range(repeats):
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        start = time.monotonic()
        ttft = None
        chars = 0
        if stream:
            async with client.stream(
                "POST", url, json=payload, headers=headers,
                timeout=httpx.Timeout(300.0),
            ) as resp:
                async for line in resp.aiter_lines():
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
        else:
            resp = await client.post(
                url, json=payload, headers=headers, timeout=httpx.Timeout(300.0)
            )
            resp.raise_for_status()
            body = resp.json()
            chars = len(body["choices"][0]["message"].get("content") or "")
            ttft = None
        total = (time.monotonic() - start) * 1000
        # ~4 chars/token heuristic for throughput estimate when usage absent.
        est_tokens = max(1, chars // 4)
        samples.append({
            "ttft_ms": ttft,
            "total_ms": round(total, 1),
            "tokens_per_s": round(est_tokens / (total / 1000), 1) if total else None,
        })
        await asyncio.sleep(0.4)
    return samples


PROMPTS = {
    "short": "Reply with exactly: pong",
    "medium": "In one sentence, what is a firewall?",
    "case": (
        "Which entity is the most connected in this case and how many "
        "relationships does it have? Answer in one sentence."
    ),
}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", choices=["raw", "gateway"], default="raw")
    ap.add_argument("--repeats", type=int, default=7)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--prompt", choices=list(PROMPTS), default="short")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    async with httpx.AsyncClient() as client:
        if args.layer == "raw":
            samples = await bench_raw(
                client, DEFAULT_LLAMA, _api_key(), PROMPTS[args.prompt],
                args.repeats, args.max_tokens, args.stream,
            )
            report = _summarise(f"raw:{args.prompt}", samples)
        else:
            print("gateway layer requires auth; use scripts/ai/bench_gateway.py", file=sys.stderr)
            return 2

    print(json.dumps(report, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

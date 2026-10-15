#!/usr/bin/env python3
"""Gateway-layer latency benchmark: full backend path (auth + retrieval + tools).

Complements scripts/ai/bench.py (raw llama-server). Never compare raw and
gateway numbers directly — they measure different layers.

Usage:
  cd backend && ../scripts/ai/bench_gateway.py
  cd backend && ../scripts/ai/bench_gateway.py --repeats 5 --profile quick
  cd backend && ../scripts/ai/bench_gateway.py --json ../ai_runtime/bench_gateway.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

API_BASE = "http://localhost:8000/api/v1"

# Reproducible prompts: one short general, one case-grounded ranking question.
SHORT_PROMPT = "Reply with exactly: pong"
CASE_NUMBER = "SHOW-2026-001"
CASE_PROMPT = (
    "Which entity is the most connected in this case and how many "
    "relationships does it have? Answer in one sentence."
)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _summarise(name: str, samples: list[dict]) -> dict:
    total = [s["total_ms"] for s in samples]
    ttft = [s["ttft_ms"] for s in samples if s.get("ttft_ms") is not None]
    out = {
        "name": name,
        "n": len(samples),
        "total_ms": {
            "median": round(statistics.median(total), 1),
            "p95": round(_pct(total, 0.95), 1),
        },
    }
    if ttft:
        out["ttft_ms"] = {
            "median": round(statistics.median(ttft), 1),
            "p95": round(_pct(ttft, 0.95), 1),
        }
    return out


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        f"{API_BASE}/auth/login", json={"username": username, "password": password}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def bench_prompt(
    client: httpx.AsyncClient, headers: dict, prompt: str,
    case_id: str | None, repeats: int,
) -> list[dict]:
    samples = []
    for _ in range(repeats):
        payload: dict = {"question": prompt}
        if case_id:
            payload["mode"] = "case"
            payload["case_id"] = case_id
        start = time.monotonic()
        resp = await client.post(
            f"{API_BASE}/ai/chat", json=payload, headers=headers,
            timeout=httpx.Timeout(180.0),
        )
        total = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        samples.append({"total_ms": round(total, 1), "ttft_ms": None})
        await asyncio.sleep(3.5)  # stay under per-user rate limit
    return samples


async def resolve_case(
    client: httpx.AsyncClient, headers: dict, case_number: str
) -> str | None:
    resp = await client.get(
        f"{API_BASE}/cases", params={"search": case_number}, headers=headers
    )
    if resp.status_code != 200:
        return None
    for item in resp.json().get("items", []):
        if item.get("case_number") == case_number:
            return item["id"]
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--username", default="investigator")
    ap.add_argument("--password", default="investigator-dev-password")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    async with httpx.AsyncClient() as client:
        token = await login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        case_id = await resolve_case(client, headers, CASE_NUMBER)

        short = await bench_prompt(client, headers, SHORT_PROMPT, None, args.repeats)
        report = [_summarise("gateway:short", short)]
        if case_id:
            case = await bench_prompt(
                client, headers, CASE_PROMPT, case_id, args.repeats
            )
            report.append(_summarise(f"gateway:case[{CASE_NUMBER}]", case))
        else:
            print(f"WARNING: {CASE_NUMBER} not found; case bench skipped", file=sys.stderr)

    print(json.dumps(report, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

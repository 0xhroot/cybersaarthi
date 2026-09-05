#!/usr/bin/env python3
"""Drive the SIH demo evidence set through the REAL CyberSaarthi API.

Creates the case (if absent), uploads the three generated evidence files,
runs real ingestion, then verifies entities/relationships/analytics/findings.
Prints timing for each step so the rehearsal document can record real numbers.

Usage (from repo root):
    python3 docs/scripts/run_sih_seed.py admin admin-dev-password
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid

API = os.environ.get("SIH_API", "http://localhost:8000")
SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "backend", "scripts", "sih_demo_seed")
CASE_TITLE = "SIH 2026 Demonstration - Synthesised criminal network analysis"

FILES = [
    ("csv", "persons.csv"),
    ("json", "transfers.json"),
    ("txt", "associations.txt"),
]


class Api:
    def __init__(self, token: str) -> None:
        self.token = token

    def _open(self, method: str, path: str, body=None, multipart: bool = False, files=None, data=None):
        url = f"{API}/api/v1{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        if body is not None and not multipart:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode()
        elif multipart:
            boundary = uuid.uuid4().hex
            chunks = []
            for field, value in data or {}:
                chunks.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"\r\n\r\n{value}\r\n".encode()
                )
            for fname, fbytes, ctype in files or []:
                chunks.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
                    f"Content-Type: {ctype}\r\n\r\n".encode() + fbytes + b"\r\n"
                )
            chunks.append(f"--{boundary}--\r\n".encode())
            payload = b"".join(chunks)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            payload = None

        t0 = time.time()
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
        dt = time.time() - t0
        text = raw.decode()
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text
        return status, parsed, dt

    def request(self, method: str, path: str, **kw):
        status, parsed, dt = self._open(method, path, **kw)
        if status >= 400:
            raise RuntimeError(f"{method} {path} -> {status}: {parsed}")
        return parsed, dt


def fmt(dt: float) -> str:
    return f"{dt:.2f}s"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("username", default=os.environ.get("SIH_USERNAME", "admin"))
    parser.add_argument("password", default=os.environ.get("SIH_PASSWORD", "admin-dev-password"))
    args = parser.parse_args()

    print("== SIH demo: real-mode pipeline driver ==")
    t = time.time()
    login_req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=json.dumps({"username": args.username, "password": args.password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login_req) as resp:
        creds = json.loads(resp.read())
    print(f"login: {fmt(time.time() - t)} (user={args.username})")
    api = Api(creds["access_token"])

    # --- Find or create the case ---
    t = time.time()
    cases, _ = api.request("GET", "/cases?limit=200")
    items = cases.get("items", [])
    case = next((c for c in items if c.get("title") == CASE_TITLE), None)
    if case is None:
        case, _ = api.request("POST", "/cases", body={
            "title": CASE_TITLE,
            "description": "Large deterministic synthetic dataset exercising entity resolution, "
                           "knowledge graph, and investigation analytics (no real data).",
            "status": "in_progress",
        })
    case_id = case["id"]
    print(f"case: {case['case_number']} ({case_id}) [{fmt(time.time() - t)}]")

    # --- Upload + ingest each evidence file ---
    evidence_ids = {}
    for fmt_name, fname in FILES:
        path = os.path.join(SEED_DIR, fname)
        with open(path, "rb") as fh:
            content = fh.read()
        status, ev, dt = api._open(
            "POST", f"/cases/{case_id}/evidence", multipart=True,
            files=[(fname, content, "application/octet-stream")],
            data=[("data_source", fmt_name)],
        )
        if status == 409:
            # Duplicate by SHA-256 already stored; look it up via the list.
            listing, _ = api.request("GET", f"/cases/{case_id}/evidence?limit=200")
            ev = next((e for e in listing.get("items", []) if e.get("original_filename") == fname), None)
            if ev is None:
                raise RuntimeError(f"duplicate {fname} but not found in list")
            print(f"evidence {fname}: already present (dedupe) -> {ev['id']}")
        else:
            assert status == 201, f"evidence upload failed: {status} {ev}"
            print(f"evidence {fname}: uploaded {fmt(dt)} -> {ev['id']} (sha256={ev['sha256'][:12]}...)")
        eid = ev["id"]
        evidence_ids[fname] = eid

        status, job, dt = api._open(
            "POST", f"/cases/{case_id}/ingest",
            body={"evidence_file_id": eid},
        )
        assert status == 200, f"ingest failed: {status} {job}"
        j = job.get("job", {})
        summary = j.get("summary") or {}
        print(
            f"ingest {fname}: {fmt(dt)} job={j.get('status')} graph_sync={j.get('graph_sync_status')} "
            f"duplicate={job.get('duplicate')}"
        )
        if summary:
            print(f"    summary: {json.dumps(summary)[:500]}")

    # --- Entity / relationship / evidence counts ---
    for path, label in [
        (f"/cases/{case_id}/entities?limit=1", "entities"),
        (f"/cases/{case_id}/relationships?limit=1", "relationships"),
        (f"/cases/{case_id}/evidence", "evidence"),
    ]:
        try:
            body, _ = api.request("GET", path)
            total = body.get("total")
            print(f"{label}: total={total}")
        except Exception as exc:
            print(f"{label}: ERROR {exc}")

    # --- Analytics run ---
    t = time.time()
    run, _ = api.request("POST", f"/cases/{case_id}/analytics/run", body={})
    print(f"analytics run: {fmt(time.time() - t)} status={run.get('status')} ")

    # Summary of metrics
    try:
        summary, _ = api.request("GET", f"/cases/{case_id}/analytics/summary")
        print("analytics summary:", json.dumps(summary)[:600])
    except Exception as exc:
        print("analytics summary ERROR:", exc)

    # findings
    try:
        findings, _ = api.request("GET", f"/cases/{case_id}/findings?limit=10")
        fcount = findings.get("total", len(findings.get("items", [])))
        print(f"findings: total={fcount}")
    except Exception as exc:
        print("findings ERROR:", exc)

    print("DONE case_id=", case_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
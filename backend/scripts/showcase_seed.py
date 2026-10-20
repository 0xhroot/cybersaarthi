"""SIH Showcase seed - one polished demo case, built through the REAL API.

Drives the actual application workflows (case creation, multipart evidence
upload, ingestion, custody events, intelligence jobs, human-style reviews,
report generation, report audit) so every artifact a judge sees was produced
by the product itself, never by direct database insertion. The only rows the
destructive reset ever writes/deletes are the showcase cases themselves.

Subcommands (see the Makefile targets `demo-seed`, `demo-status`, `demo-reset`):

    python -m scripts.showcase_seed seed      # idempotent; safe to re-run
    python -m scripts.showcase_seed status    # read-only capability checklist
    python -m scripts.showcase_seed reset     # DESTROYS ONLY the showcase cases
                                              # (requires DEMO_RESET_CONFIRM=sih-showcase)

Idempotency: cases are found by their unique SIH-2026-xxx case_number,
evidence by original filename (plus the server's sha256 409 dedupe),
custody events by (event_type, occurred_at), intelligence jobs by any
terminal successful attempt, report audits by the exact sha256 of the draft,
analytics by an existing finding_count, reports by report_type, timeline
proposals by their own proposal_key. Re-running `seed` never duplicates
logical data and never touches non-showcase cases.

Environment:
    CS_SHOWCASE_USER / CS_SHOWCASE_PASSWORD     login (default admin / admin-dev-password)
    CS_SHOWCASE_MEMBER_USER/PASSWORD            presenter account added as member
                                                (default investigator / investigator-dev-password)
    CS_API_BASE                                 default http://localhost:8000
    CS_SEED_JOB_TIMEOUT                         per-job wait seconds (default 420)
    CS_SEED_RETRY_FAILED=1                      re-submit failed or partial attempts
    DEMO_RESET_CONFIRM=sih-showcase             required for `reset`

Guards: nothing runs when APP_ENV=production; `reset` additionally requires
the explicit confirmation value above and deletes only the two SIH-2026-xxx
case numbers (never a LIKE/prefix sweep).

All seeded content is fictional synthetic data - see docs/demo/SIH_SHOWCASE.md.
The SIH-2026-xxx case-number convention is the smallest schema-compatible
demo/real distinction (the Case model has no tag/metadata column).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).parent / "showcase_fixtures"

PRIMARY_CASE = {
    "case_number": "SIH-2026-001",
    "title": "SIH Showcase - Sunrise Mercantile payment-diversion fraud",
    "description": (
        "SYNTHETIC DEMO CASE (SIH Showcase) - every name, account, transaction and hash is "
        "fictional. A complainant's account was drained through transfers to a beneficiary "
        "account impersonating a merchant; a wallet ledger contradicts the bank statement "
        "for the same transaction reference. Objective: reconcile the two sources, resolve "
        "the entity aliases, map the money trail and produce an auditor-reviewed report."
    ),
    "status": "in_progress",
}
SUPPORT_CASE = {
    "case_number": "SIH-2026-002",
    "title": "DEMO FIXTURE - related merchant payment inquiries (cross-case support)",
    "description": (
        "SYNTHETIC DEMO FIXTURE for the SIH Showcase. Holds a minimal second payment record "
        "that shares one beneficiary account and phone number with SIH-2026-001 so the "
        "cross-case pattern engine has the two authorized cases its contract requires. Not "
        "an independent investigation."
    ),
    "status": "in_progress",
}
SHOWCASE_CASE_NUMBERS = (PRIMARY_CASE["case_number"], SUPPORT_CASE["case_number"])

# (filename, data_source, content_type, case_number) - fixtures committed in
# showcase_fixtures/, all fictional.
PRIMARY_FILES = [
    ("complaint_mixed.txt", "txt", "text/plain", PRIMARY_CASE["case_number"]),
    ("merchant_statement.csv", "csv", "text/csv", PRIMARY_CASE["case_number"]),
    ("wallet_ledger.json", "json", "application/json", PRIMARY_CASE["case_number"]),
    ("entity_review.csv", "csv", "text/csv", PRIMARY_CASE["case_number"]),
    ("phishing_urls.txt", "txt", "text/plain", PRIMARY_CASE["case_number"]),
    ("hash_manifest.csv", "csv", "text/csv", PRIMARY_CASE["case_number"]),
]
SUPPORT_FILES = [
    ("supporting_payments.csv", "csv", "text/csv", SUPPORT_CASE["case_number"]),
]

# Append-only custody chain for the two primary exhibits. (event_type,
# occurred_at) is the natural idempotency key: a duplicate pair would raise
# custody.duplicate_event, so the seed never double-posts.
CUSTODY_CHAIN = [
    {
        "event_type": "collected",
        "occurred_at": "2026-04-13T09:30:00+05:30",
        "collector": "SIH demo custody agent Meera Joshi (synthetic)",
        "location": "Prism Cooperative Bank Demo Branch (fictional)",
        "method": "encrypted demo transfer",
        "notes": "Synthetic SIH showcase: original export collected for examination.",
    },
    {
        "event_type": "transferred",
        "occurred_at": "2026-04-13T14:00:00+05:30",
        "transferor": "Meera Joshi (synthetic)",
        "recipient": "Forensic desk officer Sunil Iyer (synthetic)",
        "location": "Cyber Cell Demo Lab (fictional)",
        "method": "encrypted demo transfer",
        "notes": "Synthetic SIH showcase: handed to the forensic desk.",
    },
    {
        "event_type": "received",
        "occurred_at": "2026-04-13T16:00:00+05:30",
        "recipient": "Forensic desk officer Sunil Iyer (synthetic)",
        "location": "Cyber Cell Demo Lab (fictional)",
        "notes": "Synthetic SIH showcase: receipt acknowledged at the forensic desk.",
    },
    {
        "event_type": "verified",
        "occurred_at": "2026-04-14T10:15:00+05:30",
        "notes": "Synthetic SIH showcase: sha256 recomputed and matched the intake hash.",
    },
]
CUSTODY_FILES = ("merchant_statement.csv", "complaint_mixed.txt")

# Narrative anchors whose dates agree with the evidence; record-derived dates
# are added separately by committing real reconstruction proposals.
CURATED_TIMELINE = [
    {
        "occurred_at": "2026-04-02T10:15:00+05:30",
        "kind": "case_event",
        "title": "Complaint CMP-SIH-2026-0417 received",
        "description": (
            "Fictional complainant Ananya Deshpande reports unauthorised transfers; the "
            "synthetic complaint (mixed Hindi/English) is ingested as evidence."
        ),
        "evidence_file": "complaint_mixed.txt",
    },
    {
        "occurred_at": "2026-04-13T09:30:00+05:30",
        "kind": "case_event",
        "title": "Bank statement and complaint sealed into custody",
        "description": "Chain of custody opened for the two primary exhibits.",
        "evidence_file": "merchant_statement.csv",
    },
    {
        "occurred_at": "2026-04-14T10:15:00+05:30",
        "kind": "case_event",
        "title": "Custody verification recomputed sha256 - match",
        "description": "Integrity check re-hashed the stored object against intake records.",
        "evidence_file": "merchant_statement.csv",
    },
]

DRAFT_TEMPLATE = FIXTURES_DIR / "report_draft.tpl.md"
# Deliberately non-existent citation target for the planted unsupported claim.
DRAFT_MISSING_CITE = "00000000-0000-4000-8000-000000000000"

# Job feature -> submit path segment (two features do not equal their slug).
FEATURE_SUBMIT_PATHS = {
    "entity_resolution": "entity-resolution",
    "timeline": "timeline-reconstruction",
    "contradiction": "contradiction-detection",
    "financial_flow": "financial-flow",
    "multilingual": "multilingual",
    "triage": "triage",
}

TERMINAL = {"succeeded", "partial", "failed", "canceled"}
DONE_OK = {"succeeded", "partial"}
ACTIVE = {"pending", "running"}


@dataclass
class Step:
    name: str
    action: str  # created | existing | skipped | pending | failed
    detail: str = ""


@dataclass
class SeedReport:
    steps: list[Step] = field(default_factory=list)

    def add(self, name: str, action: str, detail: str = "") -> None:
        self.steps.append(Step(name, action, detail))

    @property
    def failed(self) -> list[Step]:
        return [s for s in self.steps if s.action == "failed"]

    def render(self) -> str:
        lines = [
            f"  {s.action.upper():8s} {s.name}" + (f" - {s.detail}" if s.detail else "")
            for s in self.steps
        ]
        counts: dict[str, int] = {}
        for s in self.steps:
            counts[s.action] = counts.get(s.action, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        return "\n".join(lines) + f"\n  => {summary}"


# --- low-level HTTP -----------------------------------------------------------


async def _get(client: httpx.AsyncClient, path: str, **params):
    resp = await client.get(path, params=params or None)
    resp.raise_for_status()
    return resp.json()


async def _post(client: httpx.AsyncClient, path: str, expected: tuple[int, ...], **kwargs):
    resp = await client.post(path, **kwargs)
    if resp.status_code not in expected:
        raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:400]}")
    return resp.json() if resp.content else None


async def _list_all(client: httpx.AsyncClient, path: str, *, limit: int = 200, **params):
    """Page a list endpoint until ``total`` rows are collected."""
    items: list[dict] = []
    offset = 0
    while True:
        data = await _get(client, path, limit=limit, offset=offset, **params)
        chunk = data.get("items", [])
        items.extend(chunk)
        total = data.get("total", len(items))
        offset += len(chunk)
        if not chunk or offset >= total:
            return items


def _utc_instant(occurred_at: str) -> str:
    """Normalize an ISO-8601 timestamp for duplicate detection.

    The API stores/returns instants as ``...Z`` (UTC) while the seed supplies
    ``+05:30`` offsets; naive prefix comparison would miss real duplicates and
    re-post them (the timeline endpoint has no server-side dedupe).
    """
    try:
        dt = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        return occurred_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


async def login(base_url: str, username: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=f"{base_url}/api/v1", timeout=60) as client:
        resp = await client.post("/auth/login", json={"username": username, "password": password})
        if resp.status_code != 200:
            raise SystemExit(f"login failed for {username!r}: {resp.status_code} {resp.text[:200]}")
        return resp.json()["access_token"]


# --- steps --------------------------------------------------------------------


async def find_case(client: httpx.AsyncClient, case_number: str):
    items = await _list_all(client, "/cases", limit=200)
    return next((c for c in items if c.get("case_number") == case_number), None)


async def ensure_case(client: httpx.AsyncClient, spec: dict, report: SeedReport):
    existing = await find_case(client, spec["case_number"])
    if existing:
        report.add(f"case {spec['case_number']}", "existing", existing["id"])
        return existing
    created = await _post(client, "/cases", expected=(201,), json=spec)
    report.add(f"case {spec['case_number']}", "created", created["id"])
    return created


async def ensure_member(client: httpx.AsyncClient, case_id: str, user_id: str, report: SeedReport):
    members = await _get(client, f"/cases/{case_id}/members")
    if any(m["user_id"] == user_id for m in members.get("items", [])):
        report.add("case member (presenter account)", "existing", user_id)
        return
    await _post(
        client,
        f"/cases/{case_id}/members",
        expected=(200, 201),
        json={"user_id": user_id, "role": "collaborator"},
    )
    report.add("case member (presenter account)", "created", user_id)


async def _case_evidence(client: httpx.AsyncClient, case_id: str) -> list[dict]:
    return await _list_all(client, f"/cases/{case_id}/evidence", limit=200)


async def ensure_evidence(
    client: httpx.AsyncClient,
    case_id: str,
    fname: str,
    data_source: str,
    content_type: str,
    report: SeedReport,
) -> dict:
    for ev in await _case_evidence(client, case_id):
        if ev.get("original_filename") == fname:
            report.add(f"evidence {fname}", "existing", ev["id"])
            return ev
    blob = (FIXTURES_DIR / fname).read_bytes()
    metadata = json.dumps({"synthetic": True, "sih_showcase": True, "fixture": fname})
    resp = await client.post(
        f"/cases/{case_id}/evidence",
        files={"file": (fname, blob, content_type)},
        data={"data_source": data_source, "metadata": metadata},
    )
    if resp.status_code == 409:  # sha-256 duplicate race: reuse the stored row
        for ev in await _case_evidence(client, case_id):
            if ev.get("original_filename") == fname:
                report.add(f"evidence {fname}", "existing", f"{ev['id']} (sha256 dedupe)")
                return ev
    if resp.status_code != 201:
        raise RuntimeError(f"upload {fname} -> {resp.status_code}: {resp.text[:300]}")
    ev = resp.json()
    report.add(f"evidence {fname}", "created", f"{ev['id']} sha256={ev['sha256'][:12]}...")
    return ev


async def ensure_ingest(client: httpx.AsyncClient, case_id: str, ev: dict, report: SeedReport):
    if ev.get("status") == "parsed" or ev.get("record_count"):
        report.add(f"ingest {ev['original_filename']}", "existing", f"status={ev['status']}")
        return
    out = await _post(
        client,
        f"/cases/{case_id}/ingest",
        expected=(200, 201, 202),
        json={"evidence_file_id": ev["id"]},
    )
    job = out.get("job", {})
    report.add(
        f"ingest {ev['original_filename']}",
        "created",
        f"status={job.get('status')} duplicate={out.get('duplicate')}",
    )


async def _jobs(client: httpx.AsyncClient, case_id: str, feature: str) -> list[dict]:
    return await _list_all(
        client, f"/cases/{case_id}/evidence-intelligence/jobs", limit=500, feature=feature
    )


async def _wait_job_id(
    client: httpx.AsyncClient, case_id: str, job_id: str, timeout_s: float, poll: float = 3.0
) -> dict | None:
    """Poll the case's job list until the given job id reaches a terminal state."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        jobs = await _list_all(client, f"/cases/{case_id}/evidence-intelligence/jobs", limit=500)
        for job in jobs:
            if job.get("id") == job_id and job.get("status") in TERMINAL:
                return job
        await asyncio.sleep(poll)
    return None


async def ensure_job(
    client: httpx.AsyncClient,
    case_id: str,
    feature: str,
    report: SeedReport,
    body: dict | None = None,
    path: str | None = None,
    timeout_s: float = 420,
    retry_failed: bool = False,
) -> tuple[dict | None, str]:
    """Submit one intelligence job unless a succeeded attempt already exists.

    failed/canceled -> reported as failed and not re-submitted; partial ->
    kept as existing; both re-submit only with ``retry_failed`` (keeps re-runs
    stable and never burns attempts when the model server is down).

    Returns ``(job, action)`` where action is one of created/existing/failed/
    pending - callers use it to decide first-run-only side effects.
    """
    jobs = await _jobs(client, case_id, feature)
    ok = [j for j in jobs if j.get("status") == "succeeded"]
    if ok:
        job = max(ok, key=lambda j: j.get("created_at") or "")
        report.add(f"job {feature}", "existing", f"status={job['status']}")
        return job, "existing"
    active = [j for j in jobs if j.get("status") in ACTIVE]
    target_id: str | None = None
    if active:
        target_id = max(active, key=lambda j: j.get("created_at") or "")["id"]
    else:
        non_ok = [j for j in jobs if j.get("status") in TERMINAL]
        if non_ok and not retry_failed:
            job = max(non_ok, key=lambda j: j.get("created_at") or "")
            if job.get("status") in ("failed", "canceled"):
                report.add(
                    f"job {feature}",
                    "failed",
                    f"previous attempt {job['status']}: {str(job.get('error') or '')[:140]} "
                    "(set CS_SEED_RETRY_FAILED=1 to retry)",
                )
                return job, "failed"
            report.add(
                f"job {feature}",
                "existing",
                "status=partial (set CS_SEED_RETRY_FAILED=1 to re-run)",
            )
            return job, "existing"
        submit_path = path or (
            f"/cases/{case_id}/evidence-intelligence/{FEATURE_SUBMIT_PATHS[feature]}"
        )
        try:
            out = await _post(client, submit_path, expected=(200, 201, 202), json=body or {})
            target_id = (out or {}).get("job", {}).get("id")
        except RuntimeError as exc:
            if "409" not in str(exc):
                raise
            active = [j for j in await _jobs(client, case_id, feature) if j.get("status") in ACTIVE]
            target_id = active[0]["id"] if active else None
    if target_id is None:
        report.add(f"job {feature}", "pending", "submission produced no job id")
        return None, "pending"
    job = await _wait_job_id(client, case_id, target_id, timeout_s)
    if job is None:
        report.add(f"job {feature}", "pending", "not terminal before timeout; check demo-status")
        return None, "pending"
    action = "created" if job.get("status") in DONE_OK else "failed"
    report.add(
        f"job {feature}",
        action,
        f"status={job['status']}"
        + (f" error={str(job.get('error'))[:140]}" if action == "failed" else ""),
    )
    return job, action


async def _artifacts(client: httpx.AsyncClient, case_id: str, kind: str) -> list[dict]:
    return await _list_all(
        client, f"/cases/{case_id}/evidence-intelligence/artifacts", limit=500, kind=kind
    )


async def ensure_custody(client: httpx.AsyncClient, case_id: str, ev: dict, report: SeedReport):
    chrono = await _get(client, f"/cases/{case_id}/evidence/{ev['id']}/custody")
    present = {(e["event_type"], _utc_instant(e["occurred_at"])) for e in chrono.get("events", [])}
    for event in CUSTODY_CHAIN:
        key = (event["event_type"], _utc_instant(event["occurred_at"]))
        if key in present:
            report.add(f"custody {event['event_type']} {ev['original_filename']}", "existing")
            continue
        body = dict(event)
        body["recorded_sha256"] = ev["sha256"]
        await _post(
            client,
            f"/cases/{case_id}/evidence/{ev['id']}/custody-events",
            expected=(200, 201),
            json=body,
        )
        report.add(
            f"custody {event['event_type']} {ev['original_filename']}",
            "created",
            event["occurred_at"],
        )


async def ensure_victim(client: httpx.AsyncClient, case_id: str, report: SeedReport):
    victims = await _list_all(client, f"/cases/{case_id}/victims", limit=200)
    if any(v.get("name") == "Ananya Deshpande" for v in victims):
        report.add("victim Ananya Deshpande (synthetic)", "existing")
        return
    await _post(
        client,
        f"/cases/{case_id}/victims",
        expected=(200, 201),
        json={
            "name": "Ananya Deshpande",
            "gender": "female",
            "classification": "individual",
            "phone": "+91 98200 00042",
            "incident_date": "2026-04-05T00:00:00+05:30",
            "incident_type": "unauthorised_bank_transfer",
            "fraud_category": "payment_diversion",
            "reported_amount": 47500.0,
            "currency": "INR",
            "description": "SYNTHETIC SIH showcase victim record - fictional complainant.",
        },
    )
    report.add("victim Ananya Deshpande (synthetic)", "created")


async def _timeline_items(client: httpx.AsyncClient, case_id: str) -> list[dict]:
    return await _list_all(client, f"/cases/{case_id}/timeline", limit=500)


async def ensure_curated_timeline(
    client: httpx.AsyncClient, case_id: str, evidence_ids: dict, report: SeedReport
) -> None:
    seen = {
        (_utc_instant(e["occurred_at"]), e.get("title"))
        for e in await _timeline_items(client, case_id)
    }
    for event in CURATED_TIMELINE:
        key = (_utc_instant(event["occurred_at"]), event["title"])
        if key in seen:
            report.add(f"timeline: {event['title']}", "existing")
            continue
        body = {k: v for k, v in event.items() if k != "evidence_file"}
        ev_id = evidence_ids.get(event["evidence_file"])
        if ev_id:
            body["evidence_file_id"] = ev_id
        await _post(client, f"/cases/{case_id}/timeline", expected=(200, 201), json=body)
        report.add(f"timeline: {event['title']}", "created", event["occurred_at"])


async def ensure_reconstruction(
    client: httpx.AsyncClient, case_id: str, report: SeedReport, timeout_s: float
) -> None:
    """Run reconstruction, approve commit-able proposals, commit them.

    Proposals whose date could not be parsed stay pending_review on purpose:
    rejecting them is a human decision the presenter can demo live.
    """
    await ensure_job(client, case_id, "timeline", report, body={}, timeout_s=timeout_s)
    proposals = await _artifacts(client, case_id, "timeline_proposal")
    approved_ids: list[str] = []
    approved_earlier = 0
    for art in proposals:
        payload = art.get("payload") or {}
        if not payload.get("occurred_at"):
            continue
        if art.get("status") == "approved":
            approved_ids.append(art["id"])
            approved_earlier += 1
        elif art.get("status") == "pending_review":
            await _post(
                client,
                f"/cases/{case_id}/evidence-intelligence/artifacts/{art['id']}/review",
                expected=(200, 201),
                json={"decision": "approved"},
            )
            approved_ids.append(art["id"])
    committed = refreshed_already = 0
    for art_id in approved_ids:
        out = await _post(
            client,
            f"/cases/{case_id}/evidence-intelligence/timeline-proposals/{art_id}/commit",
            expected=(200, 201),
            json={},
        )
        if (out or {}).get("duplicate"):
            refreshed_already += 1
        else:
            committed += 1
    unparseable = sum(1 for a in proposals if not (a.get("payload") or {}).get("occurred_at"))
    detail = (
        f"{len(proposals)} proposals, {committed} newly committed, "
        f"{refreshed_already} already committed, {approved_earlier} pre-approved"
    )
    if unparseable:
        detail += f", {unparseable} without a parseable date left pending human review"
    report.add(
        "timeline reconstruction",
        "created" if committed else "existing",
        detail,
    )


async def ensure_resolution_review(client: httpx.AsyncClient, case_id: str, report: SeedReport):
    matches = await _list_all(client, f"/cases/{case_id}/resolution/review", limit=200)
    report.add(
        "entity resolution review queue",
        "existing" if matches else "skipped",
        f"{len(matches)} candidate match(es) pending human review",
    )


async def ensure_financial_trace(client: httpx.AsyncClient, case_id: str, report: SeedReport):
    out = await _post(
        client,
        f"/cases/{case_id}/evidence-intelligence/financial-flow/trace",
        expected=(200,),
        json={
            "target": "ACCSIH001",
            "target_kind": "account",
            "edge_kind": "association",
            "max_depth": 3,
            "max_paths": 10,
        },
    )
    detail = (
        f"status={out.get('status')} matched_facts={out.get('matched_facts')} "
        f"paths={len(out.get('paths') or [])}"
    )
    if out.get("status") == "not_found":
        report.add("financial-flow trace ACCSIH001", "failed", detail)
    else:
        report.add("financial-flow trace ACCSIH001", "created", detail)


async def ensure_cross_case(
    client: httpx.AsyncClient,
    case_id: str,
    support_id: str,
    report: SeedReport,
    timeout_s: float,
    retry_failed: bool = False,
) -> None:
    candidates = await _list_all(
        client, "/cross-case/candidates", limit=500, anchor_case_id=case_id
    )
    if candidates:
        report.add("cross-case candidates", "existing", f"{len(candidates)} candidate(s)")
        return
    out = await _post(
        client,
        "/cross-case/discover",
        expected=(200, 201, 202),
        json={"anchor_case_id": case_id, "case_ids": [case_id, support_id]},
    )
    job_id = (out or {}).get("job", {}).get("id")
    if job_id:
        await _wait_job_id(client, case_id, job_id, timeout_s)
    candidates = await _list_all(
        client, "/cross-case/candidates", limit=500, anchor_case_id=case_id
    )
    report.add("cross-case candidates", "created", f"{len(candidates)} candidate(s)")


async def ensure_analytics(client: httpx.AsyncClient, case_id: str, report: SeedReport):
    # NB: analytics/summary counts graph-derived findings, not Finding rows -
    # the idempotency signal must be the findings the Findings page shows.
    findings = await _list_all(client, f"/cases/{case_id}/findings", limit=200)
    if findings:
        report.add("analytics run", "existing", f"{len(findings)} finding(s) on file")
        return
    run = await _post(client, f"/cases/{case_id}/analytics/run", expected=(200, 201), json={})
    report.add("analytics run", "created", f"run status={run.get('status')}")


async def ensure_report(client: httpx.AsyncClient, case_id: str, report: SeedReport):
    reports = await _list_all(client, f"/cases/{case_id}/reports", limit=200)
    if any(r.get("report_type") == "intelligence" for r in reports):
        report.add("intelligence report (pdf)", "existing")
        return
    out = await _post(
        client,
        f"/cases/{case_id}/reports",
        expected=(200, 201),
        json={
            "report_type": "intelligence",
            "format": "pdf",
            "title": "SIH Showcase - Intelligence Report (synthetic)",
        },
    )
    report.add("intelligence report (pdf)", "created", str(out.get("id") or out)[:80])


def render_draft(evidence_ids: dict, timeline_id: str) -> str:
    text = DRAFT_TEMPLATE.read_text()
    replacements = {
        "CASE_NUMBER": PRIMARY_CASE["case_number"],
        "EV_STATEMENT": evidence_ids["merchant_statement.csv"],
        "EV_LEDGER": evidence_ids["wallet_ledger.json"],
        "EV_URLS": evidence_ids["phishing_urls.txt"],
        "EV_TIMELINE": timeline_id,
        "EV_MISSING": DRAFT_MISSING_CITE,
    }
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


async def ensure_report_audit(
    client: httpx.AsyncClient,
    case_id: str,
    draft: str,
    report: SeedReport,
    timeout_s: float,
    retry_failed: bool = False,
) -> None:
    digest = hashlib.sha256(draft.encode("utf-8")).hexdigest()

    def _match(audits: list[dict]) -> list[dict]:
        return [a for a in audits if a.get("draft_hash") == digest]

    audits = await _list_all(client, f"/cases/{case_id}/report-audits", limit=200)
    # Attempts already terminal when we enter: a fresh submission must be told
    # apart from them (a stale `failed` must not shadow a later retry).
    done = [a for a in _match(audits) if a.get("status") in TERMINAL]
    stale_ids = {a.get("id") for a in done}
    if done:
        audit = max(done, key=lambda a: a.get("created_at") or "")
        status = audit.get("status")
        if status == "succeeded":
            report.add(
                "report audit",
                "existing",
                f"status={status} claims={audit.get('claims')}",
            )
            return
        if not retry_failed:
            if status in ("failed", "canceled"):
                report.add(
                    "report audit",
                    "failed",
                    f"previous attempt {status}: {str(audit.get('error') or '')[:140]} "
                    "(set CS_SEED_RETRY_FAILED=1 to retry)",
                )
            else:
                report.add(
                    "report audit",
                    "existing",
                    "status=partial (set CS_SEED_RETRY_FAILED=1 to re-run)",
                )
            return
    active = [a for a in _match(audits) if a.get("status") in ACTIVE]
    if not active:
        try:
            await _post(
                client,
                f"/cases/{case_id}/report-audits",
                expected=(200, 201, 202),
                json={"draft_text": draft},
            )
        except RuntimeError as exc:
            if "409" not in str(exc):
                raise
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        audits = await _list_all(client, f"/cases/{case_id}/report-audits", limit=200)
        fresh = [
            a
            for a in _match(audits)
            if a.get("status") in TERMINAL and a.get("id") not in stale_ids
        ]
        if fresh:
            audit = max(fresh, key=lambda a: a.get("created_at") or "")
            action = "created" if audit.get("status") in DONE_OK else "failed"
            report.add(
                "report audit",
                action,
                f"status={audit['status']} claims={audit.get('claims')} "
                f"summary={json.dumps(audit.get('result_summary'))[:200]}",
            )
            return
        await asyncio.sleep(3)
    report.add("report audit", "pending", "not terminal before timeout; check demo-status")


# --- orchestrators ------------------------------------------------------------


async def _soft(report: SeedReport, name: str, coro):
    """Run one step; record any failure as a step instead of aborting the seed.

    Structural steps (case + evidence creation) stay un-wrapped outside this
    helper because everything downstream needs their ids.
    """
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001 - a seed must report, not crash
        report.add(name, "failed", f"{type(exc).__name__}: {str(exc)[:300]}")
        return None


async def run_seed(
    client: httpx.AsyncClient,
    *,
    member_user_id: str | None = None,
    job_timeout: float = 420,
    retry_failed: bool = False,
) -> SeedReport:
    """Idempotently seed the full SIH showcase through the real API."""
    report = SeedReport()
    primary = await ensure_case(client, PRIMARY_CASE, report)
    support = await ensure_case(client, SUPPORT_CASE, report)
    primary_id, support_id = primary["id"], support["id"]

    evidence_ids: dict[str, str] = {}
    evidence_by_name: dict[str, dict] = {}
    for fname, data_source, content_type, _case_number in PRIMARY_FILES:
        ev = await ensure_evidence(client, primary_id, fname, data_source, content_type, report)
        await ensure_ingest(client, primary_id, ev, report)
        evidence_ids[fname] = ev["id"]
        evidence_by_name[fname] = ev
    for fname, data_source, content_type, _case_number in SUPPORT_FILES:
        ev = await ensure_evidence(client, support_id, fname, data_source, content_type, report)
        await ensure_ingest(client, support_id, ev, report)

    for fname in CUSTODY_FILES:
        await _soft(
            report,
            f"custody chain {fname}",
            ensure_custody(client, primary_id, evidence_by_name[fname], report),
        )
    await _soft(report, "victim record", ensure_victim(client, primary_id, report))
    await _soft(
        report,
        "curated timeline",
        ensure_curated_timeline(client, primary_id, evidence_ids, report),
    )

    await _soft(
        report,
        "resolution job + queue",
        ensure_job(
            client,
            primary_id,
            "entity_resolution",
            report,
            body={},
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    await _soft(report, "resolution queue", ensure_resolution_review(client, primary_id, report))
    await _soft(
        report,
        "contradiction job",
        ensure_job(
            client,
            primary_id,
            "contradiction",
            report,
            body={},
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    contradictions = (
        await _soft(
            report,
            "contradiction artifacts",
            _artifacts(client, primary_id, "contradiction"),
        )
        or []
    )
    report.add(
        "contradiction artifacts",
        "existing" if contradictions else "pending",
        f"{len(contradictions)} artifact(s) pending review",
    )
    fin_result = await _soft(
        report,
        "financial-flow job",
        ensure_job(
            client,
            primary_id,
            "financial_flow",
            report,
            body={},
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    fin_action = fin_result[1] if fin_result else "failed"
    if fin_action == "created":
        # First run: verify the extracted facts end-to-end through the real
        # trace endpoint. Re-runs skip it - the endpoint is stateless, so the
        # check belongs live in the Financial Flow view, not in a re-seed.
        await _soft(report, "financial trace", ensure_financial_trace(client, primary_id, report))
    else:
        report.add(
            "financial trace",
            "skipped",
            "stateless verification accompanies first run; open the Financial Flow view live",
        )
    await _soft(
        report,
        "custody-audit job",
        ensure_job(
            client,
            primary_id,
            "custody",
            report,
            body={},
            path=f"/cases/{primary_id}/evidence-integrity/custody-audit",
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    await _soft(
        report,
        "timeline reconstruction",
        ensure_reconstruction(client, primary_id, report, job_timeout),
    )
    await _soft(
        report,
        "multilingual job",
        ensure_job(
            client,
            primary_id,
            "multilingual",
            report,
            body={"evidence_file_id": evidence_ids["complaint_mixed.txt"], "translate": True},
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    await _soft(
        report,
        "triage job",
        ensure_job(
            client,
            primary_id,
            "triage",
            report,
            body={"evidence_file_id": evidence_ids["phishing_urls.txt"]},
            timeout_s=job_timeout,
            retry_failed=retry_failed,
        ),
    )
    await _soft(
        report,
        "cross-case discover",
        ensure_cross_case(
            client, primary_id, support_id, report, job_timeout, retry_failed=retry_failed
        ),
    )
    await _soft(report, "analytics run", ensure_analytics(client, primary_id, report))
    await _soft(report, "intelligence report", ensure_report(client, primary_id, report))

    timeline_items = await _soft(report, "timeline list", _timeline_items(client, primary_id)) or []
    timeline_id = timeline_items[0]["id"] if timeline_items else DRAFT_MISSING_CITE
    draft = render_draft(evidence_ids, timeline_id)
    await _soft(
        report,
        "report audit",
        ensure_report_audit(client, primary_id, draft, report, job_timeout, retry_failed),
    )

    if member_user_id:
        try:
            await ensure_member(client, primary_id, member_user_id, report)
        except (RuntimeError, httpx.HTTPError) as exc:
            report.add("case member (presenter account)", "failed", str(exc)[:200])
    else:
        report.add("case member (presenter account)", "skipped", "no member_user_id supplied")
    return report


async def run_status(client: httpx.AsyncClient) -> str:
    """Read-only per-capability checklist for the showcase cases."""
    lines: list[str] = []
    try:
        ai = await _get(client, "/ai/status")
        lines.append(
            f"model server: enabled={ai.get('enabled')} ready={ai.get('ready')} "
            f"last_error={str(ai.get('last_error'))[:80]}"
        )
    except httpx.HTTPError as exc:
        lines.append(f"model server: status endpoint unreachable ({exc})")
    primary = await find_case(client, PRIMARY_CASE["case_number"])
    support = await find_case(client, SUPPORT_CASE["case_number"])
    lines.append(
        "primary case SIH-2026-001: "
        + (f"PRESENT {primary['id']}" if primary else "MISSING (run demo-seed)")
    )
    lines.append(
        "support case SIH-2026-002: "
        + (f"PRESENT {support['id']}" if support else "MISSING (run demo-seed)")
    )
    if not primary:
        return "\n".join(lines)
    cid = primary["id"]

    evidence = await _case_evidence(client, cid)
    by_name = {e.get("original_filename"): e.get("status") for e in evidence}
    lines.append(
        "1. evidence ingestion: "
        + ", ".join(f"{f}={by_name.get(f, 'MISSING')}" for f, *_ in PRIMARY_FILES)
    )
    stmt = next(
        (e for e in evidence if e.get("original_filename") == "merchant_statement.csv"), None
    )
    if stmt:
        chrono = await _get(client, f"/cases/{cid}/evidence/{stmt['id']}/custody")
        lines.append(
            f"9. custody: {chrono.get('event_count')} event(s) on the statement; "
            f"integrity = recompute sha256 via POST evidence-integrity/verify"
        )
    entities = await _get(client, f"/cases/{cid}/entities", limit=1)
    matches = await _list_all(client, f"/cases/{cid}/resolution/review", limit=200)
    lines.append(
        f"2. entity resolution: {entities.get('total')} entities, "
        f"{len(matches)} match(es) pending review"
    )
    timeline = await _get(client, f"/cases/{cid}/timeline", limit=1)
    proposals = await _artifacts(client, cid, "timeline_proposal")
    pending_p = sum(1 for p in proposals if p.get("status") == "pending_review")
    lines.append(
        f"3. timeline: {timeline.get('total')} events, "
        f"{len(proposals)} proposals ({pending_p} pending review)"
    )
    contradictions = await _artifacts(client, cid, "contradiction")
    lines.append(f"4. contradictions: {len(contradictions)} artifact(s)")
    flow = await _artifacts(client, cid, "financial_finding")
    lines.append(f"5. financial flow: {len(flow)} finding artifact(s)")
    candidates = await _list_all(client, "/cross-case/candidates", limit=500, anchor_case_id=cid)
    lines.append(f"6. cross-case: {len(candidates)} candidate(s)")
    translations = await _artifacts(client, cid, "translation")
    extractions = await _artifacts(client, cid, "extraction")
    lines.append(
        f"7. multilingual: {len(extractions)} extraction artifact(s), "
        f"{len(translations)} translation(s)"
    )
    triage = await _artifacts(client, cid, "triage_observation")
    lines.append(f"8. forensics triage: {len(triage)} artifact(s)")
    audits = await _list_all(client, f"/cases/{cid}/report-audits", limit=200)
    lines.append(
        "10. report audit: "
        + (
            ", ".join(f"{a.get('status')}({a.get('claims')} claims)" for a in audits)
            if audits
            else "none (run demo-seed; the model server must be up)"
        )
    )
    findings = await _get(client, f"/cases/{cid}/findings", limit=1)
    reports = await _get(client, f"/cases/{cid}/reports", limit=1)
    lines.append(f"findings: {findings.get('total')}, reports: {reports.get('total')}")
    members = await _get(client, f"/cases/{cid}/members")
    lines.append(f"members: {len(members.get('items', []))} (presenter access)")
    return "\n".join(lines)


async def run_reset(app_env: str, confirm: str | None, out) -> int:
    """Delete ONLY the two SIH-2026-xxx showcase cases (explicit ids, guarded)."""
    if app_env == "production":
        print("REFUSED: demo reset never runs with APP_ENV=production", file=out)
        return 2
    if confirm != "sih-showcase":
        print("REFUSED: set DEMO_RESET_CONFIRM=sih-showcase to delete showcase data.", file=out)
        return 2
    from app.core.config import get_settings
    from app.db.postgres import Database
    from app.db.storage import Storage
    from sqlalchemy import bindparam, text

    settings = get_settings()
    db = Database(settings)
    factory = db.session_factory()
    graph_note = "graph: skipped"
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    text("SELECT id, case_number FROM cases WHERE case_number IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": list(SHOWCASE_CASE_NUMBERS)},
                )
            ).all()
            if not rows:
                print("nothing to reset: showcase cases not present", file=out)
                return 0
            removed = 0
            for case_uuid, case_number in rows:
                stored = (
                    (
                        await session.execute(
                            text(
                                "SELECT stored_key FROM evidence_files "
                                "WHERE case_id = :cid AND stored_key IS NOT NULL"
                            ),
                            {"cid": case_uuid},
                        )
                    )
                    .scalars()
                    .all()
                )
                ai_deleted = (
                    await session.execute(
                        text(
                            "DELETE FROM ai_messages WHERE conversation_id IN "
                            "(SELECT id FROM ai_conversations WHERE case_id = :cid)"
                        ),
                        {"cid": case_uuid},
                    )
                ).rowcount
                conv_deleted = (
                    await session.execute(
                        text("DELETE FROM ai_conversations WHERE case_id = :cid"),
                        {"cid": case_uuid},
                    )
                ).rowcount
                audit_deleted = (
                    await session.execute(
                        text("DELETE FROM audit_logs WHERE case_id = :cid"),
                        {"cid": case_uuid},
                    )
                ).rowcount
                case_deleted = (
                    await session.execute(
                        text("DELETE FROM cases WHERE id = :cid"), {"cid": case_uuid}
                    )
                ).rowcount
                await session.commit()
                removed += case_deleted
                print(
                    f"  removed {case_number} ({case_uuid}): case={case_deleted} "
                    f"audit_rows={audit_deleted} ai_messages={ai_deleted} "
                    f"conversations={conv_deleted} stored_objects={len(stored)}",
                    file=out,
                )
                if stored:
                    try:
                        Storage(settings).delete_objects(list(stored))
                    except Exception as exc:  # best-effort object cleanup
                        print(f"    note: object cleanup skipped ({exc})", file=out)
            try:
                from app.db.neo4j import GraphStore
                from app.services.graph_sync import GraphSyncService

                for case_uuid, _case_number in rows:
                    nodes, rels = await GraphSyncService(
                        GraphStore(settings), settings
                    ).delete_case(case_uuid)
                    graph_note = f"graph: last case removed nodes={nodes} rels={rels}"
            except Exception as exc:
                graph_note = f"graph cleanup skipped ({exc})"
            print(f"reset complete: {removed} case(s) removed; {graph_note}", file=out)
    finally:
        try:
            await db.engine().dispose()
        except Exception as exc:
            print(f"note: engine dispose skipped ({exc})", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIH showcase seed (see module docstring)")
    parser.add_argument("command", choices=("seed", "status", "reset"))
    args = parser.parse_args(argv)

    from app.core.config import get_settings

    settings = get_settings()
    if args.command == "reset":
        return asyncio.run(
            run_reset(settings.APP_ENV, os.environ.get("DEMO_RESET_CONFIRM"), sys.stdout)
        )
    if settings.APP_ENV == "production":
        print("REFUSED: showcase seed never runs with APP_ENV=production")
        return 2

    base = os.environ.get("CS_API_BASE") or "http://localhost:8000"
    user = os.environ.get("CS_SHOWCASE_USER") or "admin"
    password = os.environ.get("CS_SHOWCASE_PASSWORD") or "admin-dev-password"
    timeout_s = float(os.environ.get("CS_SEED_JOB_TIMEOUT") or "420")
    retry_failed = os.environ.get("CS_SEED_RETRY_FAILED", "") == "1"

    async def _run() -> int:
        token = await login(base, user, password)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(
            base_url=f"{base}/api/v1", headers=headers, timeout=120
        ) as client:
            if args.command == "status":
                print(await run_status(client))
                return 0

            # Fresh stacks have no users at all: bootstrap the documented dev
            # accounts first (idempotent) so `make demo-seed` works end-to-end.
            try:
                from app.db.postgres import Database

                from scripts.seed_users import ensure_seed_users

                db = Database(settings)
                async with db.session_factory()() as session:
                    created = await ensure_seed_users(session)
                if created:
                    print(f"seed users created: {[u.get('username') for u in created]}")
                await db.engine().dispose()
            except Exception as exc:
                print(f"note: seed users not ensured ({str(exc)[:160]}); continuing")

            member_id = None
            try:
                member_token = await login(
                    base,
                    os.environ.get("CS_SHOWCASE_MEMBER_USER", "investigator"),
                    os.environ.get("CS_SHOWCASE_MEMBER_PASSWORD", "investigator-dev-password"),
                )
                async with httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=60) as inv:
                    inv.headers["Authorization"] = f"Bearer {member_token}"
                    me_resp = await inv.get("/auth/me")
                    me_resp.raise_for_status()
                    member_id = me_resp.json()["user"]["id"]
            except Exception as exc:
                print(f"note: presenter member step skipped ({str(exc)[:160]})")

            t0 = time.time()
            report = await run_seed(
                client,
                member_user_id=member_id,
                job_timeout=timeout_s,
                retry_failed=retry_failed,
            )
            me = await _get(client, "/auth/me")
            elapsed = time.time() - t0
            print(f"SIH showcase seed ({me['user']['username']} via {base}), {elapsed:.1f}s:")
            print(report.render())
            if report.failed:
                print(f"FINISHED WITH {len(report.failed)} FAILED STEP(S)")
                return 2
            print("FINISHED OK - open the app and search for case SIH-2026-001")
            return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())

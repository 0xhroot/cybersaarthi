"""Report generation service: JSON / CSV / PDF case artifacts."""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.storage import Storage
from app.models import (
    Entity,
    EvidenceFile,
    Finding,
    Relationship,
    Report,
    TimelineEvent,
)

# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

ReportData = dict[str, Any] | list[dict[str, Any]]


async def _fetch_case_summary_data(session: AsyncSession, case_id: uuid.UUID) -> dict[str, Any]:
    entities = list(
        (await session.execute(select(Entity).where(Entity.case_id == str(case_id)))).scalars()
    )
    evidence = list(
        (
            await session.execute(select(EvidenceFile).where(EvidenceFile.case_id == str(case_id)))
        ).scalars()
    )
    findings = list(
        (await session.execute(select(Finding).where(Finding.case_id == str(case_id)))).scalars()
    )
    relationships = list(
        (
            await session.execute(select(Relationship).where(Relationship.case_id == str(case_id)))
        ).scalars()
    )
    return {
        "case_id": str(case_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "entities": [
            {"id": str(e.id), "type": e.entity_type, "value": e.display_value, "status": e.status}
            for e in entities
        ],
        "evidence_files": [
            {
                "id": str(e.id),
                "filename": e.original_filename,
                "sha256": e.sha256,
                "status": e.status,
            }
            for e in evidence
        ],
        "relationships": [
            {"id": str(r.id), "type": r.relationship_type, "confidence": r.confidence}
            for r in relationships
        ],
        "findings": [
            {"id": str(f.id), "title": f.title, "type": f.finding_type, "severity": f.severity}
            for f in findings
        ],
        "totals": {
            "entities": len(entities),
            "evidence": len(evidence),
            "relationships": len(relationships),
            "findings": len(findings),
        },
    }


async def _fetch_timeline_data(session: AsyncSession, case_id: uuid.UUID) -> list[dict[str, Any]]:
    events = list(
        (
            await session.execute(
                select(TimelineEvent)
                .where(TimelineEvent.case_id == str(case_id))
                .order_by(TimelineEvent.occurred_at)
            )
        ).scalars()
    )
    return [
        {
            "occurred_at": e.occurred_at.isoformat(),
            "kind": e.kind,
            "title": e.title,
            "description": e.description,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# Format builders
# ---------------------------------------------------------------------------


def _build_json(data: ReportData) -> bytes:
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def _build_csv(data: ReportData) -> bytes:
    raw: Any = data
    buf = io.StringIO()
    writer = csv.writer(buf)
    if "entities" in raw:
        writer.writerow(["kind", "id", "type", "value", "status"])
        for row in raw["entities"]:
            writer.writerow(["entity", row["id"], row["type"], row["value"], row["status"]])
        writer.writerow([])
        writer.writerow(["kind", "id", "filename", "sha256", "status"])
        for row in raw.get("evidence_files", []):
            writer.writerow(["evidence", row["id"], row["filename"], row["sha256"], row["status"]])
        writer.writerow([])
        writer.writerow(["kind", "id", "title", "type", "severity"])
        for row in raw.get("findings", []):
            writer.writerow(["finding", row["id"], row["title"], row["type"], row["severity"]])
    elif isinstance(raw, list) and raw and "occurred_at" in raw[0]:
        writer.writerow(["occurred_at", "kind", "title", "description"])
        for row in raw:
            writer.writerow(
                [row["occurred_at"], row["kind"], row["title"], row.get("description", "")]
            )
    else:
        writer.writerow(["key", "value"])
        for k, v in raw.items():
            writer.writerow([k, json.dumps(v, default=str)])
    return buf.getvalue().encode("utf-8")


def _build_pdf(title: str, data: ReportData) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if isinstance(data, dict):
        for section_key, rows in data.items():
            if section_key in ("case_id", "generated_at", "totals"):
                pdf.cell(0, 6, f"{section_key}: {rows}", new_x="LMARGIN", new_y="NEXT")
                continue
            if not isinstance(rows, list) or not rows:
                continue
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, section_key.replace("_", " ").title(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            for row in rows:
                line = " | ".join(f"{k}={v}" for k, v in row.items())
                pdf.multi_cell(0, 5, line)
            pdf.ln(2)
    elif isinstance(data, list):
        for row in data:
            line = " | ".join(f"{k}={v}" for k, v in row.items())
            pdf.multi_cell(0, 5, line)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_REPORT_DATA_BUILDERS: dict[str, Callable[[AsyncSession, uuid.UUID], Awaitable[ReportData]]] = {
    "case_summary": _fetch_case_summary_data,
    "timeline": _fetch_timeline_data,
    "intelligence": _fetch_case_summary_data,
    "evidence_manifest": _fetch_case_summary_data,
    "network_analysis": _fetch_case_summary_data,
}

_FORMAT_BUILDERS: dict[str, Callable[..., bytes]] = {
    "json": _build_json,
    "csv": _build_csv,
    "pdf": _build_pdf,
}


async def generate_report(
    *,
    session: AsyncSession,
    storage: Storage,
    settings: Settings,
    case_id: uuid.UUID,
    report_type: str,
    fmt: str,
    title: str,
    created_by: uuid.UUID | None,
) -> Report:
    report = Report(
        case_id=str(case_id),
        report_type=report_type,
        format=fmt,
        title=title,
        status="generating",
        created_by=str(created_by) if created_by else None,
    )
    session.add(report)
    await session.flush()
    try:
        data = await _REPORT_DATA_BUILDERS[report_type](session, case_id)
        content = (
            _FORMAT_BUILDERS[fmt](title=title, data=data)
            if fmt == "pdf"
            else _FORMAT_BUILDERS[fmt](data)
        )
        now = datetime.now(UTC)
        key = f"reports/{case_id}/{now.strftime('%Y%m%d%H%M%S')}_{report.id}.{fmt}"
        storage.client().put_object(
            Bucket=storage.bucket_name(),
            Key=key,
            Body=content,
            ContentType={"json": "application/json", "csv": "text/csv", "pdf": "application/pdf"}[
                fmt
            ],
        )
        report.minio_key = key
        report.byte_size = len(content)
        report.status = "ready"
    except Exception as exc:
        report.status = "failed"
        report.failure_reason = str(exc)[:512]
    await session.flush()
    return report


async def get_report(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> Report | None:
    return await session.get(Report, report_id)


async def list_reports(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Report], int]:
    count_q = select(func.count()).select_from(Report).where(Report.case_id == str(case_id))
    total = (await session.execute(count_q)).scalar_one()
    q = (
        select(Report)
        .where(Report.case_id == str(case_id))
        .order_by(Report.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(q)).scalars())
    return rows, total


async def get_report_bytes(
    *,
    storage: Storage,
    report: Report,
) -> bytes:
    if report.minio_key is None:
        raise ValueError("report has no stored artifact")
    obj = storage.client().get_object(
        Bucket=storage.bucket_name(),
        Key=report.minio_key,
    )
    return obj["Body"].read()

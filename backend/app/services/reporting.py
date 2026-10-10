"""Report generation service: JSON / CSV / PDF case artifacts."""

from __future__ import annotations

import csv
import io
import json
import logging
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF
from fpdf.enums import WrapMode, XPos, YPos
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

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------
#
# The previous renderer called ``pdf.multi_cell(0, h, line)`` in a loop.  fpdf2's
# ``multi_cell`` defaults to ``new_x=XPos.RIGHT``, so every row left the cursor
# at the *right* margin; the next ``multi_cell(0, ...)`` then saw zero usable
# width and raised ``FPDFException: Not enough horizontal space to render a
# single character`` (fpdf/line_break.py).  Any section with two or more rows
# therefore failed, which is why PDF reports consistently ended up ``failed``
# while JSON/CSV succeeded.  The renderer below positions every cell explicitly
# (``set_xy``), pre-measures wrapped lines with ``get_string_width``, handles
# page breaks with repeated table headings, and sanitises text to the Latin-1
# range supported by the built-in Helvetica font.

# Common typographic characters mapped onto characters the core PDF fonts can
# encode, before falling back to NFKD transliteration / replacement.
_PDF_SYMBOLS: dict[int, str] = {
    0x09: " ",  # tab
    0x00A0: " ",  # nbsp
    0x2018: "'",
    0x2019: "'",
    0x201A: "'",
    0x201B: "'",
    0x201C: '"',
    0x201D: '"',
    0x201E: '"',
    0x2013: "-",
    0x2014: "-",
    0x2212: "-",
    0x2022: "-",  # bullet
    0x2026: "...",  # ellipsis
    0x2192: "->",
    0x2190: "<-",
    0x2194: "<->",
    0x20B9: "Rs.",  # rupee
    0x00A9: "(c)",
    0x00AE: "(r)",
    0x2122: "(tm)",
}


def _pdf_text(value: Any) -> str:
    """Render arbitrary report data as print-safe Latin-1 text.

    Case titles, evidence filenames and entity values are untrusted data; the
    PDF core fonts only encode Latin-1, so anything else is transliterated
    (NFKD) and finally replaced rather than raising or dropping the record.
    """
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_PDF_SYMBOLS)
    # Neutralise remaining control characters (newline survives) so they can
    # never corrupt the PDF text stream.
    text = "".join(ch if (ch == "\n" or " " <= ch < "\x7f" or ch >= "\xa0") else " " for ch in text)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        pass
    decomposed = unicodedata.normalize("NFKD", text)
    latin = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    try:
        latin.encode("latin-1")
        return latin
    except UnicodeEncodeError:
        return latin.encode("latin-1", errors="replace").decode("latin-1")


def _wrap_lines(pdf: FPDF, text: str, width: float) -> list[str]:
    """Greedy word wrap measured with the active font.

    Long unbroken tokens (sha256 digests, URLs, filenames) are split by
    character so they can never overflow their column.  Returns at least one
    line so empty values still occupy a row.
    """
    if width <= 0:
        return [""]
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = word if not current else f"{current} {word}"
            if pdf.get_string_width(candidate) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if pdf.get_string_width(word) <= width:
                current = word
                continue
            piece = ""
            for char in word:
                if pdf.get_string_width(piece + char) <= width:
                    piece += char
                else:
                    lines.append(piece)
                    piece = char
            current = piece
        lines.append(current)
    return lines or [""]


class _ReportPdf(FPDF):
    """A4 report document with a running header and page numbering."""

    def __init__(self, *, running_title: str, running_meta: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.running_title = running_title
        self.running_meta = running_meta

    def header(self) -> None:  # noqa: D102 - fpdf hook
        if self.page_no() <= 1:
            return  # page 1 renders the full title block in the body flow
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110, 114, 122)
        self.set_y(7)
        usable = self.w - self.l_margin - self.r_margin
        self.cell(usable * 0.62, 4, self.running_title, new_x=XPos.END, new_y=YPos.TOP)
        self.cell(usable * 0.38, 4, self.running_meta, align="R")
        self.set_draw_color(200, 205, 213)
        self.set_line_width(0.15)
        self.line(self.l_margin, 13, self.w - self.r_margin, 13)
        self.set_text_color(20, 24, 30)
        self.set_y(self.t_margin)

    def footer(self) -> None:  # noqa: D102 - fpdf hook
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110, 114, 122)
        # ``{nb}}`` is replaced with the final page count at output time.
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(20, 24, 30)


def _ensure_space(pdf: FPDF, height: float) -> None:
    """Break the page when ``height`` millimetres do not fit below the cursor."""
    if pdf.get_y() + height > pdf.page_break_trigger:
        pdf.add_page()


def _column_widths(pdf: FPDF, columns: list[str], rows: list[Any], usable: float) -> list[float]:
    """Allocate page width proportionally to observed content width."""
    sample = rows[:200]
    weights: list[float] = []
    for column in columns:
        widest = 0.0
        for row in sample:
            value = row.get(column, "") if isinstance(row, dict) else ""
            widest = max(widest, min(pdf.get_string_width(_pdf_text(value)), 70.0))
        weights.append(max(widest + 4.0, 16.0))
    scale = usable / sum(weights)
    return [weight * scale for weight in weights]


def _fit_text(pdf: FPDF, text: str, width: float) -> str:
    """Single-line ellipsis fit used for table headings."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "...") > width:
        text = text[:-1]
    return text + "..."


def _draw_table_head(pdf: FPDF, columns: list[str], widths: list[float]) -> None:
    """Draw the (repeated) column heading row at the cursor."""
    x0 = pdf.l_margin
    head_h = 6.0
    y = pdf.get_y()
    pdf.set_fill_color(232, 235, 240)
    pdf.set_draw_color(196, 202, 211)
    pdf.set_line_width(0.15)
    pdf.set_text_color(28, 34, 44)
    pdf.rect(x0, y, sum(widths), head_h, style="FD")
    pdf.set_font("Helvetica", "B", 8)
    x = x0
    for column, width in zip(columns, widths, strict=True):
        label = _fit_text(pdf, _pdf_text(column.replace("_", " ")).title(), width - 2.0)
        pdf.set_xy(x + 1.0, y + 1.6)
        pdf.cell(width - 2.0, 3, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        x += width
    pdf.set_draw_color(196, 202, 211)
    x = x0
    for width in widths[:-1]:
        x += width
        pdf.line(x, y, x, y + head_h)
    pdf.set_text_color(20, 24, 30)
    pdf.set_xy(x0, y + head_h)


def _draw_table_rows(pdf: FPDF, columns: list[str], rows: list[Any], widths: list[float]) -> None:
    """Render every row with explicit cell placement and page-break headings."""
    line_h = 4.2
    pad = 0.9
    x0 = pdf.l_margin
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(20, 24, 30)
    pdf.set_draw_color(204, 209, 217)
    pdf.set_line_width(0.12)
    for row in rows:
        cells: list[list[str]] = []
        for column, width in zip(columns, widths, strict=True):
            value = row.get(column, "") if isinstance(row, dict) else row
            cells.append(_wrap_lines(pdf, _pdf_text(value), width - 2 * pad))
        row_h = max(len(lines) for lines in cells) * line_h + 2 * pad
        _ensure_space(pdf, row_h)
        y = pdf.get_y()
        pdf.rect(x0, y, sum(widths), row_h)
        x = x0
        for lines, width in zip(cells, widths, strict=True):
            pdf.set_xy(x + pad, y + pad)
            pdf.multi_cell(
                width - 2 * pad,
                line_h,
                "\n".join(lines),
                border=0,
                wrapmode=WrapMode.WORD,
                new_x=XPos.RIGHT,
                new_y=YPos.TOP,
            )
            x += width
            if x < x0 + sum(widths) - 0.01:
                pdf.line(x, y, x, y + row_h)
        pdf.set_xy(x0, y + row_h)


def _render_table(pdf: FPDF, section_key: str, rows: list[Any]) -> None:
    """Render one report section: heading, column headings, then all rows."""
    columns: list[str] = []
    for row in rows[:500]:
        if isinstance(row, dict):
            for key in row:
                if key not in columns:
                    columns.append(key)
    if not columns:
        return
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    heading = f"{section_key.replace('_', ' ').title()} ({len(rows)})"
    _ensure_space(pdf, 20.0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(20, 24, 30)
    for line in _wrap_lines(pdf, heading, usable):
        pdf.multi_cell(usable, 6, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    widths = _column_widths(pdf, columns, rows, usable)
    _ensure_space(pdf, 7.0)
    _draw_table_head(pdf, columns, widths)
    pdf.set_font("Helvetica", "", 8)
    _draw_table_rows(pdf, columns, rows, widths)
    pdf.ln(3)


def _build_pdf(
    title: str,
    data: ReportData,
    *,
    case_id: str | None = None,
    report_type: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """Render a complete, multi-page case report as PDF bytes."""
    pdf = _ReportPdf(running_title=_pdf_text(title), running_meta=f"Case {case_id or '-'}")
    pdf.alias_nb_pages()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    # Title block (page 1)
    pdf.set_text_color(20, 24, 30)
    pdf.set_font("Helvetica", "B", 16)
    for line in _wrap_lines(pdf, _pdf_text(title), usable):
        pdf.multi_cell(usable, 8, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(86, 92, 102)
    meta: list[tuple[str, str]] = []
    if report_type:
        meta.append(("Report type", report_type.replace("_", " ")))
    if case_id:
        meta.append(("Case ID", case_id))
    if generated_at is not None:
        meta.append(("Generated", generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")))
    if isinstance(data, dict) and isinstance(data.get("totals"), dict):
        totals = data["totals"]
        meta.append(("Totals", ", ".join(f"{k}: {v}" for k, v in totals.items())))
    for label, value in meta:
        for line in _wrap_lines(pdf, f"{label}: {value}", usable):
            pdf.multi_cell(usable, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    y = pdf.get_y()
    pdf.set_draw_color(190, 195, 203)
    pdf.set_line_width(0.25)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(5)
    pdf.set_text_color(20, 24, 30)

    if isinstance(data, dict):
        for section_key, rows in data.items():
            if section_key in ("case_id", "generated_at", "totals"):
                continue  # already rendered in the title block
            if not isinstance(rows, list):
                pdf.set_font("Helvetica", "", 9)
                for line in _wrap_lines(pdf, f"{section_key}: {rows}", usable):
                    pdf.multi_cell(usable, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                continue
            if not rows:
                pdf.set_font("Helvetica", "B", 11)
                pdf.multi_cell(
                    usable,
                    6,
                    section_key.replace("_", " ").title(),
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(86, 92, 102)
                pdf.multi_cell(usable, 5, "No records.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(20, 24, 30)
                pdf.ln(3)
                continue
            _render_table(pdf, section_key, rows)
    elif isinstance(data, list):
        heading = "Timeline events" if report_type == "timeline" else "Records"
        if not data:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(86, 92, 102)
            pdf.multi_cell(usable, 5, "No records.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(20, 24, 30)
        else:
            _render_table(pdf, heading, data)

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
}


def _failure_reason(exc: Exception, correlation_id: str | None) -> str:
    """Concise, non-sensitive failure category for the API.

    Stack traces and raw error strings stay in the server log; the stored value
    carries only the exception class and the request correlation id.
    """
    summary = f"generation_failed:{type(exc).__name__}"
    if correlation_id:
        summary = f"{summary} (request_id={correlation_id})"
    return summary[:512]


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
    correlation_id: str | None = None,
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
        now = datetime.now(UTC)
        if fmt == "pdf":
            content = _build_pdf(
                title,
                data,
                case_id=str(case_id),
                report_type=report_type,
                generated_at=now,
            )
        else:
            content = _FORMAT_BUILDERS[fmt](data)
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
        logger.exception(
            "report generation failed",
            extra={
                "report_id": str(report.id),
                "case_id": str(case_id),
                "report_type": report_type,
                "format": fmt,
                "correlation_id": correlation_id,
            },
        )
        report.status = "failed"
        report.failure_reason = _failure_reason(exc, correlation_id)
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

"""PDF report rendering: regression coverage for the report-renderer cursor bug.

The original renderer looped ``pdf.multi_cell(0, h, line)``.  fpdf2's
``multi_cell`` defaults to ``new_x=XPos.RIGHT``, so each row left the cursor at
the right margin and the *second* row of any section raised::

    FPDFException: Not enough horizontal space to render a single character

Every PDF built from a section with two or more rows therefore ended up stored
as ``failed`` while JSON/CSV succeeded.  ``test_pdf_multi_row_sections_render``
is the regression test: it fails against the old implementation and passes
against the renderer in ``app.services.reporting``.

These tests are pure (no infrastructure): they exercise ``_build_pdf`` with the
same data shapes the data fetchers produce, then parse the result with pypdf.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

import pytest
from app.models import REPORT_TYPES
from app.services.reporting import _build_csv, _build_json, _build_pdf
from pypdf import PdfReader

CASE_ID = str(uuid.uuid4())
GENERATED = datetime(2026, 10, 10, 9, 30, 0, tzinfo=UTC)
TITLE = "Case Summary - DEMO-2026-001"


def _summary_data(
    *,
    entities: int = 4,
    evidence: int = 3,
    relationships: int = 3,
    findings: int = 2,
) -> dict:
    """Mirror the shape produced by ``_fetch_case_summary_data``."""
    return {
        "case_id": CASE_ID,
        "generated_at": GENERATED.isoformat(),
        "entities": [
            {
                "id": f"entity-{i:03d}",
                "type": "person" if i % 2 else "phone",
                "value": f"Subject {i} +91-98765{i:05d}",
                "status": "active",
            }
            for i in range(entities)
        ],
        "evidence_files": [
            {
                "id": f"evidence-{i:03d}",
                "filename": f"evidence-file-{i}.txt",
                "sha256": f"{i:02x}" * 32,
                "status": "verified",
            }
            for i in range(evidence)
        ],
        "relationships": [
            {"id": f"rel-{i:03d}", "type": "knows", "confidence": 0.91 - i * 0.05}
            for i in range(relationships)
        ],
        "findings": [
            {"id": f"finding-{i:03d}", "title": f"Finding {i}", "type": "fraud", "severity": "high"}
            for i in range(findings)
        ],
        "totals": {
            "entities": entities,
            "evidence": evidence,
            "relationships": relationships,
            "findings": findings,
        },
    }


def _timeline_data(events: int = 5) -> list[dict]:
    """Mirror the shape produced by ``_fetch_timeline_data``."""
    return [
        {
            "occurred_at": GENERATED.isoformat(),
            "kind": "collection_created",
            "title": f"Event {i}",
            "description": f"Timeline event number {i} with detail",
        }
        for i in range(events)
    ]


def _render(data, *, report_type: str = "case_summary", title: str = TITLE) -> tuple[bytes, str]:
    raw = _build_pdf(
        title,
        data,
        case_id=CASE_ID,
        report_type=report_type,
        generated_at=GENERATED,
    )
    assert raw.startswith(b"%PDF-"), "renderer must emit a PDF header"
    reader = PdfReader(io.BytesIO(raw))
    assert not reader.is_encrypted
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return raw, text


# ---------------------------------------------------------------------------
# Regression: multi-row sections (the bug that failed in production)
# ---------------------------------------------------------------------------


def test_pdf_multi_row_sections_render() -> None:
    """REGRESSION: the second row of any section used to raise.

    Pre-fix error (fpdf2 2.8.8)::

        FPDFException: Not enough horizontal space to render a single character
    """
    data = _summary_data()
    raw, text = _render(data)
    assert len(raw) > 1_000
    # every entity row survives into the document (no silent record dropping)
    for i in range(4):
        assert f"Subject {i}" in text.replace("\n", " ")
    assert "evidence-file-2.txt" in text.replace("\n", " ")
    assert "Finding 1" in text.replace("\n", " ")


def test_pdf_repeated_multi_row_timeline_renders() -> None:
    raw, text = _render(_timeline_data(8), report_type="timeline")
    assert len(raw) > 1_000
    for i in range(8):
        assert f"Event {i}" in text.replace("\n", " ")


# ---------------------------------------------------------------------------
# Every advertised report type in every supported format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_pdf_every_report_type_renders(report_type: str) -> None:
    data = _timeline_data(4) if report_type == "timeline" else _summary_data()
    raw, text = _render(data, report_type=report_type)
    # cover block: title, case identifier, timestamp
    assert TITLE.split(" - ")[0] in text.replace("\n", " ") or "Case Summary" in text
    assert CASE_ID in text.replace("\n", " ")
    assert "2026-10-10" in text
    assert report_type.replace("_", " ").lower() in text.lower()
    assert "{nb}" not in text


def test_json_builder_output_is_stable() -> None:
    """JSON output must stay byte-identical to the previous behaviour."""
    data = _summary_data(entities=2, evidence=1, relationships=1, findings=1)
    import json

    assert _build_json(data) == json.dumps(data, indent=2, default=str).encode("utf-8")


def test_csv_builder_output_is_stable() -> None:
    """CSV output must keep its header rows and section ordering."""
    data = _summary_data(entities=2, evidence=1, relationships=1, findings=1)
    text = _build_csv(data).decode("utf-8")
    lines = text.splitlines()
    assert lines[0] == "kind,id,type,value,status"
    assert lines[1].startswith("entity,entity-000")
    assert "kind,id,filename,sha256,status" in lines
    assert "kind,id,title,type,severity" in lines
    csv_rows = _timeline_data(2)
    timeline = _build_csv(csv_rows).decode("utf-8")
    assert timeline.splitlines()[0] == "occurred_at,kind,title,description"


# ---------------------------------------------------------------------------
# Empty datasets, unicode, multipage, long values
# ---------------------------------------------------------------------------


def test_pdf_empty_case_renders_placeholder_sections() -> None:
    data = {
        "case_id": CASE_ID,
        "generated_at": GENERATED.isoformat(),
        "entities": [],
        "evidence_files": [],
        "relationships": [],
        "findings": [],
        "totals": {"entities": 0, "evidence": 0, "relationships": 0, "findings": 0},
    }
    raw, text = _render(data)
    reader = PdfReader(io.BytesIO(raw))
    assert len(reader.pages) >= 1
    assert text.replace("\n", " ").count("No records.") >= 4


def test_pdf_empty_timeline_renders() -> None:
    raw, text = _render([], report_type="timeline")
    assert raw.startswith(b"%PDF-")
    assert "No records." in text


def test_pdf_unicode_and_special_characters_render() -> None:
    """Untrusted text outside the Latin-1 range must transliterate, not crash."""
    data = _summary_data(entities=3)
    data["entities"][0]["value"] = (
        "Fatima \u2019Shaikh \u2014 \u201cQueen\u201d \u20b91,000,000 \u2026"
    )
    data["entities"][1]["value"] = "\u65e5\u672c\u8a9e\u306e\u8a3c\u62e0 \ud83d\ude42"
    data["entities"][2]["value"] = "na\u00efve caf\u00e9 \u2192 verified"
    raw, text = _render(data)
    assert len(raw) > 1_000
    # safe substitutions survive into the document
    cleaned = text.replace("\n", " ")
    assert "Fatima 'Shaikh" in cleaned
    assert "Rs.1,000,000 ..." in cleaned
    assert "-> verified" in cleaned
    assert "naïve café" in cleaned
    # no raw control bytes or unresolved alias
    assert "\x00" not in text
    assert "{nb}" not in text


def test_pdf_text_sanitizer_strips_control_characters() -> None:
    from app.services.reporting import _pdf_text

    assert _pdf_text("a\x00b\x1bc\td") == "a b c d"
    assert _pdf_text(None) == ""
    assert _pdf_text("line1\r\nline2") == "line1\nline2"
    # CJK falls back to a visible placeholder instead of raising
    assert _pdf_text("\u65e5\u672c") == "??"


def test_pdf_multi_page_layout_repeats_headings_and_numbers_pages() -> None:
    data = _summary_data(entities=140, evidence=60, relationships=80, findings=40)
    raw, text = _render(data)
    reader = PdfReader(io.BytesIO(raw))
    page_count = len(reader.pages)
    assert page_count >= 3, "large case must span multiple pages"
    page_texts = [page.extract_text() or "" for page in reader.pages]
    # table heading row is repeated after page breaks
    heading_pages = sum(1 for t in page_texts if "Filename" in t or "Confidence" in t)
    assert heading_pages >= 2, "column headings must repeat on continuation pages"
    # page numbering
    assert "Page 1 of" in page_texts[0]
    assert f"Page {page_count} of {page_count}" in page_texts[-1].replace("\n", " ")


def test_pdf_long_unbroken_values_and_title_do_not_crash() -> None:
    data = _summary_data(entities=5)
    data["entities"][0]["value"] = "https://example.org/" + "seg/" * 80
    data["entities"][1]["value"] = "z" * 500
    long_title = "Quarterly intelligence digest \u2014 " + "very long title " * 30
    raw, text = _render(data, title=long_title)
    assert raw.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(raw))
    assert len(reader.pages) >= 1
    assert "seg/seg/seg" in text.replace("\n", "").replace(" ", "")


def test_pdf_treats_report_content_as_data_not_markup() -> None:
    """HTML/script payload in case text must render literally, never execute."""
    data = _summary_data(entities=1)
    data["entities"][0]["value"] = '<script>alert("xss")</script>'
    raw, text = _render(data)
    assert raw.startswith(b"%PDF-")
    cleaned = text.replace("\n", " ")
    assert "<script>" in cleaned  # visible as literal text
    assert 'alert("xss")' in cleaned

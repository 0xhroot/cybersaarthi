"""Phase 2: PDF evidence pipeline (format detection + pypdf page parsing).

Covers the honest failure modes the ingestion copilot depends on: corrupt
bytes, encrypted documents, page caps, truncation markers and the
no-text-layer (OCR-required) path - none of which may ever yield invented
content. Fixtures are synthetic PDFs built with fpdf2/pypdf at test time.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from app.core.enums import EvidenceFormat
from app.services.parsing import OCRRequiredError, ParseError, parse
from app.services.validation import UploadValidationError, detect_format, sniff_format
from fpdf import FPDF
from pypdf import PdfReader, PdfWriter


def _pdf_with_text(pages: list[str]) -> bytes:
    doc = FPDF()
    for text in pages:
        doc.add_page()
        if text:
            doc.set_font("helvetica", size=12)
            doc.multi_cell(0, 8, text)
    return bytes(doc.output())


def test_detect_format_pdf_by_extension_and_by_magic() -> None:
    assert detect_format("statement.pdf", b"anything") is EvidenceFormat.PDF
    assert detect_format("no-extension", b"%PDF-1.7\n%abc") is EvidenceFormat.PDF
    assert detect_format("weird.bin", b"%PDF-1.4\ntrailer") is EvidenceFormat.PDF
    assert sniff_format(b"%PDF-1.4\nanything") is EvidenceFormat.PDF
    # Non-PDF text still sniffs as before.
    assert sniff_format(b"key,value\n1,2\n") is EvidenceFormat.CSV


def test_unrecognised_format_message_mentions_pdf_support() -> None:
    with pytest.raises(UploadValidationError, match="PDF"):
        sniff_format(b"\x00\x01binary\x02\x03")


def test_pdf_parse_yields_one_record_per_page_with_page_numbers() -> None:
    data = _pdf_with_text(["Invoice for Asha Verma", "Payment on 2026-01-15"])
    records = parse(data, EvidenceFormat.PDF)
    assert [r["page"] for r in records] == [1, 2]
    assert "Asha Verma" in records[0]["text"]
    assert "2026-01-15" in records[1]["text"]
    assert all(isinstance(r["text"], str) for r in records)


def test_pdf_empty_pages_keep_full_page_mapping() -> None:
    data = _pdf_with_text(["only first page has words", ""])
    records = parse(data, EvidenceFormat.PDF)
    assert len(records) == 2
    assert records[0]["text"].strip()
    assert records[1]["text"] == ""  # page present, content empty: skip later


def test_pdf_without_text_layer_requires_ocr_and_says_so() -> None:
    data = _pdf_with_text([""])  # image-only equivalent: nothing extractable
    with pytest.raises(OCRRequiredError) as exc:
        parse(data, EvidenceFormat.PDF)
    message = str(exc.value)
    assert "OCR is required" in message
    assert "no OCR engine" in message


def test_corrupt_pdf_is_a_parse_error_not_empty_content() -> None:
    with pytest.raises(ParseError, match="malformed or corrupt"):
        parse(b"%PDF-1.4\nthis is not really a pdf", EvidenceFormat.PDF)


def test_blank_bytes_reported_as_empty_pdf() -> None:
    with pytest.raises(ParseError, match="PDF file is empty"):
        parse(b"   \n", EvidenceFormat.PDF)


def test_password_protected_pdf_refuses_to_guess() -> None:
    plain = PdfReader(BytesIO(_pdf_with_text(["classified report body"])))
    writer = PdfWriter()
    for page in plain.pages:
        writer.add_page(page)
    writer.encrypt("case-sensitive-password")
    buf = BytesIO()
    writer.write(buf)
    with pytest.raises(ParseError, match="password-protected"):
        parse(buf.getvalue(), EvidenceFormat.PDF)


def test_page_cap_is_enforced_with_actual_page_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.parsing.get_settings",
        lambda: SimpleNamespace(EVIDENCE_PDF_MAX_PAGES=1, EVIDENCE_PDF_PAGE_MAX_CHARS=10_000),
    )
    data = _pdf_with_text(["page one", "page two"])
    with pytest.raises(ParseError, match="2 pages; the configured limit is 1"):
        parse(data, EvidenceFormat.PDF)


def test_per_page_character_cap_marks_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.parsing.get_settings",
        lambda: SimpleNamespace(EVIDENCE_PDF_MAX_PAGES=50, EVIDENCE_PDF_PAGE_MAX_CHARS=8),
    )
    data = _pdf_with_text(["a very long line of evidence words"])
    records = parse(data, EvidenceFormat.PDF)
    assert len(records[0]["text"]) <= 8
    assert records[0]["text_truncated"] is True

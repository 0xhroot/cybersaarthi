"""Parsing raw evidence bytes into an ordered list of source records.

CSV is read with the standard library (header-driven records), JSON accepts an
object or array, TXT is split into non-empty paragraphs, and PDF produces one
page record per page (``{"page": n, "text": ...}``) via ``pypdf`` so every
later derivation can cite an exact source page. Each record is a plain ``dict``
so it can be stored untouched as ``SourceRecord.raw_data``.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.core.config import get_settings
from app.core.enums import EvidenceFormat


class ParseError(ValueError):
    """Raised when evidence bytes cannot be turned into records."""


class OCRRequiredError(ParseError):
    """A PDF with no text layer: content exists only as images.

    Raised instead of returning empty records so callers can distinguish
    "OCR is required but unavailable" from every other parse failure and
    report it explicitly (never as extracted content).
    """


def parse(data: bytes, format: EvidenceFormat, encoding: str = "utf-8") -> list[dict[str, Any]]:
    if format == EvidenceFormat.CSV:
        return _parse_csv(data, encoding)
    if format == EvidenceFormat.JSON:
        return _parse_json(data, encoding)
    if format == EvidenceFormat.TXT:
        return _parse_txt(data, encoding)
    if format == EvidenceFormat.PDF:
        return _parse_pdf(data)
    raise ParseError(f"unsupported evidence format: {format!r}")


def _decode(data: bytes, encoding: str) -> str:
    try:
        return data.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise ParseError(f"could not decode evidence as {encoding!r}: {exc}") from exc


def _parse_csv(data: bytes, encoding: str) -> list[dict[str, Any]]:
    text = _decode(data, encoding)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not reader.fieldnames:
        raise ParseError("CSV has no header row")

    records: list[dict[str, Any]] = []
    for row in reader:
        cleaned = {key: (value if value is not None else "") for key, value in row.items()}
        if any(str(value).strip() for value in cleaned.values()):
            records.append(cleaned)
    if not records:
        raise ParseError("CSV contains no data rows")
    return records


def _parse_json(data: bytes, encoding: str) -> list[dict[str, Any]]:
    text = _decode(data, encoding)
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc

    records: list[dict[str, Any]] = []
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            records = [item for item in payload if isinstance(item, dict)]
        else:
            records = [{"value": item} for item in payload if item is not None]
    elif isinstance(payload, dict):
        rows = None
        for key in ("records", "rows", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
        if rows is None:
            records = [payload]
        elif all(isinstance(item, dict) for item in rows):
            records = [item for item in rows if isinstance(item, dict)]
        else:
            records = [{"value": item} for item in rows if item is not None]

    if not records:
        raise ParseError("JSON contains no records")
    return records


def _parse_txt(data: bytes, encoding: str) -> list[dict[str, Any]]:
    text = _decode(data, encoding)
    paragraphs = [p for p in (block.strip() for block in text.split("\n\n")) if p]
    if not paragraphs:
        raise ParseError("TXT contains no non-empty paragraphs")
    return [{"text": p} for p in paragraphs]


def _parse_pdf(data: bytes) -> list[dict[str, Any]]:
    """One record per page, preserving page numbers for source locators.

    Honest failure modes (never invented content):
    - corrupt/undecodable bytes -> ``ParseError``
    - encrypted (owner-locked) PDF -> ``ParseError`` asking for decryption
    - page cap exceeded -> ``ParseError`` with the actual page count
    - **no text layer at all** (scanned document) -> ``ParseError`` stating
      OCR is required but unavailable in this deployment
    Pages with an empty text layer inside an otherwise-textual PDF are kept as
    records with ``"text": ""`` so page mapping stays complete and downstream
    extraction can skip them explicitly.
    """
    if not data.strip():
        raise ParseError("PDF file is empty")

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise ParseError("pypdf is not installed; PDF parsing is unavailable") from exc

    settings = get_settings()
    max_pages = settings.EVIDENCE_PDF_MAX_PAGES
    max_chars = settings.EVIDENCE_PDF_PAGE_MAX_CHARS

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Owner-only "protection" unlocks with an empty user password;
            # anything else is a genuinely locked document we refuse to guess at.
            if not reader.decrypt(""):
                raise ParseError(
                    "PDF is password-protected; the document must be decrypted "
                    "before ingestion (no password guessing is attempted)"
                )
        page_count = len(reader.pages)
    except ParseError:
        raise
    except Exception as exc:  # pypdf raises a wide, unstable error surface
        raise ParseError(f"malformed or corrupt PDF: {exc}") from exc

    if page_count == 0:
        raise ParseError("PDF contains no pages")
    if page_count > max_pages:
        raise ParseError(f"PDF has {page_count} pages; the configured limit is {max_pages}")

    records: list[dict[str, Any]] = []
    for page_no in range(1, page_count + 1):
        try:
            raw_text = reader.pages[page_no - 1].extract_text() or ""
        except Exception:  # one broken page must not discard the whole file
            raw_text = ""
        text = raw_text.strip()
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        record: dict[str, Any] = {"page": page_no, "text": text}
        if truncated:
            record["text_truncated"] = True
        records.append(record)

    if not any(record["text"] for record in records):
        raise OCRRequiredError(
            "PDF has no extractable text layer (likely a scanned or image-only "
            "document); OCR is required to read it, but no OCR engine is "
            "configured in this deployment"
        )
    return records

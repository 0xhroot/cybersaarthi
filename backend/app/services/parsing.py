"""Parsing raw evidence bytes into an ordered list of source records.

CSV is read with the standard library (header-driven records), JSON accepts an
object or array, and TXT is split into non-empty paragraphs. Each record is a
plain ``dict`` so it can be stored untouched as ``SourceRecord.raw_data``.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.core.enums import EvidenceFormat


class ParseError(ValueError):
    """Raised when evidence bytes cannot be turned into records."""


def parse(data: bytes, format: EvidenceFormat, encoding: str = "utf-8") -> list[dict[str, Any]]:
    if format == EvidenceFormat.CSV:
        return _parse_csv(data, encoding)
    if format == EvidenceFormat.JSON:
        return _parse_json(data, encoding)
    if format == EvidenceFormat.TXT:
        return _parse_txt(data, encoding)
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

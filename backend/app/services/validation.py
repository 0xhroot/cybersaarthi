"""Upload validation: size caps, SHA-256 fingerprinting, encoding + format detection.

Format detection is extension-first with a content sniff fallback. Encoding is
detected with ``charset-normalizer`` and defaults to UTF-8. A file that fails
these checks is rejected before it ever reaches object storage.
"""

from __future__ import annotations

import hashlib
import json
import re

from charset_normalizer import from_bytes
from fastapi import UploadFile

from app.core.enums import EvidenceFormat

CHUNK_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    """Raised when an uploaded evidence file fails validation."""


async def read_upload_with_cap(upload: UploadFile, max_bytes: int) -> bytes:
    """Stream the upload, aborting early if it exceeds ``max_bytes``."""
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(
                f"file exceeds the maximum allowed size of {max_bytes} bytes"
            )
        digest.update(chunk)
        chunks.append(chunk)
    return b"".join(chunks)


def _detect_format_from_name(filename: str) -> EvidenceFormat | None:
    match = re.search(r"\.([A-Za-z0-9]+)$", filename.lower())
    if match is None:
        return None
    extension = match.group(1)
    if extension in {"csv", "tsv"}:
        return EvidenceFormat.CSV
    if extension in {"json", "jsonl"}:
        return EvidenceFormat.JSON
    if extension == "txt":
        return EvidenceFormat.TXT
    return None


def sniff_format(data: bytes) -> EvidenceFormat:
    """Content-based fallback format detection."""

    sample = data[:4096].decode("utf-8", errors="replace").lstrip()
    if not sample:
        raise UploadValidationError("file appears to be empty")

    if sample.startswith("[") or sample.startswith("{"):
        try:
            json.loads(sample)
            return EvidenceFormat.JSON
        except ValueError:
            pass

    rows = [row for row in sample.splitlines() if row.strip()]
    if len(rows) >= 2:
        first = rows[0].split(",")
        if len(first) >= 2 and len(rows[1].split(",")) == len(first):
            return EvidenceFormat.CSV

    raise UploadValidationError(
        "unrecognised evidence format; supported formats are CSV, JSON and TXT"
    )


def detect_format(filename: str, data: bytes) -> EvidenceFormat:
    return _detect_format_from_name(filename) or sniff_format(data)


def detect_encoding(data: bytes) -> str:
    best = from_bytes(data).best()
    if best is None or not best.encoding:
        return "utf-8"
    return best.encoding.lower()


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

"""Unit tests for upload validation: format sniffing, encoding, hashing, caps."""

from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from app.core.enums import EvidenceFormat
from app.services.validation import (
    UploadValidationError,
    detect_encoding,
    detect_format,
    fingerprint,
    read_upload_with_cap,
    sniff_format,
)
from fastapi import UploadFile


def test_detect_format_from_extension() -> None:
    assert detect_format("evidence.csv", b"[1]") == EvidenceFormat.CSV
    assert detect_format("data.json", b"{") == EvidenceFormat.JSON
    assert detect_format("notes.txt", b"hi") == EvidenceFormat.TXT
    assert detect_format("export.tsv", b"a\tb\n1\t2\n") == EvidenceFormat.CSV


def test_detect_format_sniffs_content_without_extension() -> None:
    assert detect_format("unknown.bin", b'[{"name": "x"}]') == EvidenceFormat.JSON
    assert detect_format("unknown.bin", b"name,city\nA,Mumbai\n") == EvidenceFormat.CSV


def test_sniff_format_recognises_single_json_object() -> None:
    assert sniff_format(b'{"name": "A"}') == EvidenceFormat.JSON


def test_sniff_format_rejects_empty() -> None:
    with pytest.raises(UploadValidationError):
        sniff_format(b"")


def test_sniff_format_rejects_garbage() -> None:
    with pytest.raises(UploadValidationError):
        sniff_format(b"\x00\x01 corrupt")


def test_sniff_format_rejects_single_line_text() -> None:
    with pytest.raises(UploadValidationError):
        sniff_format(b"just some words")


def test_detect_encoding_utf8() -> None:
    encoding = detect_encoding("héllo".encode())
    assert "utf" in encoding


def test_fingerprint_is_sha256() -> None:
    expected = hashlib.sha256(b"hello").hexdigest()
    assert fingerprint(b"hello") == expected


async def test_read_upload_with_cap_accepts_within_limit() -> None:
    upload = UploadFile(file=BytesIO(b"x" * 10))
    assert await read_upload_with_cap(upload, max_bytes=100) == b"x" * 10


async def test_read_upload_with_cap_rejects_oversized() -> None:
    upload = UploadFile(file=BytesIO(b"x" * 10))
    upload.file.seek(0)
    with pytest.raises(UploadValidationError):
        await read_upload_with_cap(upload, max_bytes=5)

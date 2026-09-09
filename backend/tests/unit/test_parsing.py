"""Unit tests for CSV / JSON / TXT evidence parsing."""

from __future__ import annotations

import json

import pytest
from app.core.enums import EvidenceFormat
from app.services.parsing import ParseError, parse


def test_parse_csv_is_header_driven() -> None:
    data = b"name,phone,city\nRajesh Kumar,9876543210,Mumbai\n"
    records = parse(data, EvidenceFormat.CSV)
    assert records == [{"name": "Rajesh Kumar", "phone": "9876543210", "city": "Mumbai"}]


def test_parse_csv_skips_blank_rows() -> None:
    data = b"name,phone\nA,1\n,\nB,2\n"
    records = parse(data, EvidenceFormat.CSV)
    assert records == [{"name": "A", "phone": "1"}, {"name": "B", "phone": "2"}]


def test_parse_csv_empty_raises() -> None:
    with pytest.raises(ParseError):
        parse(b"", EvidenceFormat.CSV)


def test_parse_csv_no_data_rows_raises() -> None:
    with pytest.raises(ParseError):
        parse(b"name,phone\n", EvidenceFormat.CSV)


def test_parse_json_array_of_objects() -> None:
    data = json.dumps([{"name": "A"}, {"name": "B"}]).encode()
    records = parse(data, EvidenceFormat.JSON)
    assert records == [{"name": "A"}, {"name": "B"}]


def test_parse_json_object_with_records_key() -> None:
    data = json.dumps({"records": [{"name": "A"}, {"name": "B"}]}).encode()
    records = parse(data, EvidenceFormat.JSON)
    assert records == [{"name": "A"}, {"name": "B"}]


def test_parse_json_scalar_list_wraps_values() -> None:
    data = json.dumps(["MH12AB1234", "9876543210"]).encode()
    records = parse(data, EvidenceFormat.JSON)
    assert records == [{"value": "MH12AB1234"}, {"value": "9876543210"}]


def test_parse_json_plain_object_is_single_record() -> None:
    data = json.dumps({"name": "A", "phone": "9876543210"}).encode()
    records = parse(data, EvidenceFormat.JSON)
    assert records == [{"name": "A", "phone": "9876543210"}]


def test_parse_json_invalid_raises() -> None:
    with pytest.raises(ParseError):
        parse(b"{not json", EvidenceFormat.JSON)


def test_parse_json_empty_array_raises() -> None:
    with pytest.raises(ParseError):
        parse(b"[]", EvidenceFormat.JSON)


def test_parse_txt_paragraphs() -> None:
    data = b"First paragraph here.\n\nSecond paragraph there."
    records = parse(data, EvidenceFormat.TXT)
    assert records == [{"text": "First paragraph here."}, {"text": "Second paragraph there."}]


def test_parse_txt_single_block() -> None:
    records = parse(b"One block", EvidenceFormat.TXT)
    assert records == [{"text": "One block"}]


def test_parse_txt_empty_raises() -> None:
    with pytest.raises(ParseError):
        parse(b"\n\n  \n\n", EvidenceFormat.TXT)

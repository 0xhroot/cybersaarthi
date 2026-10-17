"""Phase 2: deterministic hash-comparison states (feature 9).

Every way a verification can fail to conclude is a distinct status with
explicit None semantics - never a silent pass. ``md5`` stays unsupported: the
deployment only computes sha256 and must say so rather than guess.
"""

from __future__ import annotations

from app.services.integrity import (
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISSING_EXPECTED,
    STATUS_MISSING_SOURCE,
    STATUS_UNSUPPORTED_ALGORITHM,
    compare_hashes,
    normalize_algorithm,
)

SHA = "a" * 64


def test_match_is_exact_hex_equality_case_insensitive() -> None:
    result = compare_hashes("sha256", SHA.upper(), SHA)
    assert result.status == STATUS_MATCH
    assert result.expected == SHA
    assert result.calculated == SHA
    assert result.algorithm == "sha256"


def test_mismatch_reports_both_digests() -> None:
    other = "b" * 64
    result = compare_hashes("sha256", SHA, other)
    assert result.status == STATUS_MISMATCH
    assert result.expected == SHA
    assert result.calculated == other


def test_missing_expected_hash_is_not_a_mismatch() -> None:
    for absent in (None, "", "   "):
        result = compare_hashes("sha256", absent, SHA)
        assert result.status == STATUS_MISSING_EXPECTED
        assert result.expected is None
        assert result.calculated == SHA


def test_missing_source_bytes_never_imply_a_match() -> None:
    result = compare_hashes("sha256", SHA, None)
    assert result.status == STATUS_MISSING_SOURCE
    assert result.calculated is None
    assert result.expected == SHA


def test_unsupported_algorithm_is_explicit_even_when_everything_else_is_known() -> None:
    # Precedence: unknown algorithm short-circuits - we never "compare anyway".
    result = compare_hashes("md5", "0" * 32, "1" * 32)
    assert result.status == STATUS_UNSUPPORTED_ALGORITHM
    assert result.algorithm == "md5"


def test_algorithm_aliases_normalize_to_sha256() -> None:
    assert normalize_algorithm("SHA-256") == "sha256"
    assert normalize_algorithm("sha_256") == "sha256"
    assert normalize_algorithm(" sha256 ") == "sha256"
    assert normalize_algorithm("sha1") is None
    assert compare_hashes("SHA-256", SHA, SHA).status == STATUS_MATCH


def test_whitespace_padded_digests_still_match() -> None:
    result = compare_hashes("sha256", f"  {SHA}\n", f"\t{SHA}")
    assert result.status == STATUS_MATCH

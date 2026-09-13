"""Regression: device fingerprints must be canonical across languages.

The Android app publishes ``sha256(der_subject_public_key_info)``; the
backend must hash the exact same bytes, NOT the PEM string (the historical
bug: same key, two digests -> enroll/verify cross-check always failed).

Locks the canonical form with a fixed key + expected digest so a change to
either side (e.g. hashing the PEM, or re-encoding with different whitespace)
fails loudly.
"""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.services.devices import _derive_fingerprint

# A fixed Ed25519 key in PEM.
KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAoX8Xl8QmRYk9RgZm9hJpZos/PqM3NtLM2dhECjIKPEk=
-----END PUBLIC KEY-----"""


@pytest.fixture(scope="module")
def public_key() -> ed25519.Ed25519PublicKey:
    return serialization.load_pem_public_key(KEY_PEM.encode("utf-8"))


def test_canonical_der_digest(public_key: ed25519.Ed25519PublicKey) -> None:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    expected = hashlib.sha256(der).hexdigest()
    assert _derive_fingerprint(KEY_PEM) == expected
    assert len(expected) == 64


def test_pem_string_hashing_is_rejected(public_key: ed25519.Ed25519PublicKey) -> None:
    """The historical bug (hashing the PEM string) yields a different digest."""
    pem_hash = hashlib.sha256(KEY_PEM.encode("utf-8")).hexdigest()
    assert _derive_fingerprint(KEY_PEM) != pem_hash


def test_whitespace_insensitive(public_key: ed25519.Ed25519PublicKey) -> None:
    """Canonicalization must survive PEM whitespace/line-ending variance."""
    indented = "\n".join("  " + ln if ln else "" for ln in KEY_PEM.splitlines())
    crlf = KEY_PEM.replace("\n", "\r\n")
    a = _derive_fingerprint(KEY_PEM)
    assert _derive_fingerprint(indented) == a
    assert _derive_fingerprint(crlf) == a

"""Unit tests for password hashing primitives."""

from __future__ import annotations

import pytest
from app.core.security import hash_password, verify_password


def test_hash_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash)


def test_wrong_password_is_rejected() -> None:
    password_hash = hash_password("right-password")
    assert not verify_password("wrong-password", password_hash)


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_corrupt_hash_is_safely_rejected() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")

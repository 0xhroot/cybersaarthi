"""Unit tests for the HMAC-signed access tokens (RFC-less, stdlib-only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.auth import (
    EXPIRES_AT_CLAIM,
    IDENTIFIER_PER_CLAIM,
    ISSUED_AT_CLAIM,
    NONCE_CLAIM,
    create_access_token,
    decode_access_token,
)

SECRET = "unit-test-secret"


def _now() -> datetime:
    return datetime(2030, 1, 1, tzinfo=UTC)


def test_round_trip_returns_the_user_id() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, secret=SECRET, expires_minutes=30, now=_now())
    assert decode_access_token(token, secret=SECRET, now=_now()) == user_id


def test_different_secret_rejects_the_token() -> None:
    token = create_access_token(uuid.uuid4(), secret=SECRET, expires_minutes=30, now=_now())
    assert decode_access_token(token, secret="other-secret", now=_now()) is None


def test_expired_token_is_rejected() -> None:
    token = create_access_token(uuid.uuid4(), secret=SECRET, expires_minutes=30, now=_now())
    later = _now() + timedelta(minutes=31)
    assert decode_access_token(token, secret=SECRET, now=later) is None


def test_token_is_accepted_through_expiry_but_not_after_it() -> None:
    token = create_access_token(uuid.uuid4(), secret=SECRET, expires_minutes=30, now=_now())
    at_expiry = _now() + timedelta(minutes=30)
    assert decode_access_token(token, secret=SECRET, now=at_expiry) is not None
    just_after = _now() + timedelta(minutes=30, seconds=1)
    assert decode_access_token(token, secret=SECRET, now=just_after) is None


def test_tampered_payload_changes_signature_verification() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, secret=SECRET, expires_minutes=30, now=_now())
    payload, signature = token.split(".", 1)
    # Flip a character inside the payload: signature no longer matches.
    tampered = ("A" if payload[0] != "A" else "B") + payload[1:]
    assert decode_access_token(f"{tampered}.{signature}", secret=SECRET, now=_now()) is None


def test_malformed_tokens_never_raise() -> None:
    secrets = ["", "no-dot-here", "!!!.$$$", "abc", f"{'x' * 100}.{'y' * 40}"]
    for token in secrets:
        assert decode_access_token(token, secret=SECRET, now=_now()) is None


def test_tokens_are_unique_across_signings() -> None:
    user_id = uuid.uuid4()
    tokens = {
        create_access_token(user_id, secret=SECRET, expires_minutes=30, now=_now())
        for _ in range(20)
    }
    assert len(tokens) == 20


def test_payload_is_self_describing_but_contains_no_credentials() -> None:
    token = create_access_token(uuid.uuid4(), secret=SECRET, expires_minutes=7, now=_now())
    # Only the payload half is readable; it must never carry secrets.
    payload, _ = token.split(".", 1)
    import base64
    import json

    decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert IDENTIFIER_PER_CLAIM in decoded
    assert ISSUED_AT_CLAIM in decoded
    assert EXPIRES_AT_CLAIM in decoded
    assert NONCE_CLAIM in decoded
    assert decoded[EXPIRES_AT_CLAIM] - decoded[ISSUED_AT_CLAIM] == 7 * 60
    assert "password" not in decoded and "hash" not in decoded


def test_user_id_must_be_valid_uuid() -> None:
    import base64
    import hashlib
    import hmac

    payload = {IDENTIFIER_PER_CLAIM: "not-a-uuid", "exp": 4102444800, "iat": 4100000000}
    body = (
        base64.urlsafe_b64encode(
            __import__("json").dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(SECRET.encode(), body.encode("ascii"), hashlib.sha256).hexdigest()
    forged = f"{body}.{signature}"
    # Signature is valid but the uid claim is malformed -> treated as invalid.
    assert decode_access_token(forged, secret=SECRET, now=_now()) is None

"""HMAC-signed bearer access tokens.

Tokens are compact, self-contained and server-verified: a URL-safe base64
JSON payload (user id, issued-at, expiry, one-time nonce) followed by an
HMAC-SHA256 signature. The secret comes from configuration (``SECRET_KEY``)
and the lifetime from ``ACCESS_TOKEN_EXPIRE_MINUTES``, so tokens are
short-lived by design. No credentials or hashes are ever embedded.

Signing uses the standard library only (no new dependencies) and keeps the
verification path constant-time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime

IDENTIFIER_PER_CLAIM = "uid"
ISSUED_AT_CLAIM = "iat"
EXPIRES_AT_CLAIM = "exp"
NONCE_CLAIM = "jti"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes | None:
    try:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)
    except (ValueError, TypeError):
        return None


def create_access_token(
    user_id: uuid.UUID,
    *,
    secret: str,
    expires_minutes: int,
    now: datetime | None = None,
) -> str:
    """Sign an access token for *user_id* valid for ``expires_minutes``."""
    issued_at = now if now is not None else datetime.now(UTC)
    payload = {
        IDENTIFIER_PER_CLAIM: str(user_id),
        ISSUED_AT_CLAIM: int(issued_at.timestamp()),
        EXPIRES_AT_CLAIM: int(issued_at.timestamp()) + int(expires_minutes) * 60,
        NONCE_CLAIM: secrets.token_hex(16),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64url_encode(body)
    signature = _sign(encoded, secret)
    return f"{encoded}.{signature}"


def decode_access_token(
    token: str,
    *,
    secret: str,
    now: datetime | None = None,
) -> uuid.UUID | None:
    """Return the token's user id, or ``None`` if the token is invalid.

    ``None`` covers malformed encoding, a bad signature (tampered token),
    an expired token and an unreadable user claim. Verification never raises.
    """
    if "." not in token:
        return None
    encoded, supplied_signature = token.split(".", 1)
    expected = _sign(encoded, secret)
    if not hmac.compare_digest(supplied_signature, expected):
        return None
    body = _b64url_decode(encoded)
    if body is None:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expires_at = payload.get(EXPIRES_AT_CLAIM)
    if not isinstance(expires_at, int):
        return None
    current = now if now is not None else datetime.now(UTC)
    if current.timestamp() > expires_at:
        return None
    user_id = payload.get(IDENTIFIER_PER_CLAIM)
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None


def _sign(encoded_payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256)
    return digest.hexdigest()

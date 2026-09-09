"""Security primitives.

Phase 1 establishes the building blocks only; no authentication endpoints are
exposed yet. Passwords are hashed before persistence so the database never
stores recoverable credentials.
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash *password* with bcrypt and return the encoded hash."""
    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if *password* matches the stored bcrypt *password_hash*."""
    try:
        stored = password_hash.encode("utf-8")
        return bcrypt.checkpw(password.encode("utf-8"), stored)
    except (ValueError, TypeError):
        return False

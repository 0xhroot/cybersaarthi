"""Recanonicalize device fingerprints: recompute stored fingerprint column.

Canonical fingerprint = SHA-256 over the DER-spki-of-the-key. Earlier writes
hashed the PEM string; recompute every stored fingerprint from the enrolled
public_key so all rows match the DER canonical vector the Android client and
web UI now use.

Revision ID: cd34ef56ab78
Revises: b7d4f2c9a1e0
Create Date: 2026-09-13 02:20:00.000000
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from cryptography.hazmat.primitives import serialization

revision: str = "cd34ef56ab78"
down_revision: str | None = "6b4a8da27811"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _canonical_fingerprint(public_key_pem: str) -> str | None:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except Exception:
        return None
    der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    table = sa.table(
        "field_devices",
        sa.column("id", sa.String()),
        sa.column("public_key", sa.Text()),
        sa.column("fingerprint", sa.String(128)),
    )
    rows = bind.execute(sa.select(table.c.id, table.c.public_key)).fetchall()
    for row_id, public_key in rows:
        fp = _canonical_fingerprint(public_key) if public_key else None
        if fp is None:
            continue
        bind.execute(
            table.update()
            .where(table.c.id == row_id)
            .values(fingerprint=fp)
        )


def downgrade() -> None:
    pass

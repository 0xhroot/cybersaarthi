"""add evidence_files.deleted_at (soft delete)

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
Create Date: 2026-09-02 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_files",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_evidence_files_deleted_at"), "evidence_files", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_evidence_files_deleted_at"), table_name="evidence_files")
    op.drop_column("evidence_files", "deleted_at")

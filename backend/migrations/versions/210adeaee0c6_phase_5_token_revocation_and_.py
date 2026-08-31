"""phase_5_token_revocation_and_concurrency_unique_ingestion

Revision ID: 210adeaee0c6
Revises: cc19f4d2b003
Create Date: 2026-08-31 11:34:33.310496
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '210adeaee0c6'
down_revision: str | None = 'cc19f4d2b003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A08: prevent redundant concurrent ingestion of the same evidence file.
    op.create_unique_constraint(
        "uq_ingestion_jobs_case_evidence",
        "ingestion_jobs",
        ["case_id", "evidence_file_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ingestion_jobs_case_evidence",
        "ingestion_jobs",
        type_="unique",
    )

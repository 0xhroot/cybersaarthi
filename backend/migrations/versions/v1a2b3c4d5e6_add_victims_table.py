"""add victims table

Revision ID: v1a2b3c4d5e6
Revises: d2e3f4a5b6c7
Create Date: 2026-09-09 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v1a2b3c4d5e6"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "victims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Basic identity
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column(
            "classification",
            sa.String(length=32),
            server_default="individual",
            nullable=False,
        ),
        # Contact
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        # Incident
        sa.Column("incident_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incident_type", sa.String(length=128), nullable=True),
        sa.Column("fraud_category", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # Financial
        sa.Column("reported_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("amount_lost", sa.Float(), nullable=True),
        sa.Column("recovery_amount", sa.Float(), nullable=True),
        # Digital
        sa.Column("digital_accounts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("devices", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("wallet_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Investigation
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="reported",
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=True),
        sa.Column("investigator_notes", sa.Text(), nullable=True),
        sa.Column("recovery_status", sa.String(length=64), nullable=True),
        # Audit
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'under_investigation', 'evidence_collected', "
            "'recovery_initiated', 'recovered', 'closed')",
            name=op.f("ck_victims_victim_status_valid"),
        ),
        sa.CheckConstraint(
            "classification IN ('individual', 'organization', 'government', "
            "'financial_institution', 'unknown')",
            name=op.f("ck_victims_victim_classification_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_victims")),
    )
    op.create_index(op.f("ix_victims_case_id"), "victims", ["case_id"], unique=False)
    op.create_index(op.f("ix_victims_status"), "victims", ["status"], unique=False)
    op.create_index(
        op.f("ix_victims_case_status"), "victims", ["case_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_victims_case_status"), table_name="victims")
    op.drop_index(op.f("ix_victims_status"), table_name="victims")
    op.drop_index(op.f("ix_victims_case_id"), table_name="victims")
    op.drop_table("victims")

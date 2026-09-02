"""add case membership (case_members)

Revision ID: c1a2b3c4d5e6
Revises: b7d4f2c9a1e0
Create Date: 2026-09-02 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3c4d5e6"
down_revision: str | None = "b7d4f2c9a1e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_members",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default="collaborator",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_case_members_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_case_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("case_id", "user_id", name=op.f("pk_case_members")),
        sa.CheckConstraint(
            "role IN ('collaborator', 'viewer')",
            name=op.f("ck_case_members_case_member_role_valid"),
        ),
    )


def downgrade() -> None:
    op.drop_table("case_members")

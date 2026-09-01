"""phase 5: user account lifecycle status

Revision ID: b7d4f2c9a1e0
Revises: 210adeaee0c6
Create Date: 2026-09-02 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4f2c9a1e0"
down_revision: str | None = "210adeaee0c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCOUNT_STATUSES = ("PENDING", "ACTIVE", "SUSPENDED", "REJECTED")


def upgrade() -> None:
    # Introduce the four-state account lifecycle. Existing rows with the old
    # boolean flag are migrated to the closest status: active -> ACTIVE,
    # inactive -> SUSPENDED (previously "deactivated").
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="ACTIVE",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)
    op.execute(
        "UPDATE users SET status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'SUSPENDED' END"
    )
    op.create_check_constraint(
        op.f("ck_users_user_status_valid"),
        "users",
        "status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'REJECTED')",
    )
    op.drop_column("users", "is_active")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.execute(
        "UPDATE users SET is_active = (status = 'ACTIVE')"
    )
    op.drop_constraint(op.f("ck_users_user_status_valid"), "users", type_="check")
    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_column("users", "status")
"""phase 4 productization: auth, rbac, ownership, audit, findings workflow

Revision ID: cc19f4d2b003
Revises: a4b9c7e16d20
Create Date: 2026-08-29 12:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cc19f4d2b003"
down_revision: str | None = "a4b9c7e16d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role_id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://cybersaarthi.local/roles/{name}")


SEED_ROLES = (
    (
        "ADMIN",
        "Full control: users, cases, evidence, ingestion, analytics, findings, audit.",
    ),
    (
        "INVESTIGATOR",
        "Runs investigations end to end: cases, evidence, analytics, findings lifecycle, audit.",
    ),
    (
        "ANALYST",
        "Read-only case access plus analytics runs and findings review.",
    ),
    (
        "VIEWER",
        "Read-only access to cases, evidence and findings.",
    ),
)


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name=op.f("fk_cases_owner_id_users"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_cases_owner_id"), "cases", ["owner_id"], unique=False)

    op.add_column(
        "findings",
        sa.Column(
            "reviewed_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name=op.f("fk_findings_reviewed_by_users"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_findings_reviewed_by"), "findings", ["reviewed_by"], unique=False)
    op.add_column("findings", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("findings", sa.Column("review_comment", sa.Text(), nullable=True))

    op.add_column(
        "audit_logs",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey(
                "cases.id",
                name=op.f("fk_audit_logs_case_id_cases"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_audit_logs_case_id"), "audit_logs", ["case_id"], unique=False)

    op.add_column(
        "analytics_runs",
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name=op.f("fk_analytics_runs_actor_id_users"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_analytics_runs_actor_id"), "analytics_runs", ["actor_id"], unique=False
    )

    op.add_column(
        "ingestion_jobs",
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name=op.f("fk_ingestion_jobs_actor_id_users"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_ingestion_jobs_actor_id"), "ingestion_jobs", ["actor_id"], unique=False
    )

    seed_roles_table = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        seed_roles_table,
        [{"id": _role_id(name), "name": name, "description": description} for name, description in SEED_ROLES],
    )


def downgrade() -> None:
    seed_roles_table = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    for name, _ in SEED_ROLES:
        op.execute(
            seed_roles_table.delete().where(seed_roles_table.c.id == _role_id(name))
        )

    op.drop_column("ingestion_jobs", "actor_id")
    op.drop_column("analytics_runs", "actor_id")
    op.drop_index(op.f("ix_audit_logs_case_id"), table_name="audit_logs")
    op.drop_column("audit_logs", "case_id")
    op.drop_column("findings", "review_comment")
    op.drop_column("findings", "reviewed_at")
    op.drop_index(op.f("ix_findings_reviewed_by"), table_name="findings")
    op.drop_column("findings", "reviewed_by")
    op.drop_index(op.f("ix_cases_owner_id"), table_name="cases")
    op.drop_column("cases", "owner_id")
"""phase 3 investigation intelligence engine

Revision ID: a4b9c7e16d20
Revises: f31fa700fb23
Create Date: 2026-08-29 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4b9c7e16d20"
down_revision: str | None = "f31fa700fb23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_runs",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_analytics_runs_analytics_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_analytics_runs_case_id_cases"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_runs")),
    )
    op.create_index(op.f("ix_analytics_runs_case_id"), "analytics_runs", ["case_id"], unique=False)

    op.create_table(
        "metric_results",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("raw_value", sa.Float(), nullable=False),
        sa.Column("normalized_score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_metric_results_case_id_cases"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"], name=op.f("fk_metric_results_entity_id_entities"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analytics_runs.id"], name=op.f("fk_metric_results_run_id_analytics_runs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_results")),
    )
    op.create_index(op.f("ix_metric_results_case_id"), "metric_results", ["case_id"], unique=False)
    op.create_index(op.f("ix_metric_results_case_metric"), "metric_results", ["case_id", "metric_name"], unique=False)
    op.create_index(op.f("ix_metric_results_case_entity"), "metric_results", ["case_id", "entity_id"], unique=False)
    op.create_index(op.f("ix_metric_results_run_id"), "metric_results", ["run_id"], unique=False)

    op.create_table(
        "community_results",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("community_id", sa.String(length=32), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("internal_edges", sa.Integer(), nullable=False),
        sa.Column("external_edges", sa.Integer(), nullable=False),
        sa.Column("dominant_entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dominant_relationship_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("member_entity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_community_results_case_id_cases"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analytics_runs.id"], name=op.f("fk_community_results_run_id_analytics_runs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_community_results")),
        sa.UniqueConstraint("case_id", "run_id", "community_id", name="uq_community_run_id"),
    )
    op.create_index(op.f("ix_community_results_case_id"), "community_results", ["case_id"], unique=False)

    op.create_table(
        "network_profiles",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "tier IN ('FOCAL', 'SIGNIFICANT', 'MONITORED', 'PERIPHERAL')",
            name=op.f("ck_network_profiles_network_profile_tier_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_network_profiles_case_id_cases"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"], name=op.f("fk_network_profiles_entity_id_entities"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analytics_runs.id"], name=op.f("fk_network_profiles_run_id_analytics_runs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_network_profiles")),
        sa.UniqueConstraint("entity_id", "run_id", name="uq_network_profile_entity_run"),
    )
    op.create_index(op.f("ix_network_profiles_case_id"), "network_profiles", ["case_id"], unique=False)
    op.create_index(op.f("ix_network_profiles_entity_id"), "network_profiles", ["entity_id"], unique=False)

    op.create_table(
        "findings",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("finding_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("affected_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_relationships", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "finding_type IN ('pattern', 'anomaly', 'hypothesis', "
            "'network_insight', 'relationship_insight')",
            name=op.f("ck_findings_finding_type_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_findings_finding_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('NEW', 'REVIEWED', 'DISMISSED', 'CONFIRMED')",
            name=op.f("ck_findings_finding_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_findings_case_id_cases"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analytics_runs.id"], name=op.f("fk_findings_run_id_analytics_runs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
    )
    op.create_index(op.f("ix_findings_case_id"), "findings", ["case_id"], unique=False)
    op.create_index(op.f("ix_findings_case_status"), "findings", ["case_id", "status"], unique=False)
    op.create_index(op.f("ix_findings_case_type"), "findings", ["case_id", "finding_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_case_type"), table_name="findings")
    op.drop_index(op.f("ix_findings_case_status"), table_name="findings")
    op.drop_index(op.f("ix_findings_case_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_network_profiles_entity_id"), table_name="network_profiles")
    op.drop_index(op.f("ix_network_profiles_case_id"), table_name="network_profiles")
    op.drop_table("network_profiles")
    op.drop_index(op.f("ix_community_results_case_id"), table_name="community_results")
    op.drop_table("community_results")
    op.drop_index(op.f("ix_metric_results_run_id"), table_name="metric_results")
    op.drop_index(op.f("ix_metric_results_case_entity"), table_name="metric_results")
    op.drop_index(op.f("ix_metric_results_case_metric"), table_name="metric_results")
    op.drop_index(op.f("ix_metric_results_case_id"), table_name="metric_results")
    op.drop_table("metric_results")
    op.drop_index(op.f("ix_analytics_runs_case_id"), table_name="analytics_runs")
    op.drop_table("analytics_runs")
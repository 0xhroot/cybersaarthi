"""evidence intelligence foundation: analysis_jobs + derived_artifacts

Revision ID: a9b8c7d6e5f4
Revises: c8e2f4a6b1d3
Create Date: 2026-10-16 14:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a9b8c7d6e5f4'
down_revision: str | None = 'c8e2f4a6b1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'analysis_jobs',
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('feature', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('total_records', sa.Integer(), nullable=False),
        sa.Column('processed_records', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('result_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('evidence_file_id', sa.Uuid(), nullable=True),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'partial', 'failed', 'canceled')",
            name=op.f('ck_analysis_jobs_analysis_job_status_valid'),
        ),
        sa.CheckConstraint(
            "feature IN ('ingestion', 'entity_resolution', 'timeline', 'contradiction', "
            "'financial_flow', 'cross_case', 'multilingual', 'triage', 'custody', 'report_audit')",
            name=op.f('ck_analysis_jobs_analysis_job_feature_valid'),
        ),
        sa.CheckConstraint(
            'progress >= 0 AND progress <= 100',
            name=op.f('ck_analysis_jobs_analysis_job_progress_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['case_id'], ['cases.id'], name=op.f('fk_analysis_jobs_case_id_cases'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['evidence_file_id'],
            ['evidence_files.id'],
            name=op.f('fk_analysis_jobs_evidence_file_id_evidence_files'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['actor_id'], ['users.id'], name=op.f('fk_analysis_jobs_actor_id_users'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_jobs')),
        sa.UniqueConstraint('case_id', 'idempotency_key', name=op.f('uq_analysis_jobs_case_idempotency')),
    )
    op.create_index('ix_analysis_jobs_case_id', 'analysis_jobs', ['case_id'], unique=False)
    op.create_index('ix_analysis_jobs_actor_id', 'analysis_jobs', ['actor_id'], unique=False)
    op.create_index(
        'ix_analysis_jobs_case_feature_status',
        'analysis_jobs',
        ['case_id', 'feature', 'status'],
        unique=False,
    )

    op.create_table(
        'derived_artifacts',
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('validation_status', sa.String(length=16), nullable=False),
        sa.Column('evidence_file_id', sa.Uuid(), nullable=True),
        sa.Column('source_record_id', sa.Uuid(), nullable=True),
        sa.Column('source_locator', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('parser_version', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=True),
        sa.Column('model_profile', sa.String(length=16), nullable=True),
        sa.Column('analysis_job_id', sa.Uuid(), nullable=True),
        sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Uuid(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('parent_artifact_id', sa.Uuid(), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('extraction', 'entity_resolution', 'timeline_proposal', "
            "'contradiction', 'financial_finding', 'cross_case_link', 'translation', "
            "'triage_observation', 'custody_finding', 'report_claim_review')",
            name=op.f('ck_derived_artifacts_derived_artifact_kind_valid'),
        ),
        sa.CheckConstraint(
            "origin IN ('llm', 'deterministic')",
            name=op.f('ck_derived_artifacts_derived_artifact_origin_valid'),
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'failed', 'superseded')",
            name=op.f('ck_derived_artifacts_derived_artifact_status_valid'),
        ),
        sa.CheckConstraint(
            "validation_status IN ('valid', 'flagged', 'invalid')",
            name=op.f('ck_derived_artifacts_derived_artifact_validation_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['case_id'], ['cases.id'], name=op.f('fk_derived_artifacts_case_id_cases'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['evidence_file_id'],
            ['evidence_files.id'],
            name=op.f('fk_derived_artifacts_evidence_file_id_evidence_files'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['source_record_id'],
            ['source_records.id'],
            name=op.f('fk_derived_artifacts_source_record_id_source_records'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['analysis_job_id'],
            ['analysis_jobs.id'],
            name=op.f('fk_derived_artifacts_analysis_job_id_analysis_jobs'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['reviewed_by'], ['users.id'], name=op.f('fk_derived_artifacts_reviewed_by_users'), ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['parent_artifact_id'],
            ['derived_artifacts.id'],
            name=op.f('fk_derived_artifacts_parent_artifact_id_derived_artifacts'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'], name=op.f('fk_derived_artifacts_created_by_users'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_derived_artifacts')),
        sa.UniqueConstraint(
            'case_id', 'kind', 'content_hash', name=op.f('uq_derived_artifacts_case_kind_hash')
        ),
    )
    op.create_index('ix_derived_artifacts_case_id', 'derived_artifacts', ['case_id'], unique=False)
    op.create_index(
        'ix_derived_artifacts_evidence_file_id', 'derived_artifacts', ['evidence_file_id'], unique=False
    )
    op.create_index(
        'ix_derived_artifacts_source_record_id', 'derived_artifacts', ['source_record_id'], unique=False
    )
    op.create_index(
        'ix_derived_artifacts_analysis_job_id', 'derived_artifacts', ['analysis_job_id'], unique=False
    )
    op.create_index(
        'ix_derived_artifacts_case_kind_status',
        'derived_artifacts',
        ['case_id', 'kind', 'status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_derived_artifacts_case_kind_status', table_name='derived_artifacts')
    op.drop_index('ix_derived_artifacts_analysis_job_id', table_name='derived_artifacts')
    op.drop_index('ix_derived_artifacts_source_record_id', table_name='derived_artifacts')
    op.drop_index('ix_derived_artifacts_evidence_file_id', table_name='derived_artifacts')
    op.drop_index('ix_derived_artifacts_case_id', table_name='derived_artifacts')
    op.drop_table('derived_artifacts')
    op.drop_index('ix_analysis_jobs_case_feature_status', table_name='analysis_jobs')
    op.drop_index('ix_analysis_jobs_actor_id', table_name='analysis_jobs')
    op.drop_index('ix_analysis_jobs_case_id', table_name='analysis_jobs')
    op.drop_table('analysis_jobs')

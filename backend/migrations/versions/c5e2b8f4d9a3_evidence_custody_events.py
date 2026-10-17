"""evidence custody events + recorded artifact status (phase 2, feature 9)

Revision ID: c5e2b8f4d9a3
Revises: a9b8c7d6e5f4
Create Date: 2026-10-16 18:40:00.000000

No chain-of-custody table existed anywhere in the schema, so this migration
adds the first one (events are only recorded going forward; nothing is
back-filled) and widens derived_artifacts.status with ``recorded`` for
deterministic verification results and AI explanations that must never enter
the human approval queue.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c5e2b8f4d9a3'
down_revision: str | None = 'a9b8c7d6e5f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'evidence_custody_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('evidence_file_id', sa.Uuid(), nullable=True),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('collector', sa.String(length=255), nullable=True),
        sa.Column('transferor', sa.String(length=255), nullable=True),
        sa.Column('recipient', sa.String(length=255), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('method', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_sha256', sa.String(length=64), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('collected', 'transferred', 'received', 'sealed', "
            "'unsealed', 'verified', 'accessed', 'exported', 'restored', 'disposed')",
            name=op.f('ck_evidence_custody_events_custody_event_type_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['actor_user_id'],
            ['users.id'],
            name=op.f('fk_evidence_custody_events_actor_user_id_users'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['case_id'],
            ['cases.id'],
            name=op.f('fk_evidence_custody_events_case_id_cases'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['evidence_file_id'],
            ['evidence_files.id'],
            name=op.f('fk_evidence_custody_events_evidence_file_id_evidence_files'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_custody_events')),
    )
    op.create_index(
        'ix_evidence_custody_events_case_id', 'evidence_custody_events', ['case_id'], unique=False
    )
    op.create_index(
        'ix_evidence_custody_events_evidence_file_id',
        'evidence_custody_events',
        ['evidence_file_id'],
        unique=False,
    )
    op.create_index(
        'ix_evidence_custody_events_evidence_occurred',
        'evidence_custody_events',
        ['evidence_file_id', 'occurred_at'],
        unique=False,
    )
    # derived_artifacts.status gains 'recorded' (verification facts and AI
    # explanations are informational; they are never queued for approval).
    op.drop_constraint(
        op.f('ck_derived_artifacts_derived_artifact_status_valid'),
        'derived_artifacts',
        type_='check',
    )
    op.create_check_constraint(
        op.f('ck_derived_artifacts_derived_artifact_status_valid'),
        'derived_artifacts',
        "status IN ('pending_review', 'approved', 'rejected', 'failed', "
        "'superseded', 'recorded')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('ck_derived_artifacts_derived_artifact_status_valid'),
        'derived_artifacts',
        type_='check',
    )
    op.create_check_constraint(
        op.f('ck_derived_artifacts_derived_artifact_status_valid'),
        'derived_artifacts',
        "status IN ('pending_review', 'approved', 'rejected', 'failed', 'superseded')",
    )
    op.drop_index('ix_evidence_custody_events_evidence_occurred', table_name='evidence_custody_events')
    op.drop_index('ix_evidence_custody_events_evidence_file_id', table_name='evidence_custody_events')
    op.drop_index('ix_evidence_custody_events_case_id', table_name='evidence_custody_events')
    op.drop_table('evidence_custody_events')

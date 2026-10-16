"""allow 'hypothesize' as an ai conversation mode

Revision ID: c8e2f4a6b1d3
Revises: b4f1c2d3e4a5
Create Date: 2026-10-16 11:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'c8e2f4a6b1d3'
down_revision: str | None = 'b4f1c2d3e4a5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = 'ck_ai_conversations_ai_conversation_mode_valid'
TABLE = 'ai_conversations'
# Ordered exactly like the model's AI_CONVERSATION_MODES.
WITH_HYPOTHESIZE = (
    'general', 'case', 'evidence', 'graph', 'copilot', 'report', 'knowledge',
    'analysis', 'hypothesize',
)
WITHOUT_HYPOTHESIZE = (
    'general', 'case', 'evidence', 'graph', 'copilot', 'report', 'knowledge',
    'analysis',
)


def _set_modes(modes: tuple[str, ...]) -> None:
    values = ", ".join(f"'{mode}'" for mode in modes)
    # op.f() marks the already-convention-prefixed name so drop does not get a
    # second `ck_<table>_` prefix bolted on by the naming convention.
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_='check')
    op.execute(
        f'ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} CHECK (mode IN ({values}))'
    )


def upgrade() -> None:
    _set_modes(WITH_HYPOTHESIZE)


def downgrade() -> None:
    # Hypothesize threads predate the downgrade; their mode label is demoted
    # to 'general' (messages and ownership are untouched).
    op.execute(f"UPDATE {TABLE} SET mode = 'general' WHERE mode = 'hypothesize'")
    _set_modes(WITHOUT_HYPOTHESIZE)

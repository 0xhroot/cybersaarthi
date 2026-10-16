"""allow 'analysis' as an ai conversation mode

Revision ID: b4f1c2d3e4a5
Revises: 36e5ad8fd75e
Create Date: 2026-10-16 08:12:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'b4f1c2d3e4a5'
down_revision: str | None = '36e5ad8fd75e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = 'ck_ai_conversations_ai_conversation_mode_valid'
TABLE = 'ai_conversations'
# Ordered exactly like the model's AI_CONVERSATION_MODES.
WITH_ANALYSIS = ('general', 'case', 'evidence', 'graph', 'copilot', 'report',
                 'knowledge', 'analysis')
WITHOUT_ANALYSIS = ('general', 'case', 'evidence', 'graph', 'copilot', 'report',
                    'knowledge')


def _set_modes(modes: tuple[str, ...]) -> None:
    values = ", ".join(f"'{mode}'" for mode in modes)
    # op.f() marks the already-convention-prefixed name so drop does not get a
    # second `ck_<table>_` prefix bolted on by the naming convention.
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_='check')
    op.execute(
        f'ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} CHECK (mode IN ({values}))'
    )


def upgrade() -> None:
    _set_modes(WITH_ANALYSIS)


def downgrade() -> None:
    # Analysis threads predate the downgrade; their mode is demoted to
    # 'general' so the narrower constraint can always be restored (losing only
    # the mode label, never messages or ownership).
    op.execute(f"UPDATE {TABLE} SET mode = 'general' WHERE mode = 'analysis'")
    _set_modes(WITHOUT_ANALYSIS)

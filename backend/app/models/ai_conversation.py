"""AI assistant conversations (per user, optionally scoped to a case)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

AI_CONVERSATION_MODES = ("general", "case", "evidence", "graph", "copilot", "report", "knowledge")
AI_CONVERSATION_STATUSES = ("active", "archived")


class AIConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chat thread owned by one user, optionally bound to one case."""

    __tablename__ = "ai_conversations"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('general', 'case', 'evidence', 'graph', 'copilot', 'report', 'knowledge')",
            name="ai_conversation_mode_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ai_conversation_status_valid",
        ),
        Index("ix_ai_conversations_user_id", "user_id"),
        Index("ix_ai_conversations_case_id", "case_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New conversation")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # Prompt/behavior version used for the latest completion in this thread.
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    settings: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AIConversation id={self.id} mode={self.mode!r} user={self.user_id}>"


__all__ = [
    "AI_CONVERSATION_MODES",
    "AI_CONVERSATION_STATUSES",
    "AIConversation",
]

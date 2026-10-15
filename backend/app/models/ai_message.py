"""AI assistant messages with provenance and tool-call audit fields."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

AI_MESSAGE_ROLES = ("user", "assistant", "system", "tool")


class AIMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One message in an AI conversation.

    Assistant messages keep validated source references (ids the *user* was
    authorized to see at generation time) and a tool-call audit trail. Prompt
    and answer text are stored so investigators can revisit AI assistance
    during a case; they are excluded from any export unless explicitly asked.
    """

    __tablename__ = "ai_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ai_message_role_valid",
        ),
        Index("ix_ai_messages_conversation_id", "conversation_id"),
        Index("ix_ai_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # [{type, id, label, url}] — validated refs, not model hallucinations.
    sources: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    # [{tool, ok, arguments, error, duration_ms}] — tool-loop audit trail.
    tool_events: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    grounded: Mapped[bool] = mapped_column(nullable=False, default=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AIMessage id={self.id} role={self.role!r} conv={self.conversation_id}>"


__all__ = ["AIMessage", "AI_MESSAGE_ROLES"]

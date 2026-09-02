"""Association model linking users to cases (case membership)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# A member's role within a case (independent of their global RBAC role).
CASE_MEMBER_ROLES = ("collaborator", "viewer")


class CaseMember(Base):
    __tablename__ = "case_members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('collaborator', 'viewer')",
            name="case_member_role_valid",
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), default="collaborator", nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CaseMember case={self.case_id} user={self.user_id} role={self.role!r}>"

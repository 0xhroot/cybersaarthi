"""User model. Account lifecycle is Phase 5: every account carries a status
(PENDING/ACTIVE/SUSPENDED/REJECTED) that drives both authentication and the
admin approval workflow."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AccountStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ACCOUNT_STATUSES = tuple(status.value for status in AccountStatus)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'REJECTED')",
            name="user_status_valid",
        ),
    )

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default=AccountStatus.ACTIVE.value,
        index=True,
        nullable=False,
    )

    @property
    def is_active(self) -> bool:
        """Backward-compatible read-only flag: only ACTIVE accounts count."""
        return self.status == AccountStatus.ACTIVE.value

    @property
    def is_pending(self) -> bool:
        return self.status == AccountStatus.PENDING.value

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} status={self.status!r}>"

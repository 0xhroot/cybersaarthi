"""EntityAlias - one of the surface forms an entity is known under."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "alias_value", name="uq_entity_aliases_entity_value"),
    )

    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    alias_value: Mapped[str] = mapped_column(String(512), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), default="value", nullable=False)

    def __repr__(self) -> str:
        return f"<EntityAlias id={self.id} value={self.alias_value!r}>"

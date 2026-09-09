"""DataSource - a named provenance type for ingested evidence (CSV, JSON, TXT, ...)."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

BUILTIN_DATA_SOURCES = ("csv", "json", "txt", "manual", "database")


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DataSource id={self.id} name={self.name!r}>"

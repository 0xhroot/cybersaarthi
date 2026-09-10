"""FieldDevice - a generic secure evidence-collection device registered to a case.

Devices present a keypair whose public half is bound (and administrator-approved)
to the case. Any evidence signed by the private key is verifiable end-to-end. The
verification itself happens server-side; the ``public_key`` is never used by the
client to encrypt, and ``secret_key`` never leaves the device.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

FIELD_DEVICE_PLATFORMS = (
    "android_mobile",
    "esp32",
    "raspberry_pi",
    "tablet",
    "laptop",
    "other",
)

FIELD_DEVICE_STATUSES = ("pending", "approved", "revoked", "suspended")

SIGNATURE_ALGORITHMS = ("RSA-SHA256", "Ed25519")


class FieldDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_devices"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('android_mobile', 'esp32', 'raspberry_pi', 'tablet', 'laptop', 'other')",
            name="field_device_platform_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'revoked', 'suspended')",
            name="field_device_status_valid",
        ),
        CheckConstraint(
            "signature_algorithm IN ('RSA-SHA256', 'Ed25519')",
            name="field_device_signature_algorithm_valid",
        ),
        UniqueConstraint("case_id", "serial", name="uq_field_devices_case_serial"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    serial: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(
        String(32), default="RSA-SHA256", nullable=False
    )
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<FieldDevice id={self.id} serial={self.serial!r} status={self.status!r}>"

"""IoT - registered devices and their telemetry for a fraud investigation.

Investigators register physical or logical devices (mobile phones, routers,
GPS trackers, smart devices, vehicle telematics) discovered as part of a case.
Every device can emit timestamped events that capture location, connectivity,
messaging or tamper activity relevant to the investigation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

IOT_DEVICE_TYPES = (
    "mobile",
    "router",
    "gps_tracker",
    "smart_device",
    "vehicle",
    "cctv",
    "computer",
    "other",
)

IOT_DEVICE_STATUSES = ("registered", "active", "inactive", "seized", "removed")
IOT_EVENT_TYPES = (
    "location",
    "connectivity",
    "message",
    "call",
    "app_use",
    "tamper",
    "power",
    "network",
    "custom",
)


class IoTDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "iot_devices"
    __table_args__ = (
        CheckConstraint(
            "device_type IN ('mobile', 'router', 'gps_tracker', 'smart_device', "
            "'vehicle', 'cctv', 'computer', 'other')",
            name="iot_device_type_valid",
        ),
        CheckConstraint(
            "status IN ('registered', 'active', 'inactive', 'seized', 'removed')",
            name="iot_device_status_valid",
        ),
        UniqueConstraint("case_id", "serial_number", name="uq_iot_devices_case_id"),
        Index("ix_iot_devices_case_id", "case_id"),
        Index("ix_iot_devices_case_status", "case_id", "status"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), default="mobile", nullable=False)
    make: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[str] = mapped_column(String(255), nullable=False)
    imei: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    os: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="registered", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    registered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IoTDevice id={self.id} name={self.name!r} type={self.device_type!r} "
            f"status={self.status!r}>"
        )


class IoTEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single telemetry event reported by (or about) a registered device."""

    __tablename__ = "iot_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('location', 'connectivity', 'message', 'call', "
            "'app_use', 'tamper', 'power', 'network', 'custom')",
            name="iot_event_type_valid",
        ),
        Index("ix_iot_events_case_id", "case_id"),
        Index("ix_iot_events_device_id", "device_id"),
        Index("ix_iot_events_device_time", "device_id", "event_time"),
        Index("ix_iot_events_case_time", "case_id", "event_time"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IoTEvent id={self.id} device={self.device_id} type={self.event_type!r} "
            f"time={self.event_time}>"
        )

"""add iot devices and events tables

Revision ID: w2b3c4d5e6f7
Revises: v1a2b3c4d5e6
Create Date: 2026-09-09 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "w2b3c4d5e6f7"
down_revision: str | None = "v1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "iot_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "device_type",
            sa.String(length=32),
            server_default="mobile",
            nullable=False,
        ),
        sa.Column("make", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=False),
        sa.Column("imei", sa.String(length=32), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("mac_address", sa.String(length=32), nullable=True),
        sa.Column("os", sa.String(length=128), nullable=True),
        sa.Column("os_version", sa.String(length=128), nullable=True),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("owner_phone", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="registered",
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("firmware_version", sa.String(length=128), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "registered_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "device_type IN ('mobile', 'router', 'gps_tracker', 'smart_device', "
            "'vehicle', 'cctv', 'computer', 'other')",
            name=op.f("ck_iot_devices_iot_device_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('registered', 'active', 'inactive', 'seized', 'removed')",
            name=op.f("ck_iot_devices_iot_device_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_iot_devices")),
        sa.UniqueConstraint(
            "case_id",
            "serial_number",
            name=op.f("uq_iot_devices_case_id"),
        ),
    )
    op.create_index(
        op.f("ix_iot_devices_case_id"), "iot_devices", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_iot_devices_case_status"),
        "iot_devices",
        ["case_id", "status"],
        unique=False,
    )

    op.create_table(
        "iot_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("iot_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("payload", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_label", sa.String(length=512), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "ingested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "event_type IN ('location', 'connectivity', 'message', 'call', "
            "'app_use', 'tamper', 'power', 'network', 'custom')",
            name=op.f("ck_iot_events_iot_event_type_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_iot_events")),
    )
    op.create_index(op.f("ix_iot_events_case_id"), "iot_events", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_iot_events_device_id"), "iot_events", ["device_id"], unique=False
    )
    op.create_index(
        op.f("ix_iot_events_device_time"),
        "iot_events",
        ["device_id", "event_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_iot_events_case_time"),
        "iot_events",
        ["case_id", "event_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_iot_events_case_time"), table_name="iot_events")
    op.drop_index(op.f("ix_iot_events_device_time"), table_name="iot_events")
    op.drop_index(op.f("ix_iot_events_device_id"), table_name="iot_events")
    op.drop_index(op.f("ix_iot_events_case_id"), table_name="iot_events")
    op.drop_table("iot_events")
    op.drop_index(op.f("ix_iot_devices_case_status"), table_name="iot_devices")
    op.drop_index(op.f("ix_iot_devices_case_id"), table_name="iot_devices")
    op.drop_table("iot_devices")
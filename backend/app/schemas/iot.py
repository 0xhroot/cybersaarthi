"""Request/response schemas for IoT device and event management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

IoTDeviceType = Literal[
    "mobile",
    "router",
    "gps_tracker",
    "smart_device",
    "vehicle",
    "cctv",
    "computer",
    "other",
]

IoTDeviceStatus = Literal["registered", "active", "inactive", "seized", "removed"]

IoTEventType = Literal[
    "location",
    "connectivity",
    "message",
    "call",
    "app_use",
    "tamper",
    "power",
    "network",
    "custom",
]


class IoTDeviceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    device_type: IoTDeviceType = "mobile"
    make: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str = Field(min_length=1, max_length=255)
    imei: str | None = Field(default=None, max_length=32)
    ip_address: str | None = Field(default=None, max_length=64)
    mac_address: str | None = Field(default=None, max_length=32)
    os: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=128)
    owner_name: str | None = Field(default=None, max_length=255)
    owner_phone: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=10000)
    firmware_version: str | None = Field(default=None, max_length=128)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    metadata_json: dict[str, object] | None = None


class IoTDeviceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    device_type: IoTDeviceType | None = None
    make: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, min_length=1, max_length=255)
    imei: str | None = Field(default=None, max_length=32)
    ip_address: str | None = Field(default=None, max_length=64)
    mac_address: str | None = Field(default=None, max_length=32)
    os: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=128)
    owner_name: str | None = Field(default=None, max_length=255)
    owner_phone: str | None = Field(default=None, max_length=64)
    status: IoTDeviceStatus | None = None
    description: str | None = Field(default=None, max_length=10000)
    firmware_version: str | None = Field(default=None, max_length=128)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    metadata_json: dict[str, object] | None = None


class IoTDeviceOut(BaseModel):
    id: UUID
    case_id: UUID
    name: str
    device_type: str
    make: str | None
    model: str | None
    serial_number: str
    imei: str | None
    ip_address: str | None
    mac_address: str | None
    os: str | None
    os_version: str | None
    owner_name: str | None
    owner_phone: str | None
    status: str
    description: str | None
    firmware_version: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    metadata_json: dict[str, object] | None
    event_count: int = 0
    created_at: datetime
    updated_at: datetime


class IoTDeviceListResponse(BaseModel):
    items: list[IoTDeviceOut]
    total: int
    limit: int
    offset: int


class IoTEventCreateRequest(BaseModel):
    device_id: UUID
    event_type: IoTEventType
    event_time: datetime
    source: str | None = Field(default=None, max_length=128)
    payload: dict[str, object] | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_label: str | None = Field(default=None, max_length=512)
    confidence: float | None = Field(default=None, ge=0, le=1)
    description: str | None = Field(default=None, max_length=10000)


class IoTEventOut(BaseModel):
    id: UUID
    case_id: UUID
    device_id: UUID
    event_type: str
    event_time: datetime
    source: str | None
    payload: dict[str, object] | None
    latitude: float | None
    longitude: float | None
    location_label: str | None
    confidence: float | None
    description: str | None
    created_at: datetime


class IoTEventListResponse(BaseModel):
    items: list[IoTEventOut]
    total: int
    limit: int
    offset: int


class IoTDeviceStatsOut(BaseModel):
    device_id: UUID
    event_count: int
    by_type: dict[str, int]
    first_event_at: datetime | None
    last_event_at: datetime | None

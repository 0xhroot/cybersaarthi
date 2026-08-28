"""Controlled vocabularies for the entity data-intelligence layer.

Phase 2 enforces canonical string values so the whole pipeline (PostgreSQL,
schemas, Neo4j graph sync) stays consistent and case rows are interchangeable.
"""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    PERSON = "person"
    PHONE = "phone"
    VEHICLE = "vehicle"
    ORGANIZATION = "organization"
    ACCOUNT = "account"
    LOCATION = "location"
    DOCUMENT = "document"
    EVENT = "event"


class EntityStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    REVIEW = "review"
    REJECTED = "rejected"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class RelationshipType(StrEnum):
    CALLED = "called"
    OWNS = "owns"
    WORKS_FOR = "works_for"
    ASSOCIATED_WITH = "associated_with"
    LOCATED_AT = "located_at"
    VISITED = "visited"
    TRANSFERRED_TO = "transferred_to"


class ResolutionDecision(StrEnum):
    AUTO_MATCH = "auto_match"
    REVIEW = "review"
    NO_MATCH = "no_match"


class EvidenceFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    TXT = "txt"


class GraphSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class ExtractionSource(StrEnum):
    """Where an entity mention originated; kept for provenance labels."""

    FIELD = "field"
    NER = "ner"
    RULE = "rule"


class EvidenceFileStatus(StrEnum):
    STORED = "stored"
    PARSED = "parsed"
    PROCESSING = "processing"
    FAILED = "failed"

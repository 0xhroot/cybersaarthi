"""Response schemas for entity and relationship queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

EntityTypeLiteral = Literal[
    "person",
    "phone",
    "vehicle",
    "organization",
    "account",
    "location",
    "document",
    "event",
]

EntityStatusLiteral = Literal["active", "merged", "review", "rejected"]


class EntityAliasOut(BaseModel):
    id: UUID
    alias_value: str
    alias_type: str


class EntityOut(BaseModel):
    id: UUID
    case_id: UUID
    entity_type: EntityTypeLiteral
    canonical_value: str
    display_value: str
    confidence: float | None
    status: EntityStatusLiteral
    created_at: datetime


class EntityDetailOut(EntityOut):
    aliases: list[EntityAliasOut] = []
    context: dict[str, Any] | None = None


class EntityListResponse(BaseModel):
    items: list[EntityOut]
    total: int
    limit: int
    offset: int


class RelationshipOut(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: Literal[
        "called",
        "owns",
        "works_for",
        "associated_with",
        "located_at",
        "visited",
        "transferred_to",
    ]
    confidence: float | None
    explanation: str | None = None
    created_at: datetime


class RelationshipListResponse(BaseModel):
    items: list[RelationshipOut]
    total: int


class ReviewCandidateOut(BaseModel):
    match_id: UUID
    candidate_id: UUID
    candidate_value: str
    candidate_type: EntityTypeLiteral
    target_entity_id: UUID | None
    target_value: str | None
    score: float
    decision: Literal["auto_match", "review"]
    signals: dict[str, Any] | None
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewCandidateOut]
    total: int

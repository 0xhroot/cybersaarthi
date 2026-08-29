"""Import all models so that ``app.models.Base.metadata`` is complete and
Alembic autogenerate / test fixtures can see the full schema."""

from app.models.analytics_run import ANALYTICS_RUN_STATUSES, AnalyticsRun
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.case import Case
from app.models.community_result import CommunityResult
from app.models.data_source import BUILTIN_DATA_SOURCES, DataSource
from app.models.entity import ENTITY_TYPES, Entity
from app.models.entity_alias import EntityAlias
from app.models.entity_candidate import EntityCandidate
from app.models.entity_match import EntityMatch
from app.models.evidence_file import EvidenceFile
from app.models.finding import (
    FINDING_SEVERITIES,
    FINDING_STATUSES,
    FINDING_TYPES,
    Finding,
)
from app.models.ingestion_job import IngestionJob
from app.models.metric_result import METRIC_NAMES, MetricResult
from app.models.network_profile import NETWORK_PROFILE_TIERS, NetworkProfile
from app.models.relationship import RELATIONSHIP_TYPES, Relationship
from app.models.relationship_evidence import RelationshipEvidence
from app.models.role import Role
from app.models.source_record import SourceRecord
from app.models.user import User
from app.models.user_role import UserRole

__all__ = [
    "ANALYTICS_RUN_STATUSES",
    "AnalyticsRun",
    "AuditLog",
    "Base",
    "BUILTIN_DATA_SOURCES",
    "Case",
    "CommunityResult",
    "DataSource",
    "ENTITY_TYPES",
    "Entity",
    "EntityAlias",
    "EntityCandidate",
    "EntityMatch",
    "EvidenceFile",
    "FINDING_SEVERITIES",
    "FINDING_STATUSES",
    "FINDING_TYPES",
    "Finding",
    "IngestionJob",
    "METRIC_NAMES",
    "MetricResult",
    "NETWORK_PROFILE_TIERS",
    "NetworkProfile",
    "RELATIONSHIP_TYPES",
    "Relationship",
    "RelationshipEvidence",
    "Role",
    "SourceRecord",
    "User",
    "UserRole",
]

"""Data access for the analytics pipeline: reads over entities/relationships/
evidence and writes of analytics tables (runs, metrics, communities, profiles,
findings)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.strength import EvidenceStats
from app.models import (
    AnalyticsRun,
    CommunityResult,
    Entity,
    Finding,
    MetricResult,
    NetworkProfile,
    Relationship,
    RelationshipEvidence,
    SourceRecord,
)


@dataclass(frozen=True)
class CaseEvidenceTotals:
    max_evidence_per_relationship: int = 0
    distinct_source_records: int = 0
    distinct_evidence_files: int = 0


class AnalyticsDataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    # Reads ----------------------------------------------------------------
    async def list_entities(self, case_id: uuid.UUID) -> list[Entity]:
        result = await self._session.execute(
            select(Entity).where(Entity.case_id == str(case_id)).order_by(Entity.created_at)
        )
        return list(result.scalars())

    async def list_relationships(self, case_id: uuid.UUID) -> list[Relationship]:
        result = await self._session.execute(
            select(Relationship)
            .where(Relationship.case_id == str(case_id))
            .order_by(Relationship.created_at)
        )
        return list(result.scalars())

    async def evidence_stats_by_relationship(self, case_id: uuid.UUID) -> dict[str, EvidenceStats]:
        """Per canonical relationship: evidence count, types, source records and
        the evidence files those records belong to (for source independence)."""
        rows = await self._session.execute(
            select(
                RelationshipEvidence.relationship_id,
                RelationshipEvidence.evidence_type,
                RelationshipEvidence.source_record_id,
                SourceRecord.evidence_file_id,
            )
            .outerjoin(SourceRecord, SourceRecord.id == RelationshipEvidence.source_record_id)
            .join(
                Relationship,
                Relationship.id == RelationshipEvidence.relationship_id,
            )
            .where(Relationship.case_id == str(case_id))
        )
        grouped: dict[str, dict[str, Any]] = {}
        for relationship_id, evidence_type, source_record_id, evidence_file_id in rows.all():
            entry = grouped.setdefault(
                str(relationship_id),
                {
                    "count": 0,
                    "types": set(),
                    "source_records": set(),
                    "evidence_files": set(),
                },
            )
            entry["count"] += 1
            entry["types"].add(evidence_type)
            if source_record_id:
                entry["source_records"].add(str(source_record_id))
            if evidence_file_id:
                entry["evidence_files"].add(str(evidence_file_id))
        return {
            rel_id: EvidenceStats(
                count=entry["count"],
                types=tuple(sorted(entry["types"])),
                source_record_ids=tuple(sorted(entry["source_records"])),
                evidence_file_ids=tuple(sorted(entry["evidence_files"])),
            )
            for rel_id, entry in grouped.items()
        }

    async def case_evidence_totals(
        self,
        evidence_stats: dict[str, EvidenceStats],
    ) -> CaseEvidenceTotals:
        return CaseEvidenceTotals(
            max_evidence_per_relationship=max(
                (stats.count for stats in evidence_stats.values()), default=0
            ),
            distinct_source_records=len(
                {record for stats in evidence_stats.values() for record in stats.source_record_ids}
            ),
            distinct_evidence_files=len(
                {
                    file_id
                    for stats in evidence_stats.values()
                    for file_id in stats.evidence_file_ids
                }
            ),
        )

    # Writes ---------------------------------------------------------------
    async def create_run(self, case_id: uuid.UUID) -> AnalyticsRun:
        run = AnalyticsRun(
            case_id=str(case_id),
            status="running",
            stage="boot",
            started_at=datetime.now(UTC),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def update_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str | None = None,
        stage: str | None = None,
        error: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        run = await self._session.get(AnalyticsRun, run_id)
        if run is None:
            return
        if status is not None:
            run.status = status
        if stage is not None:
            run.stage = stage
        if error is not None or (status == "failed"):
            run.error = error
        if summary is not None:
            run.summary = summary
        if status == "completed":
            run.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def list_runs(self, case_id: uuid.UUID, limit: int = 20) -> list[AnalyticsRun]:
        result = await self._session.execute(
            select(AnalyticsRun)
            .where(AnalyticsRun.case_id == str(case_id))
            .order_by(AnalyticsRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def save_metric_results(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID | None,
        rows: list[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        self._session.add_all(
            [
                MetricResult(
                    case_id=str(case_id),
                    run_id=str(run_id) if run_id else None,
                    entity_id=row["entity_id"],
                    metric_name=row["metric"],
                    raw_value=row["raw"],
                    normalized_score=row.get("normalized"),
                    rank=row.get("rank"),
                    explanation=row.get("explanation"),
                    extra=row.get("extra"),
                )
                for row in rows
            ]
        )
        await self._session.flush()
        return len(rows)

    async def save_community_results(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID | None,
        communities: list[dict[str, Any]],
    ) -> int:
        if not communities:
            return 0
        self._session.add_all(
            [
                CommunityResult(
                    case_id=str(case_id),
                    run_id=str(run_id) if run_id else None,
                    community_id=row["community_id"],
                    member_count=row["member_count"],
                    density=row["density"],
                    internal_edges=row["internal_edges"],
                    external_edges=row["external_edges"],
                    dominant_entity_types=row.get("dominant_entity_types") or [],
                    dominant_relationship_types=row.get("dominant_relationship_types") or [],
                    member_entity_ids=sorted(row.get("member_entity_ids") or []),
                    score=row.get("score"),
                    explanation=row.get("explanation"),
                )
                for row in communities
            ]
        )
        await self._session.flush()
        return len(communities)

    async def save_network_profiles(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID | None,
        profiles: list[dict[str, Any]],
    ) -> int:
        if not profiles:
            return 0
        self._session.add_all(
            [
                NetworkProfile(
                    entity_id=row["entity_id"],
                    case_id=str(case_id),
                    run_id=str(run_id) if run_id else None,
                    overall_score=row["overall_score"],
                    tier=row["tier"],
                    features=row["features"],
                    signals=row.get("signals") or [],
                    explanation=row.get("explanation"),
                )
                for row in profiles
            ]
        )
        await self._session.flush()
        return len(profiles)

    async def save_findings(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID | None,
        findings: list[dict[str, Any]],
    ) -> int:
        if not findings:
            return 0
        self._session.add_all(
            [
                Finding(
                    case_id=str(case_id),
                    run_id=str(run_id) if run_id else None,
                    finding_type=row["finding_type"],
                    title=row["title"],
                    summary=row["summary"],
                    severity=row["severity"],
                    score=row["score"],
                    confidence=row.get("confidence"),
                    status="NEW",
                    affected_entities=row.get("affected_entities") or [],
                    affected_relationships=row.get("affected_relationships") or [],
                    evidence_ids=row.get("evidence_ids") or [],
                    explanation=row["explanation"],
                    details=row.get("metadata"),
                )
                for row in findings
            ]
        )
        await self._session.flush()
        return len(findings)

    # Findings reads / status --------------------------------------------
    async def list_findings(
        self,
        case_id: uuid.UUID,
        *,
        finding_type: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Finding], int]:
        filters = [Finding.case_id == str(case_id)]
        if finding_type:
            filters.append(Finding.finding_type == finding_type)
        if status:
            filters.append(Finding.status == status)
        if severity:
            filters.append(Finding.severity == severity)
        base = select(Finding).where(*filters)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(Finding.score.desc(), Finding.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), int(total or 0)

    async def get_finding(self, case_id: uuid.UUID, finding_id: uuid.UUID) -> Finding | None:
        result = await self._session.execute(
            select(Finding).where(
                Finding.id == finding_id,
                Finding.case_id == str(case_id),
            )
        )
        return result.scalar_one_or_none()

    async def update_finding_status(
        self,
        finding_id: uuid.UUID,
        status: str,
    ) -> Finding | None:
        finding = await self._session.get(Finding, finding_id)
        if finding is None:
            return None
        finding.status = status
        await self._session.flush()
        return finding

    async def findings_stats(self, case_id: uuid.UUID) -> dict[str, dict[str, int]]:
        rows = await self._session.execute(
            select(
                Finding.finding_type,
                Finding.severity,
                Finding.status,
                Finding.id,
            ).where(Finding.case_id == str(case_id))
        )
        stats: dict[str, dict[str, int]] = {
            "by_type": {},
            "by_severity": {},
            "by_status": {},
        }
        for finding_type, severity, status, _ in rows.all():
            stats["by_type"][finding_type] = stats["by_type"].get(finding_type, 0) + 1
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        return stats

"""Evidence provenance: trace a file back to its records and forward to the
entities, relationships and findings it supports.

Provenance links flow through the persisted pipeline constructs that were
built during ingestion:

    evidence_file -> source_records --(via RelationshipEvidence)--> relationships
    relationships -> their source/target entities
    findings     -> Finding.evidence_ids (JSONB array; each entry is a *
                    source-record* id, so findings are resolved by joining
                    through the records this file produced)
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import String, cast, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DataSource,
    EvidenceFile,
    Finding,
    Relationship,
    RelationshipEvidence,
    SourceRecord,
)


class ProvenanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scoped_evidence(
        self, case_id: uuid.UUID, evidence_file_id: uuid.UUID
    ) -> EvidenceFile | None:
        evidence = await self._session.get(EvidenceFile, evidence_file_id)
        if evidence is None or str(evidence.case_id) != str(case_id):
            return None
        return evidence

    async def data_source_name(self, data_source_id: str | None) -> str | None:
        if not data_source_id:
            return None
        source = await self._session.get(DataSource, uuid.UUID(data_source_id))
        return source.name if source else None

    async def provenance(
        self, case_id: uuid.UUID, evidence_file_id: uuid.UUID
    ) -> dict[str, Any] | None:
        evidence = await self.get_scoped_evidence(case_id, evidence_file_id)
        if evidence is None:
            return None

        records = await self._session.execute(
            select(SourceRecord)
            .where(SourceRecord.evidence_file_id == str(evidence.id))
            .order_by(SourceRecord.record_no)
        )
        source_records = list(records.scalars())

        record_ids = [record.id for record in source_records]
        relationship_ids: list[str] = []
        if record_ids:
            rel_rows = await self._session.execute(
                select(RelationshipEvidence.relationship_id).where(
                    RelationshipEvidence.source_record_id.in_(record_ids)
                )
            )
            relationship_ids = sorted({str(r) for r in rel_rows.scalars()})

        entity_ids: list[str] = []
        if relationship_ids:
            entity_rows = await self._session.execute(
                select(Relationship.source_entity_id, Relationship.target_entity_id).where(
                    Relationship.id.in_(relationship_ids)
                )
            )
            entity_ids = sorted(
                {
                    str(entity_id)
                    for row in entity_rows.all()
                    for entity_id in (row.source_entity_id, row.target_entity_id)
                }
            )

        finding_ids: list[str] = []
        if record_ids:
            record_id_strs = [str(record) for record in record_ids]
            finding_rows = await self._session.execute(
                select(Finding.id).where(
                    Finding.case_id == str(case_id),
                    Finding.evidence_ids.op("?|")(cast(record_id_strs, ARRAY(String))),
                )
            )
            finding_ids = sorted({str(f) for f in finding_rows.scalars()})

        return {
            "evidence_file_id": evidence.id,
            "record_count": len(source_records),
            "records_by_status": dict(Counter(record.status for record in source_records)),
            "relationship_ids": relationship_ids,
            "entity_ids": entity_ids,
            "finding_ids": finding_ids,
        }

"""Routes: evidence upload, listing and ingestion jobs."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_case_or_404,
    get_evidence_repository,
    get_ingestion_service,
    require_permission,
)
from app.core import rbac
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import DataSource, EvidenceFile, IngestionJob, User
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence import (
    EvidenceCreateResponse,
    EvidenceDetailResponse,
    EvidenceListItem,
    EvidenceListResponse,
    EvidenceProvenanceResponse,
    GraphSyncResult,
    IngestAcceptedResponse,
    IngestJobListResponse,
    IngestJobResponse,
    IngestRequest,
)
from app.services.audit import record_audit
from app.services.ingestion import IngestionService
from app.services.provenance import ProvenanceService
from app.services.validation import (
    UploadValidationError,
    detect_format,
    fingerprint,
    read_upload_with_cap,
)

router = APIRouter(prefix="/cases", tags=["evidence"])


def _safe_stem(filename: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:120]
    return stem or "evidence"


def _to_job_response(job: IngestionJob) -> IngestJobResponse:
    return IngestJobResponse(
        id=job.id,
        case_id=uuid.UUID(str(job.case_id)),
        evidence_file_id=uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None,
        stage=job.stage,
        status=job.status,
        progress=job.progress,
        total_records=job.total_records,
        processed_records=job.processed_records,
        graph_sync_status=job.graph_sync_status,
        error=job.error,
        graph_error=job.graph_error,
        summary=job.summary,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _parse_metadata(raw: str | None) -> dict[str, object] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"metadata must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="metadata must be a JSON object")
    return parsed


def _evidence_to_create_response(evidence: EvidenceFile) -> EvidenceCreateResponse:
    return EvidenceCreateResponse(
        id=evidence.id,
        case_id=uuid.UUID(str(evidence.case_id)),
        original_filename=evidence.original_filename,
        stored_key=evidence.stored_key,
        content_type=evidence.content_type,
        file_size=evidence.file_size,
        sha256=evidence.sha256,
        format=evidence.format,
        encoding=evidence.encoding,
        status=evidence.status,
        status_detail=evidence.status_detail,
        created_at=evidence.created_at,
    )


def _evidence_detail(evidence: EvidenceFile, data_source: str | None) -> EvidenceDetailResponse:
    return EvidenceDetailResponse(
        id=evidence.id,
        case_id=uuid.UUID(str(evidence.case_id)),
        data_source=data_source,
        original_filename=evidence.original_filename,
        stored_key=evidence.stored_key,
        content_type=evidence.content_type,
        file_size=evidence.file_size,
        sha256=evidence.sha256,
        format=evidence.format,
        encoding=evidence.encoding,
        status=evidence.status,
        status_detail=evidence.status_detail,
        record_count=evidence.record_count,
        metadata_json=evidence.metadata_json,
        created_at=evidence.created_at,
    )


@router.post(
    "/{case_id}/evidence",
    response_model=EvidenceCreateResponse,
    status_code=201,
)
async def upload_evidence(
    case_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    data_source: str = Form(default="csv"),
    metadata: str = Form(default=None),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_UPLOAD)),
) -> EvidenceCreateResponse:
    """Store an evidence file, deduplicated by content SHA-256."""
    await get_case_or_404(case_id, request, session)

    try:
        data = await read_upload_with_cap(file, settings.EVIDENCE_MAX_SIZE_BYTES)
    except UploadValidationError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    sha256 = fingerprint(data)
    existing = await evidence_repository.get_by_sha(case_id, sha256)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"duplicate evidence file (sha256 {sha256[:12]}...) already stored",
        )

    try:
        fmt = detect_format(file.filename or "", data)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metadata_json = _parse_metadata(metadata)

    source = await evidence_repository.get_or_create_data_source(data_source or fmt.value)
    object_key = (
        f"cases/{case_id}/evidence/{uuid.uuid4()}/{_safe_stem(file.filename or 'evidence')}"
    )

    storage = request.app.state.storage
    content_type = file.content_type or "application/octet-stream"
    await asyncio.to_thread(storage.upload, object_key, data, content_type)

    try:
        evidence = await evidence_repository.create_evidence_file(
            case_id=case_id,
            data_source_id=source.id,
            original_filename=file.filename or "evidence",
            stored_key=object_key,
            content_type=content_type,
            file_size=len(data),
            sha256=sha256,
            metadata_json=metadata_json,
        )
        await record_audit(
            session,
            actor_id=user.id,
            action="evidence.uploaded",
            resource_type="evidence_file",
            resource_id=evidence.id,
            case_id=case_id,
            metadata={
                "filename": evidence.original_filename,
                "sha256": sha256,
                "format": fmt.value,
            },
        )
        await session.commit()
    except Exception:
        # A03: the object reached the bucket before the row committed (or a
        # concurrent duplicate insert failed on the unique constraint). Remove
        # the orphan so any upload failure leaves no object behind.
        await asyncio.to_thread(storage.delete, object_key)
        raise
    await session.refresh(evidence)
    return _evidence_to_create_response(evidence)


@router.delete(
    "/{case_id}/evidence/{evidence_id}",
    status_code=204,
)
async def delete_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_DELETE)),
) -> None:
    """Delete an evidence file: DB row (cascades source records) then object.

    The row is committed before the object is removed so a failure can never
    leave a referenced-but-missing object; the row is gone in that case, so any
    leftover object is an orphan that reconciliation removes.
    """
    await get_case_or_404(case_id, request, session)
    evidence = await get_evidence_or_404(case_id, evidence_id, evidence_repository)
    key = evidence.stored_key
    await evidence_repository.delete_evidence(evidence_id)
    await record_audit(
        session,
        actor_id=user.id,
        action="evidence.deleted",
        resource_type="evidence_file",
        resource_id=evidence_id,
        case_id=case_id,
        metadata={"filename": evidence.original_filename},
    )
    await session.commit()
    await asyncio.to_thread(request.app.state.storage.delete, key)


async def get_evidence_or_404(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    evidence_repository: EvidenceRepository,
) -> EvidenceFile:
    evidence = await evidence_repository.get_evidence(evidence_id)
    if evidence is None or str(evidence.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"evidence {evidence_id} not found")
    return evidence


@router.get("/{case_id}/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
) -> EvidenceListResponse:
    await get_case_or_404(case_id, request, session)
    items, total = await evidence_repository.list_evidence(case_id, limit=limit, offset=offset)
    return EvidenceListResponse(
        items=[
            EvidenceListItem(
                id=item.id,
                original_filename=item.original_filename,
                sha256=item.sha256,
                format=item.format,
                file_size=item.file_size,
                status=item.status,
                record_count=item.record_count,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence_detail(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
) -> EvidenceDetailResponse:
    """Full metadata for a single evidence file within the case."""
    await get_case_or_404(case_id, request, session)
    evidence = await get_evidence_or_404(case_id, evidence_id, evidence_repository)
    return _evidence_detail(evidence, await _data_source_name(session, evidence.data_source_id))


async def _data_source_name(session: AsyncSession, data_source_id: str | None) -> str | None:
    if not data_source_id:
        return None
    source_id = (
        data_source_id if isinstance(data_source_id, uuid.UUID) else uuid.UUID(data_source_id)
    )
    source = await session.get(DataSource, source_id)
    return source.name if source else None


@router.get(
    "/{case_id}/evidence/{evidence_id}/provenance", response_model=EvidenceProvenanceResponse
)
async def get_evidence_provenance(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceProvenanceResponse:
    """Who/what this evidence supports: records, entities, relationships, findings."""
    await get_case_or_404(case_id, request, session)
    service = ProvenanceService(session)
    evidence = await service.get_scoped_evidence(case_id, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"evidence {evidence_id} not found")
    data = await service.provenance(case_id, evidence_id)
    assert data is not None
    return EvidenceProvenanceResponse(
        evidence=_evidence_detail(
            evidence, await _data_source_name(session, evidence.data_source_id)
        ),
        record_count=int(data["record_count"]),
        records_by_status=dict(data["records_by_status"]),
        entity_count=len(data["entity_ids"]),
        relationship_count=len(data["relationship_ids"]),
        finding_count=len(data["finding_ids"]),
        related_entity_ids=[uuid.UUID(eid) for eid in data["entity_ids"]],
        related_relationship_ids=[uuid.UUID(rid) for rid in data["relationship_ids"]],
        finding_ids=[uuid.UUID(fid) for fid in data["finding_ids"]],
    )


@router.post("/{case_id}/ingest", response_model=IngestAcceptedResponse)
async def create_ingest_job(
    case_id: uuid.UUID,
    payload: IngestRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> IngestAcceptedResponse:
    """Run the full ingestion pipeline for one evidence file.

    Ingestion executes synchronously in this API request (single-worker local
    mode) and is idempotent: PostgreSQL unique constraints make re-running a
    job a no-op, so a retry is always safe.
    """
    await get_case_or_404(case_id, request, session)
    job = await ingestion.ingest(
        case_id=case_id,
        evidence_file_id=payload.evidence_file_id,
        metadata=payload.metadata,
        actor_id=user.id,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="ingestion.job_ran",
        resource_type="ingestion_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"evidence_file_id": str(payload.evidence_file_id), "status": job.status},
    )
    await session.commit()
    return IngestAcceptedResponse(job=_to_job_response(job), duplicate=False)


@router.get("/{case_id}/ingest-jobs", response_model=IngestJobListResponse)
async def list_ingest_jobs(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
) -> IngestJobListResponse:
    await get_case_or_404(case_id, request, session)
    jobs, total = await evidence_repository.list_jobs(case_id, limit=limit, offset=offset)
    return IngestJobListResponse(
        items=[_to_job_response(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{case_id}/ingest/{job_id}/retry-graph-sync",
    response_model=GraphSyncResult,
)
async def retry_graph_sync(
    case_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> GraphSyncResult:
    """Re-run the Neo4j projection for an already-processed job."""
    await get_case_or_404(case_id, request, session)
    try:
        nodes, edges = await ingestion.retry_graph_sync(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    job = await ingestion.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    await record_audit(
        session,
        actor_id=user.id,
        action="ingestion.graph_sync_retried",
        resource_type="ingestion_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"nodes_synced": nodes, "edges_synced": edges},
    )
    await session.commit()
    return GraphSyncResult(
        job_id=job.id,
        graph_sync_status=job.graph_sync_status,
        nodes_synced=nodes,
        edges_synced=edges,
        error=job.graph_error,
    )

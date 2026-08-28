"""Routes: evidence upload, listing and ingestion jobs."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_case_or_404,
    get_evidence_repository,
    get_ingestion_service,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import EvidenceFile, IngestionJob
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence import (
    EvidenceCreateResponse,
    EvidenceListItem,
    EvidenceListResponse,
    GraphSyncResult,
    IngestAcceptedResponse,
    IngestJobListResponse,
    IngestJobResponse,
    IngestRequest,
)
from app.services.ingestion import IngestionService
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
) -> EvidenceCreateResponse:
    """Store an evidence file, deduplicated by content SHA-256."""
    await get_case_or_404(case_id, session)

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
    await session.commit()
    await session.refresh(evidence)
    return _evidence_to_create_response(evidence)


@router.get("/{case_id}/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
) -> EvidenceListResponse:
    await get_case_or_404(case_id, session)
    items = await evidence_repository.list_evidence(case_id)
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
        total=len(items),
    )


@router.post("/{case_id}/ingest", response_model=IngestAcceptedResponse)
async def create_ingest_job(
    case_id: uuid.UUID,
    payload: IngestRequest,
    session: AsyncSession = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> IngestAcceptedResponse:
    """Run the full ingestion pipeline for one evidence file."""
    await get_case_or_404(case_id, session)
    job = await ingestion.ingest(
        case_id=case_id,
        evidence_file_id=payload.evidence_file_id,
        metadata=payload.metadata,
    )
    return IngestAcceptedResponse(job=_to_job_response(job), duplicate=False)


@router.get("/{case_id}/ingest-jobs", response_model=IngestJobListResponse)
async def list_ingest_jobs(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    evidence_repository: EvidenceRepository = Depends(get_evidence_repository),
) -> IngestJobListResponse:
    await get_case_or_404(case_id, session)
    jobs = await evidence_repository.list_jobs(case_id)
    return IngestJobListResponse(
        items=[_to_job_response(job) for job in jobs],
        total=len(jobs),
    )


@router.post(
    "/{case_id}/ingest/{job_id}/retry-graph-sync",
    response_model=GraphSyncResult,
)
async def retry_graph_sync(
    case_id: uuid.UUID,
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> GraphSyncResult:
    """Re-run the Neo4j projection for an already-processed job."""
    await get_case_or_404(case_id, session)
    try:
        nodes, edges = await ingestion.retry_graph_sync(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    job = await ingestion.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return GraphSyncResult(
        job_id=job.id,
        graph_sync_status=job.graph_sync_status,
        nodes_synced=nodes,
        edges_synced=edges,
        error=job.graph_error,
    )

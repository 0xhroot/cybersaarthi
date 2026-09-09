"""Append-only audit trail. Every security-relevant mutation writes a row.

Entries are never edited or deleted by application code (only ``SET NULL`` FK
semantics on cascade/delete). Callers attach the actor id, an action verb of
the form ``resource.verb``, and optional case context plus detail metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | str | None = None,
    case_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist one audit entry and flush it so the surrounding transaction owns it.

    The row is created with ``INSERT`` semantics; the transaction's ``commit()``
    makes it durable together with the mutation it describes.
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        case_id=case_id,
        metadata_=metadata,
    )
    session.add(entry)
    await session.flush()
    return entry

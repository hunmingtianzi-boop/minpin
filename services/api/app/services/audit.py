from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def append_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    trace_id: str | None,
    event_data: dict[str, Any],
    request_ip_hash: str | None = None,
) -> None:
    """Append one tamper-evident audit entry without allowing chain forks."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_key, 0))"),
        {"scope_key": f"{tenant_id}:{company_id}:audit"},
    )
    previous_hash = await session.scalar(
        select(AuditLog.entry_hash)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.company_id == company_id,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    safe_event = json_safe(event_data)
    payload = {
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id else None,
        "trace_id": trace_id,
        "event_data": safe_event,
        "previous_hash": previous_hash,
    }
    entry_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            trace_id=trace_id,
            request_ip_hash=request_ip_hash,
            event_data=safe_event,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            # Supplying the timestamp avoids an INSERT ... RETURNING created_at
            # round-trip. Cross-tenant platform actors may append audit events,
            # but intentionally cannot SELECT the enterprise audit row through
            # RLS, and PostgreSQL applies SELECT policy checks to RETURNING.
            created_at=datetime.now(UTC),
        )
    )


def json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = ["append_audit", "json_safe"]

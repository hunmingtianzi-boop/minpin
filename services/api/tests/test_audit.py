from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

import pytest

from app.db.models import AuditLog
from app.services.audit import append_audit


class _AuditSession:
    def __init__(self) -> None:
        self.added: AuditLog | None = None

    async def execute(self, _statement: Any, _parameters: Any) -> None:
        return None

    async def scalar(self, _statement: Any) -> None:
        return None

    def add(self, row: AuditLog) -> None:
        self.added = row


@pytest.mark.asyncio
async def test_append_audit_supplies_created_at_without_server_returning() -> None:
    session = _AuditSession()

    await append_audit(  # type: ignore[arg-type]
        session,
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        action="platform.onboarding.start",
        resource_type="platform_onboarding_session",
        resource_id=uuid.uuid4(),
        trace_id="trace-id",
        event_data={"provisional": True},
    )

    assert session.added is not None
    assert session.added.created_at.tzinfo is UTC
    assert len(session.added.entry_hash) == 64

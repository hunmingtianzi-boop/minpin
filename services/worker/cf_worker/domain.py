from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClaimedEvent:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    lock_token: uuid.UUID
    event_type: str
    attempt: int


@dataclass(frozen=True, slots=True)
class OutboxRecord(ClaimedEvent):
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    headers: dict[str, Any]
    deduplication_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    recipient_user_id: uuid.UUID
    notification_type: str
    title: str
    body: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ReportIntent:
    result_type: str
    schema_version: int
    status: str
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HandlerResult:
    handler_name: str
    notifications: tuple[NotificationIntent, ...] = ()
    report: ReportIntent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def result_hash(self) -> str:
        payload = {
            "handler_name": self.handler_name,
            "notifications": [
                {
                    "recipient_user_id": str(item.recipient_user_id),
                    "notification_type": item.notification_type,
                    "title": item.title,
                    "body": item.body,
                    "resource_type": item.resource_type,
                    "resource_id": str(item.resource_id) if item.resource_id else None,
                }
                for item in self.notifications
            ],
            "report": (
                {
                    "result_type": self.report.result_type,
                    "schema_version": self.report.schema_version,
                    "status": self.report.status,
                    "report": self.report.report,
                }
                if self.report
                else None
            ),
            "metadata": self.metadata,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class PermanentEventError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvaluationRunner(Protocol):
    async def run(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        tenant_slug: str,
    ) -> dict[str, Any]: ...


class OutboxRepository(Protocol):
    async def claim(self) -> tuple[ClaimedEvent, ...]: ...

    async def load_leased(self, claim: ClaimedEvent) -> OutboxRecord | None: ...

    async def renew_lease(self, event: OutboxRecord) -> bool: ...

    async def tenant_slug(self, event: OutboxRecord) -> str: ...

    async def privacy_recipient(self, event: OutboxRecord) -> uuid.UUID | None: ...

    async def summary_recipient(self, event: OutboxRecord) -> uuid.UUID | None: ...

    async def complete(self, event: OutboxRecord, result: HandlerResult) -> str: ...

    async def fail(self, event: OutboxRecord, *, error_code: str, permanent: bool) -> str: ...


__all__ = [
    "ClaimedEvent",
    "EvaluationRunner",
    "HandlerResult",
    "NotificationIntent",
    "OutboxRecord",
    "OutboxRepository",
    "PermanentEventError",
    "ReportIntent",
]

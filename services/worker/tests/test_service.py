from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from cf_worker.config import WorkerSettings
from cf_worker.domain import ClaimedEvent, HandlerResult, OutboxRecord
from cf_worker.logging import configure_worker_logging
from cf_worker.service import WorkerService


class FakeRepository:
    def __init__(self, record: OutboxRecord) -> None:
        self.record = record
        self.active = True
        self.completed = 0
        self.failed: list[tuple[str, bool]] = []
        self.renewed = 0

    async def claim(self) -> tuple[ClaimedEvent, ...]:
        return (self.record,)

    async def load_leased(self, _claim: ClaimedEvent) -> OutboxRecord | None:
        return self.record if self.active else None

    async def renew_lease(self, _event: OutboxRecord) -> bool:
        self.renewed += 1
        return self.active

    async def complete(self, _event: OutboxRecord, _result: HandlerResult) -> str:
        if not self.active:
            return "stale"
        self.completed += 1
        self.active = False
        return "completed"

    async def fail(self, _event: OutboxRecord, *, error_code: str, permanent: bool) -> str:
        self.failed.append((error_code, permanent))
        self.active = False
        return "dead_letter" if permanent else "retry_scheduled"


class SuccessfulHandlers:
    async def handle(self, _event: OutboxRecord) -> HandlerResult:
        return HandlerResult(handler_name="test-v1")


class FailingHandlers:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def handle(self, _event: OutboxRecord) -> HandlerResult:
        raise self.error


def record(*, payload: dict[str, Any] | None = None) -> OutboxRecord:
    return OutboxRecord(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        event_type="lead.created.v1",
        attempt=1,
        aggregate_type="lead",
        aggregate_id=uuid.uuid4(),
        payload=payload or {},
        headers={},
        deduplication_key=str(uuid.uuid4()),
        created_at=datetime.now(UTC),
    )


def settings() -> WorkerSettings:
    return WorkerSettings(outbox_lease_seconds=60, outbox_heartbeat_seconds=5)


@pytest.mark.asyncio
async def test_duplicate_delivery_is_a_stale_noop_after_atomic_completion() -> None:
    repository = FakeRepository(record())
    service = WorkerService(
        repository=repository,
        handlers=SuccessfulHandlers(),
        settings=settings(),
    )
    claim = repository.record
    assert await service.process(claim) == "completed"
    assert await service.process(claim) == "stale"
    assert repository.completed == 1


@pytest.mark.asyncio
async def test_dispatch_failure_leaves_database_lease_for_recovery() -> None:
    repository = FakeRepository(record())
    service = WorkerService(
        repository=repository,
        handlers=SuccessfulHandlers(),
        settings=settings(),
    )

    def crash(_claim: ClaimedEvent) -> None:
        raise RuntimeError("broker offline")

    assert await service.dispatch_once(crash) == 0
    assert repository.active


@pytest.mark.asyncio
async def test_transient_error_is_scheduled_without_logging_sensitive_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_worker_logging("INFO")
    repository = FakeRepository(record(payload={"email": "person@example.com"}))
    service = WorkerService(
        repository=repository,
        handlers=FailingHandlers(RuntimeError("person@example.com sk-sensitive-token-value")),
        settings=settings(),
    )
    assert await service.process(repository.record) == "retry_scheduled"
    output = capsys.readouterr().out
    assert "person@example.com" not in output
    assert "sk-sensitive-token-value" not in output
    assert repository.failed == [("transient_handler_error", False)]

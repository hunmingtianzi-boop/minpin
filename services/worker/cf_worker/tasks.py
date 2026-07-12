from __future__ import annotations

import asyncio
import uuid

from celery import shared_task
from celery.utils.log import get_task_logger

from cf_worker.config import get_worker_settings
from cf_worker.domain import ClaimedEvent
from cf_worker.evaluation import ApiEvaluationRunner
from cf_worker.handlers import EventHandlerRegistry
from cf_worker.repository import PostgresOutboxRepository
from cf_worker.service import WorkerService

logger = get_task_logger(__name__)


def _service(
    repository: PostgresOutboxRepository,
) -> WorkerService:
    settings = get_worker_settings()
    return WorkerService(
        repository=repository,
        handlers=EventHandlerRegistry(repository, ApiEvaluationRunner(settings)),
        settings=settings,
    )


@shared_task(
    name="cf_worker.poll_outbox",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_outbox() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            service = _service(repository)

            def send(claim: ClaimedEvent) -> None:
                process_outbox_event.apply_async(
                    kwargs={
                        "event_id": str(claim.id),
                        "tenant_id": str(claim.tenant_id),
                        "company_id": str(claim.company_id),
                        "lock_token": str(claim.lock_token),
                        "event_type": claim.event_type,
                        "attempt": claim.attempt,
                    },
                    queue="outbox.process",
                )

            return await service.dispatch_once(send)
        finally:
            await repository.close()

    return asyncio.run(run())


@shared_task(
    name="cf_worker.process_outbox_event",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_outbox_event(
    *,
    event_id: str,
    tenant_id: str,
    company_id: str,
    lock_token: str,
    event_type: str,
    attempt: int,
) -> str:
    claim = ClaimedEvent(
        id=uuid.UUID(event_id),
        tenant_id=uuid.UUID(tenant_id),
        company_id=uuid.UUID(company_id),
        lock_token=uuid.UUID(lock_token),
        event_type=event_type[:160],
        attempt=max(int(attempt), 1),
    )

    async def run() -> str:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            return await _service(repository).process(claim)
        finally:
            await repository.close()

    return asyncio.run(run())


@shared_task(
    name="cf_worker.purge_expired_visitor_profiles",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def purge_expired_visitor_profiles() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            return await repository.purge_expired_visitor_profiles()
        finally:
            await repository.close()

    deleted = asyncio.run(run())
    logger.info("visitor profile retention purge completed", extra={"deleted": deleted})
    return deleted


__all__ = [
    "poll_outbox",
    "process_outbox_event",
    "purge_expired_visitor_profiles",
]

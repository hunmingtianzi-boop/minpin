from __future__ import annotations

import asyncio
from collections.abc import Callable

import structlog

from cf_worker.config import WorkerSettings
from cf_worker.domain import ClaimedEvent, OutboxRecord, OutboxRepository, PermanentEventError
from cf_worker.handlers import EventHandlerRegistry

logger = structlog.get_logger(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        repository: OutboxRepository,
        handlers: EventHandlerRegistry,
        settings: WorkerSettings,
    ) -> None:
        self._repository = repository
        self._handlers = handlers
        self._settings = settings

    async def dispatch_once(self, send: Callable[[ClaimedEvent], None]) -> int:
        claims = await self._repository.claim()
        dispatched = 0
        for claim in claims:
            try:
                send(claim)
            except Exception:
                # The database lease is deliberately left intact. If broker publication
                # failed, the claim becomes eligible again after lease expiry.
                logger.error(
                    "outbox_dispatch_failed",
                    event_id=str(claim.id),
                    event_type=claim.event_type,
                    attempt=claim.attempt,
                    error_code="broker_publish_failed",
                )
                continue
            dispatched += 1
            logger.info(
                "outbox_dispatched",
                event_id=str(claim.id),
                event_type=claim.event_type,
                attempt=claim.attempt,
            )
        return dispatched

    async def process(self, claim: ClaimedEvent) -> str:
        event = await self._repository.load_leased(claim)
        if event is None:
            logger.info(
                "outbox_delivery_stale",
                event_id=str(claim.id),
                event_type=claim.event_type,
                attempt=claim.attempt,
            )
            return "stale"

        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(event, heartbeat_stop),
            name=f"outbox-lease-{event.id}",
        )
        try:
            result = await self._handlers.handle(event)
        except PermanentEventError as exc:
            state = await self._repository.fail(
                event,
                error_code=exc.code,
                permanent=True,
            )
            logger.warning(
                "outbox_delivery_rejected",
                event_id=str(event.id),
                event_type=event.event_type,
                attempt=event.attempt,
                error_code=exc.code,
                state=state,
            )
            return state
        except Exception:
            state = await self._repository.fail(
                event,
                error_code="transient_handler_error",
                permanent=False,
            )
            logger.error(
                "outbox_delivery_failed",
                event_id=str(event.id),
                event_type=event.event_type,
                attempt=event.attempt,
                error_code="transient_handler_error",
                state=state,
            )
            return state
        else:
            state = await self._repository.complete(event, result)
            logger.info(
                "outbox_delivery_completed",
                event_id=str(event.id),
                event_type=event.event_type,
                attempt=event.attempt,
                state=state,
            )
            return state
        finally:
            heartbeat_stop.set()
            await heartbeat

    async def _heartbeat(self, event: OutboxRecord, stop: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self._settings.outbox_heartbeat_seconds,
                )
                return
            except TimeoutError:
                try:
                    renewed = await self._repository.renew_lease(event)
                except Exception:
                    logger.error(
                        "outbox_lease_renewal_failed",
                        event_id=str(event.id),
                        event_type=event.event_type,
                        error_code="lease_renewal_failed",
                    )
                    return
                if not renewed:
                    logger.warning(
                        "outbox_lease_lost",
                        event_id=str(event.id),
                        event_type=event.event_type,
                    )
                    return


__all__ = ["WorkerService"]

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from cf_worker.config import WorkerSettings
from cf_worker.domain import (
    ClaimedEvent,
    HandlerResult,
    NotificationIntent,
    OutboxRecord,
)

_SET_SCOPE_SQL = text(
    """
    SELECT
      set_config('app.tenant_id', :tenant_id, true),
      set_config('app.company_id', :company_id, true),
      set_config('app.card_slug', '', true),
      set_config('app.user_id', '', true),
      set_config('app.session_id', '', true)
    """
)


class PostgresOutboxRepository:
    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
            connect_args={
                "server_settings": {
                    "statement_timeout": "30000",
                    "application_name": "cf-ai-card-worker",
                }
            },
        )

    async def close(self) -> None:
        await self._engine.dispose()

    async def claim(self) -> tuple[ClaimedEvent, ...]:
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT event_id, tenant_id, company_id, lock_token, event_type, attempts
                        FROM app.claim_outbox_events(
                          :worker_id,
                          :batch_size,
                          :lease_seconds
                        )
                        """
                    ),
                    {
                        "worker_id": self._settings.worker_id,
                        "batch_size": self._settings.outbox_batch_size,
                        "lease_seconds": self._settings.outbox_lease_seconds,
                    },
                )
            ).mappings()
            return tuple(
                ClaimedEvent(
                    id=row["event_id"],
                    tenant_id=row["tenant_id"],
                    company_id=row["company_id"],
                    lock_token=row["lock_token"],
                    event_type=row["event_type"],
                    attempt=int(row["attempts"]),
                )
                for row in rows
            )

    async def load_leased(self, claim: ClaimedEvent) -> OutboxRecord | None:
        async with self._engine.begin() as connection:
            await self._set_scope(connection, claim.tenant_id, claim.company_id)
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, tenant_id, company_id, lock_token, event_type, attempts,
                               aggregate_type, aggregate_id, payload, headers,
                               deduplication_key, created_at
                        FROM outbox_events
                        WHERE id = :event_id
                          AND tenant_id = :tenant_id
                          AND company_id = :company_id
                          AND status = 'processing'
                          AND lock_token = :lock_token
                        """
                    ),
                    _claim_parameters(claim),
                )
            ).mappings().one_or_none()
            if row is None:
                return None
            return OutboxRecord(
                id=row["id"],
                tenant_id=row["tenant_id"],
                company_id=row["company_id"],
                lock_token=row["lock_token"],
                event_type=row["event_type"],
                attempt=int(row["attempts"]),
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                payload=dict(row["payload"]),
                headers=dict(row["headers"]),
                deduplication_key=row["deduplication_key"],
                created_at=row["created_at"],
            )

    async def renew_lease(self, event: OutboxRecord) -> bool:
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            result = await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET locked_at = clock_timestamp(),
                        lease_expires_at = clock_timestamp()
                          + make_interval(secs => :lease_seconds)
                    WHERE id = :event_id
                      AND tenant_id = :tenant_id
                      AND company_id = :company_id
                      AND status = 'processing'
                      AND lock_token = :lock_token
                    """
                ),
                {**_event_parameters(event), "lease_seconds": self._settings.outbox_lease_seconds},
            )
            return result.rowcount == 1

    async def tenant_slug(self, event: OutboxRecord) -> str:
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            slug = await connection.scalar(
                text("SELECT slug FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": event.tenant_id},
            )
            if not slug:
                raise RuntimeError("tenant slug unavailable")
            return str(slug)

    async def privacy_recipient(self, event: OutboxRecord) -> uuid.UUID | None:
        request_id = _payload_uuid(event.payload, "privacy_request_id")
        if request_id is None:
            return None
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            existing = await connection.scalar(
                text(
                    """
                    SELECT recipient_user_id
                    FROM notifications
                    WHERE tenant_id = :tenant_id
                      AND company_id = :company_id
                      AND resource_type = 'privacy_request'
                      AND resource_id = :request_id
                    ORDER BY created_at
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": event.tenant_id,
                    "company_id": event.company_id,
                    "request_id": request_id,
                },
            )
            if existing:
                return existing
            recipient = await connection.scalar(
                text(
                    """
                    SELECT card.owner_user_id
                    FROM privacy_requests AS request
                    JOIN cards AS card
                      ON card.tenant_id = request.tenant_id
                     AND card.company_id = request.company_id
                     AND card.id::text = request.evidence ->> 'card_id'
                    WHERE request.id = :request_id
                      AND request.tenant_id = :tenant_id
                      AND request.company_id = :company_id
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": event.tenant_id,
                    "company_id": event.company_id,
                    "request_id": request_id,
                },
            )
            if recipient:
                return recipient
            return await connection.scalar(
                text(
                    """
                    SELECT user_id
                    FROM memberships
                    WHERE tenant_id = :tenant_id
                      AND company_id = :company_id
                      AND role = 'company_admin'
                      AND status = 'active'
                    ORDER BY created_at, id
                    LIMIT 1
                    """
                ),
                {"tenant_id": event.tenant_id, "company_id": event.company_id},
            )

    async def summary_recipient(self, event: OutboxRecord) -> uuid.UUID | None:
        summary_id = _payload_uuid(event.payload, "summary_id")
        if summary_id is None:
            return None
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            return await connection.scalar(
                text(
                    """
                    SELECT card.owner_user_id
                    FROM visit_summaries AS summary
                    JOIN conversations AS conversation
                      ON conversation.id = summary.conversation_id
                     AND conversation.tenant_id = summary.tenant_id
                     AND conversation.company_id = summary.company_id
                    JOIN cards AS card
                      ON card.id = conversation.card_id
                     AND card.tenant_id = conversation.tenant_id
                     AND card.company_id = conversation.company_id
                    WHERE summary.id = :summary_id
                      AND summary.tenant_id = :tenant_id
                      AND summary.company_id = :company_id
                    LIMIT 1
                    """
                ),
                {
                    "summary_id": summary_id,
                    "tenant_id": event.tenant_id,
                    "company_id": event.company_id,
                },
            )

    async def complete(self, event: OutboxRecord, result: HandlerResult) -> str:
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            if not await self._lock_current_lease(connection, event):
                return "stale"
            existing_hash = await connection.scalar(
                text(
                    """
                    SELECT result_hash
                    FROM outbox_deliveries
                    WHERE event_id = :event_id AND handler_name = :handler_name
                    """
                ),
                {"event_id": event.id, "handler_name": result.handler_name},
            )
            if existing_hash is not None:
                await self._mark_published(connection, event)
                return "duplicate"

            for notification in result.notifications:
                await self._insert_notification(connection, event, notification)
            result_hash = result.result_hash()
            if result.report is not None:
                await connection.execute(
                    text(
                        """
                        INSERT INTO worker_job_results (
                          id, tenant_id, company_id, event_id, event_type,
                          result_type, schema_version, status, report, report_hash
                        ) VALUES (
                          :id, :tenant_id, :company_id, :event_id, :event_type,
                          :result_type, :schema_version, :status,
                          CAST(:report AS jsonb), :report_hash
                        )
                        ON CONFLICT (event_id) DO UPDATE
                        SET status = EXCLUDED.status,
                            report = EXCLUDED.report,
                            report_hash = EXCLUDED.report_hash,
                            updated_at = clock_timestamp()
                        """
                    ),
                    {
                        "id": _stable_uuid(event.id, "worker-result"),
                        "tenant_id": event.tenant_id,
                        "company_id": event.company_id,
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "result_type": result.report.result_type,
                        "schema_version": result.report.schema_version,
                        "status": result.report.status,
                        "report": json.dumps(
                            result.report.report,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "report_hash": result_hash,
                    },
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_deliveries (
                      id, tenant_id, company_id, event_id, handler_name, result_hash, completed_at
                    ) VALUES (
                      :id, :tenant_id, :company_id, :event_id,
                      :handler_name, :result_hash, clock_timestamp()
                    )
                    """
                ),
                {
                    "id": _stable_uuid(event.id, result.handler_name),
                    "tenant_id": event.tenant_id,
                    "company_id": event.company_id,
                    "event_id": event.id,
                    "handler_name": result.handler_name,
                    "result_hash": result_hash,
                },
            )
            await self._mark_published(connection, event)
            return "completed"

    async def fail(self, event: OutboxRecord, *, error_code: str, permanent: bool) -> str:
        safe_code = _safe_error_code(error_code)
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT attempts
                        FROM outbox_events
                        WHERE id = :event_id
                          AND tenant_id = :tenant_id
                          AND company_id = :company_id
                          AND status = 'processing'
                          AND lock_token = :lock_token
                        FOR UPDATE
                        """
                    ),
                    _event_parameters(event),
                )
            ).mappings().one_or_none()
            if row is None:
                return "stale"
            attempt = int(row["attempts"])
            dead_letter = should_dead_letter(
                attempt=attempt,
                max_attempts=self._settings.outbox_max_attempts,
                permanent=permanent,
            )
            backoff_seconds = calculate_backoff_seconds(
                attempt=attempt,
                base_seconds=self._settings.outbox_backoff_base_seconds,
                maximum_seconds=self._settings.outbox_backoff_max_seconds,
            )
            await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = :status,
                        available_at = CASE
                          WHEN :dead_letter THEN available_at
                          ELSE clock_timestamp() + make_interval(secs => :backoff_seconds)
                        END,
                        locked_at = NULL,
                        locked_by = NULL,
                        lock_token = NULL,
                        lease_expires_at = NULL,
                        last_error = :last_error
                    WHERE id = :event_id
                      AND tenant_id = :tenant_id
                      AND company_id = :company_id
                      AND lock_token = :lock_token
                    """
                ),
                {
                    **_event_parameters(event),
                    "status": "dead_letter" if dead_letter else "failed",
                    "dead_letter": dead_letter,
                    "backoff_seconds": backoff_seconds,
                    "last_error": safe_code,
                },
            )
            return "dead_letter" if dead_letter else "retry_scheduled"

    async def _insert_notification(
        self,
        connection: AsyncConnection,
        event: OutboxRecord,
        notification: NotificationIntent,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO notifications (
                  id, tenant_id, company_id, recipient_user_id,
                  notification_type, title, body, resource_type, resource_id
                )
                SELECT
                  CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:company_id AS uuid),
                  CAST(:recipient_user_id AS uuid), CAST(:notification_type AS varchar),
                  CAST(:title AS varchar), CAST(:body AS text),
                  CAST(:resource_type AS varchar), CAST(:resource_id AS uuid)
                WHERE NOT EXISTS (
                  SELECT 1 FROM notifications
                  WHERE tenant_id = CAST(:tenant_id AS uuid)
                    AND company_id = CAST(:company_id AS uuid)
                    AND recipient_user_id = CAST(:recipient_user_id AS uuid)
                    AND notification_type = CAST(:notification_type AS varchar)
                    AND resource_type IS NOT DISTINCT FROM CAST(:resource_type AS varchar)
                    AND resource_id IS NOT DISTINCT FROM CAST(:resource_id AS uuid)
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": _stable_uuid(
                    event.id,
                    f"notification:{notification.notification_type}:{notification.recipient_user_id}",
                ),
                "tenant_id": event.tenant_id,
                "company_id": event.company_id,
                "recipient_user_id": notification.recipient_user_id,
                "notification_type": notification.notification_type,
                "title": notification.title,
                "body": notification.body,
                "resource_type": notification.resource_type,
                "resource_id": notification.resource_id,
            },
        )

    async def _lock_current_lease(
        self,
        connection: AsyncConnection,
        event: OutboxRecord,
    ) -> bool:
        event_id = await connection.scalar(
            text(
                """
                SELECT id
                FROM outbox_events
                WHERE id = :event_id
                  AND tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND status = 'processing'
                  AND lock_token = :lock_token
                FOR UPDATE
                """
            ),
            _event_parameters(event),
        )
        return event_id is not None

    async def _mark_published(
        self,
        connection: AsyncConnection,
        event: OutboxRecord,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE outbox_events
                SET status = 'published',
                    published_at = clock_timestamp(),
                    locked_at = NULL,
                    locked_by = NULL,
                    lock_token = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL
                WHERE id = :event_id
                  AND tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND lock_token = :lock_token
                """
            ),
            _event_parameters(event),
        )

    @staticmethod
    async def _set_scope(
        connection: AsyncConnection,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        await connection.execute(
            _SET_SCOPE_SQL,
            {"tenant_id": str(tenant_id), "company_id": str(company_id)},
        )


def _claim_parameters(claim: ClaimedEvent) -> dict[str, uuid.UUID]:
    return {
        "event_id": claim.id,
        "tenant_id": claim.tenant_id,
        "company_id": claim.company_id,
        "lock_token": claim.lock_token,
    }


def _event_parameters(event: OutboxRecord) -> dict[str, uuid.UUID]:
    return _claim_parameters(event)


def _payload_uuid(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _stable_uuid(event_id: uuid.UUID, purpose: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cf-ai-card:{event_id}:{purpose}")


def _safe_error_code(value: str) -> str:
    safe = "".join(character for character in value if character.isalnum() or character in "._-")
    return (safe or "worker_error")[:120]


def calculate_backoff_seconds(*, attempt: int, base_seconds: int, maximum_seconds: int) -> int:
    return min(maximum_seconds, base_seconds * (2 ** max(attempt - 1, 0)))


def should_dead_letter(*, attempt: int, max_attempts: int, permanent: bool) -> bool:
    return permanent or attempt >= max_attempts


__all__ = [
    "PostgresOutboxRepository",
    "calculate_backoff_seconds",
    "should_dead_letter",
]

from __future__ import annotations

import os
import uuid

import pytest
from app.core.config import Settings as ApiSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cf_worker.config import WorkerSettings
from cf_worker.domain import ClaimedEvent, HandlerResult, NotificationIntent
from cf_worker.repository import PostgresOutboxRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_WORKER_INTEGRATION") != "1",
        reason="set RUN_WORKER_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_worker_can_execute_global_profile_retention_purge() -> None:
    repository = PostgresOutboxRepository(WorkerSettings(worker_id="retention-worker"))
    try:
        assert await repository.purge_expired_visitor_profiles() >= 0
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_real_claim_scope_retry_crash_recovery_and_dead_letter() -> None:
    owner = create_async_engine(ApiSettings().migration_database_url, pool_pre_ping=True)
    worker_settings = WorkerSettings(
        outbox_batch_size=1,
        outbox_lease_seconds=30,
        outbox_heartbeat_seconds=5,
        outbox_max_attempts=3,
        outbox_backoff_base_seconds=5,
        outbox_backoff_max_seconds=20,
        worker_id="integration-worker",
    )
    repository = PostgresOutboxRepository(worker_settings)
    event_id = uuid.uuid4()
    try:
        async with owner.begin() as connection:
            scopes = (
                await connection.execute(
                    text(
                        """
                        SELECT tenant_id, id
                        FROM companies
                        ORDER BY created_at, id
                        LIMIT 2
                        """
                    )
                )
            ).all()
            assert len(scopes) == 2
            tenant_id, company_id = scopes[0]
            other_tenant_id, other_company_id = scopes[1]
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                      id, tenant_id, company_id, aggregate_type, aggregate_id,
                      event_type, payload, headers, deduplication_key, status, available_at
                    ) VALUES (
                      :id, :tenant_id, :company_id, 'integration', :aggregate_id,
                      'integration.test.v1', '{}'::jsonb, '{}'::jsonb,
                      :deduplication_key, 'pending', '2000-01-01T00:00:00Z'
                    )
                    """
                ),
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "aggregate_id": uuid.uuid4(),
                    "deduplication_key": f"worker-integration:{event_id}",
                },
            )

        first = (await repository.claim())[0]
        assert first.id == event_id
        assert first.attempt == 1
        assert await repository.load_leased(first) is not None
        wrong_scope = ClaimedEvent(
            id=first.id,
            tenant_id=other_tenant_id,
            company_id=other_company_id,
            lock_token=first.lock_token,
            event_type=first.event_type,
            attempt=first.attempt,
        )
        assert await repository.load_leased(wrong_scope) is None

        loaded = await repository.load_leased(first)
        assert loaded is not None
        assert await repository.fail(
            loaded,
            error_code="integration_transient",
            permanent=False,
        ) == "retry_scheduled"
        async with owner.begin() as connection:
            status, delayed = (
                await connection.execute(
                    text(
                        """
                        SELECT status, available_at > clock_timestamp()
                        FROM outbox_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )
            ).one()
            assert status == "failed"
            assert delayed is True
            await connection.execute(
                text("UPDATE outbox_events SET available_at = '2000-01-01' WHERE id = :id"),
                {"id": event_id},
            )

        second = (await repository.claim())[0]
        assert second.id == event_id
        assert second.attempt == 2
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET locked_at = clock_timestamp() - interval '2 minutes',
                        lease_expires_at = clock_timestamp() - interval '1 minute'
                    WHERE id = :id
                    """
                ),
                {"id": event_id},
            )

        recovered = (await repository.claim())[0]
        assert recovered.id == event_id
        assert recovered.attempt == 3
        assert recovered.lock_token != second.lock_token
        assert await repository.load_leased(second) is None
        recovered_record = await repository.load_leased(recovered)
        assert recovered_record is not None
        assert await repository.fail(
            recovered_record,
            error_code="integration_transient",
            permanent=False,
        ) == "dead_letter"
        async with owner.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT status FROM outbox_events WHERE id = :id"),
                    {"id": event_id},
                )
                == "dead_letter"
            )
    finally:
        async with owner.begin() as connection:
            await connection.execute(
                text("DELETE FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
        await repository.close()
        await owner.dispose()


@pytest.mark.asyncio
async def test_real_completion_ledger_suppresses_duplicate_notification() -> None:
    owner = create_async_engine(ApiSettings().migration_database_url, pool_pre_ping=True)
    settings = WorkerSettings(
        outbox_batch_size=1,
        outbox_lease_seconds=30,
        outbox_heartbeat_seconds=5,
        worker_id="integration-worker",
    )
    repository = PostgresOutboxRepository(settings)
    event_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    recipient_id: uuid.UUID | None = None
    try:
        async with owner.begin() as connection:
            tenant_id, company_id, recipient_id = (
                await connection.execute(
                    text(
                        """
                        SELECT membership.tenant_id, membership.company_id, membership.user_id
                        FROM memberships AS membership
                        WHERE membership.company_id IS NOT NULL
                        ORDER BY membership.created_at, membership.id
                        LIMIT 1
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                      id, tenant_id, company_id, aggregate_type, aggregate_id,
                      event_type, payload, headers, deduplication_key, status, available_at
                    ) VALUES (
                      :id, :tenant_id, :company_id, 'integration', :aggregate_id,
                      'integration.complete.v1', '{}'::jsonb, '{}'::jsonb,
                      :deduplication_key, 'pending', '2000-01-01T00:00:00Z'
                    )
                    """
                ),
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "aggregate_id": resource_id,
                    "deduplication_key": f"worker-complete:{event_id}",
                },
            )
        claim = (await repository.claim())[0]
        leased = await repository.load_leased(claim)
        assert leased is not None
        result = HandlerResult(
            handler_name="integration-handler-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=recipient_id,
                    notification_type="worker_integration",
                    title="Worker integration",
                    body="Static non-PII integration notification.",
                    resource_type="worker_test",
                    resource_id=resource_id,
                ),
            ),
        )
        assert await repository.complete(leased, result) == "completed"

        replacement_token = uuid.uuid4()
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = 'processing', attempts = attempts + 1,
                        locked_at = clock_timestamp(), locked_by = 'duplicate-test',
                        lock_token = :token,
                        lease_expires_at = clock_timestamp() + interval '30 seconds'
                    WHERE id = :id
                    """
                ),
                {"id": event_id, "token": replacement_token},
            )
        duplicate_claim = ClaimedEvent(
            id=event_id,
            tenant_id=tenant_id,
            company_id=company_id,
            lock_token=replacement_token,
            event_type="integration.complete.v1",
            attempt=2,
        )
        duplicate = await repository.load_leased(duplicate_claim)
        assert duplicate is not None
        assert await repository.complete(duplicate, result) == "duplicate"

        async with owner.connect() as connection:
            notification_count = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM notifications
                    WHERE resource_type = 'worker_test' AND resource_id = :resource_id
                    """
                ),
                {"resource_id": resource_id},
            )
            delivery_count = await connection.scalar(
                text("SELECT count(*) FROM outbox_deliveries WHERE event_id = :event_id"),
                {"event_id": event_id},
            )
            assert notification_count == 1
            assert delivery_count == 1
    finally:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM notifications WHERE resource_type = 'worker_test' "
                    "AND resource_id = :resource_id"
                ),
                {"resource_id": resource_id},
            )
            await connection.execute(
                text("DELETE FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
        await repository.close()
        await owner.dispose()

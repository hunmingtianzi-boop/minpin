from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.pii import PiiCipher, PiiCipherError, mask_value
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from cf_worker.config import WorkerSettings
from cf_worker.domain import (
    ClaimedEvent,
    ExportIntent,
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
        self._cipher = PiiCipher.from_settings(settings)
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

    async def build_export(
        self,
        event: OutboxRecord,
        *,
        export_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> ExportIntent:
        async with self._engine.begin() as connection:
            await self._set_scope(connection, event.tenant_id, event.company_id)
            request = (
                await connection.execute(
                    text(
                        """
                        SELECT id, export_type, status, requested_by, requested_role,
                               scope_kind, owner_user_id, include_sensitive
                        FROM data_export_requests
                        WHERE id = :export_id
                          AND tenant_id = :tenant_id
                          AND company_id = :company_id
                        FOR UPDATE
                        """
                    ),
                    {
                        "export_id": export_id,
                        "tenant_id": event.tenant_id,
                        "company_id": event.company_id,
                    },
                )
            ).mappings().one_or_none()
            if request is None:
                raise RuntimeError("export_request_not_found")
            if request["requested_by"] != requested_by:
                raise RuntimeError("export_requester_mismatch")
            if request["include_sensitive"] and request["requested_role"] not in {
                "company_admin",
                "platform_admin",
            }:
                raise RuntimeError("sensitive_export_role_invalid")
            if request["status"] not in {"pending", "processing"}:
                raise RuntimeError("export_request_not_processable")
            await connection.execute(
                text(
                    """
                    UPDATE data_export_requests
                    SET status = 'processing', failure_code = NULL
                    WHERE id = :export_id
                      AND tenant_id = :tenant_id
                      AND company_id = :company_id
                    """
                ),
                {
                    "export_id": export_id,
                    "tenant_id": event.tenant_id,
                    "company_id": event.company_id,
                },
            )
            export_type = str(request["export_type"])
            rows = await self._export_rows(
                connection,
                event=event,
                export_type=export_type,
                scope_kind=str(request["scope_kind"]),
                owner_user_id=request["owner_user_id"],
                include_sensitive=bool(request["include_sensitive"]),
            )
            content = _csv_content(export_type, rows)
            date_part = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            return ExportIntent(
                export_id=export_id,
                file_name=f"{export_type}-{date_part}.csv",
                content_type="text/csv; charset=utf-8",
                content=content,
                row_count=len(rows),
            )

    async def _export_rows(
        self,
        connection: AsyncConnection,
        *,
        event: OutboxRecord,
        export_type: str,
        scope_kind: str,
        owner_user_id: uuid.UUID | None,
        include_sensitive: bool,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "tenant_id": event.tenant_id,
            "company_id": event.company_id,
            "limit": self._settings.export_max_rows + 1,
            "owner_user_id": None,
        }
        if scope_kind == "card_owner":
            if owner_user_id is None or include_sensitive:
                raise RuntimeError("invalid_export_scope")
            params["owner_user_id"] = owner_user_id

        if export_type == "visitors":
            result = await connection.execute(
                text(
                    """
                    SELECT visitor.id, visitor.anonymous_hash, visitor.first_seen_at,
                           visitor.last_seen_at, profile.name_ciphertext,
                           profile.mobile_ciphertext, profile.email_ciphertext,
                           profile.wechat_ciphertext, profile.company_name
                    FROM visitors AS visitor
                    LEFT JOIN visitor_profiles AS profile
                      ON profile.tenant_id = visitor.tenant_id
                     AND profile.company_id = visitor.company_id
                     AND profile.visitor_id = visitor.id
                    WHERE visitor.tenant_id = :tenant_id
                      AND visitor.company_id = :company_id
                      AND EXISTS (
                        SELECT 1 FROM visits AS visit
                        JOIN cards AS card
                          ON card.tenant_id = visit.tenant_id
                         AND card.company_id = visit.company_id
                         AND card.id = visit.card_id
                        WHERE visit.tenant_id = visitor.tenant_id
                          AND visit.company_id = visitor.company_id
                          AND visit.visitor_id = visitor.id
                          AND (
                            :owner_user_id IS NULL
                            OR card.owner_user_id = :owner_user_id
                          )
                      )
                    ORDER BY visitor.first_seen_at, visitor.id
                    LIMIT :limit
                    """
                ),
                params,
            )
        elif export_type == "leads":
            result = await connection.execute(
                text(
                    """
                    SELECT lead.id, lead.status, lead.priority, lead.created_at,
                           lead.updated_at, lead.interest_tags, lead.requirement_ciphertext,
                           card.display_name AS card_name, profile.name_ciphertext,
                           profile.mobile_ciphertext, profile.email_ciphertext,
                           profile.wechat_ciphertext, profile.company_name
                    FROM leads AS lead
                    JOIN cards AS card
                      ON card.tenant_id = lead.tenant_id
                     AND card.company_id = lead.company_id
                     AND card.id = lead.card_id
                    LEFT JOIN visitor_profiles AS profile
                      ON profile.tenant_id = lead.tenant_id
                     AND profile.company_id = lead.company_id
                     AND profile.visitor_id = lead.visitor_id
                    WHERE lead.tenant_id = :tenant_id
                      AND lead.company_id = :company_id
                      AND (
                        :owner_user_id IS NULL
                        OR card.owner_user_id = :owner_user_id
                      )
                    ORDER BY lead.created_at, lead.id
                    LIMIT :limit
                    """
                ),
                params,
            )
        elif export_type == "conversations":
            result = await connection.execute(
                text(
                    """
                    SELECT conversation.id, card.display_name AS card_name,
                           conversation.status, conversation.primary_intent,
                           conversation.risk_level, conversation.started_at,
                           conversation.last_activity_at, message.id AS message_id,
                           message.role, message.status AS message_status,
                           message.content, message.content_redacted, message.created_at
                    FROM conversations AS conversation
                    JOIN cards AS card
                      ON card.tenant_id = conversation.tenant_id
                     AND card.company_id = conversation.company_id
                     AND card.id = conversation.card_id
                    LEFT JOIN messages AS message
                      ON message.tenant_id = conversation.tenant_id
                     AND message.company_id = conversation.company_id
                     AND message.conversation_id = conversation.id
                    WHERE conversation.tenant_id = :tenant_id
                      AND conversation.company_id = :company_id
                      AND (
                        :owner_user_id IS NULL
                        OR card.owner_user_id = :owner_user_id
                      )
                    ORDER BY conversation.started_at, conversation.id,
                             message.created_at, message.id
                    LIMIT :limit
                    """
                ),
                params,
            )
        else:
            raise RuntimeError("unsupported_export_type")
        rows = [dict(row) for row in result.mappings().all()]
        if len(rows) > self._settings.export_max_rows:
            raise RuntimeError("export_row_limit_exceeded")
        return [self._present_export_row(export_type, row, include_sensitive) for row in rows]

    def _present_export_row(
        self,
        export_type: str,
        row: dict[str, Any],
        include_sensitive: bool,
    ) -> dict[str, Any]:
        if export_type == "conversations":
            if not include_sensitive:
                row["content"] = _safe_conversation_content(
                    str(row.get("content") or "")
                )
            return row
        encrypted_fields = {
            "name_ciphertext": "name",
            "mobile_ciphertext": "phone",
            "email_ciphertext": "email",
            "wechat_ciphertext": "wechat",
            "requirement_ciphertext": "generic",
        }
        for field, kind in encrypted_fields.items():
            if field not in row:
                continue
            value = _decrypt_optional(self._cipher, row.pop(field))
            output_name = field.removesuffix("_ciphertext")
            row[output_name] = value if include_sensitive else mask_value(value, kind=kind)
        if "anonymous_hash" in row:
            anonymous_hash = str(row.pop("anonymous_hash") or "")
            row["anonymous_id"] = anonymous_hash[:12]
        return row

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
            if result.export is not None:
                encrypted = self._cipher.encrypt(result.export.content)
                updated = await connection.execute(
                    text(
                        """
                        UPDATE data_export_requests
                        SET status = 'completed',
                            file_name = :file_name,
                            content_type = :content_type,
                            file_ciphertext = :file_ciphertext,
                            file_sha256 = :file_sha256,
                            encryption_key_ref = :encryption_key_ref,
                            row_count = :row_count,
                            completed_at = clock_timestamp(),
                            expires_at = clock_timestamp() + make_interval(hours => :hours),
                            failure_code = NULL
                        WHERE id = :export_id
                          AND tenant_id = :tenant_id
                          AND company_id = :company_id
                          AND outbox_event_id = :event_id
                          AND status = 'processing'
                        """
                    ),
                    {
                        "export_id": result.export.export_id,
                        "tenant_id": event.tenant_id,
                        "company_id": event.company_id,
                        "event_id": event.id,
                        "file_name": result.export.file_name,
                        "content_type": result.export.content_type,
                        "file_ciphertext": encrypted,
                        "file_sha256": result.export.content_sha256(),
                        "encryption_key_ref": self._cipher.key_ref,
                        "row_count": result.export.row_count,
                        "hours": self._settings.export_retention_hours,
                    },
                )
                if updated.rowcount != 1:
                    raise RuntimeError("export_completion_state_invalid")
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
            if event.event_type == "data_export.requested.v1":
                export_id = _payload_uuid(event.payload, "export_id")
                if export_id is not None:
                    await connection.execute(
                        text(
                            """
                            UPDATE data_export_requests
                            SET status = CASE WHEN :dead_letter THEN 'failed' ELSE 'pending' END,
                                failure_code = :failure_code
                            WHERE id = :export_id
                              AND tenant_id = :tenant_id
                              AND company_id = :company_id
                              AND status IN ('pending', 'processing')
                            """
                        ),
                        {
                            "dead_letter": dead_letter,
                            "failure_code": safe_code,
                            "export_id": export_id,
                            "tenant_id": event.tenant_id,
                            "company_id": event.company_id,
                        },
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


def _decrypt_optional(cipher: PiiCipher, value: bytes | None) -> str:
    if value is None:
        return ""
    try:
        return cipher.decrypt(value)
    except PiiCipherError:
        return "[unavailable]"


def _safe_conversation_content(value: str) -> str:
    # Conversation content may contain personal data even after normal input redaction.
    # Replace common contact-shaped tokens before the CSV layer applies formula escaping.
    import re

    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[redacted-phone]", value)
    value = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted-email]",
        value,
    )
    return value


def _csv_content(export_type: str, rows: list[dict[str, Any]]) -> str:
    headers = _EXPORT_HEADERS[export_type]
    buffer = io.StringIO(newline="")
    buffer.write("\ufeff")
    writer = csv.DictWriter(
        buffer,
        fieldnames=headers,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({header: _safe_csv_cell(row.get(header)) for header in headers})
    return buffer.getvalue()


def _safe_csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        rendered = normalized.isoformat()
    elif isinstance(value, (list, tuple)):
        rendered = " | ".join(str(item) for item in value)
    else:
        rendered = str(value)
    if rendered.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + rendered
    return rendered


_EXPORT_HEADERS: dict[str, tuple[str, ...]] = {
    "visitors": (
        "id",
        "anonymous_id",
        "first_seen_at",
        "last_seen_at",
        "name",
        "mobile",
        "email",
        "wechat",
        "company_name",
    ),
    "leads": (
        "id",
        "card_name",
        "status",
        "priority",
        "interest_tags",
        "name",
        "mobile",
        "email",
        "wechat",
        "company_name",
        "requirement",
        "created_at",
        "updated_at",
    ),
    "conversations": (
        "id",
        "card_name",
        "status",
        "primary_intent",
        "risk_level",
        "started_at",
        "last_activity_at",
        "message_id",
        "role",
        "message_status",
        "content",
        "content_redacted",
        "created_at",
    ),
}


def calculate_backoff_seconds(*, attempt: int, base_seconds: int, maximum_seconds: int) -> int:
    return min(maximum_seconds, base_seconds * (2 ** max(attempt - 1, 0)))


def should_dead_letter(*, attempt: int, max_attempts: int, permanent: bool) -> bool:
    return permanent or attempt >= max_attempts


__all__ = [
    "PostgresOutboxRepository",
    "calculate_backoff_seconds",
    "should_dead_letter",
]

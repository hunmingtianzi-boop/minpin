# ruff: noqa: E501
"""Move knowledge import parsing to the worker and support auto publication.

Revision ID: 20260713_0013
Revises: 20260712_0012
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_0013"
down_revision: str | None = "20260712_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

_SOURCE_TYPES = (
    "'pdf','docx','csv','pptx','xlsx','txt','md','html','htm',"
    "'png','jpg','jpeg','webp','tiff','bmp'"
)


def _create_claim_function() -> None:
    op.execute(
        """
        CREATE FUNCTION app.claim_knowledge_import_items(
          worker_name text, batch_limit integer, lease_seconds integer
        ) RETURNS TABLE(
          item_id uuid, tenant_id uuid, company_id uuid, batch_id uuid,
          lock_token uuid, file_name text, source_type text, content_type text,
          row_number integer, auto_publish boolean, payload_ciphertext bytea,
          payload_sha256 text, encryption_key_ref text, attempts integer,
          max_attempts integer, requested_by uuid
        ) LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public, app AS $function$
        BEGIN
          IF worker_name IS NULL OR length(worker_name) = 0
             OR batch_limit < 1 OR batch_limit > 100
             OR lease_seconds < 30 OR lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid knowledge import claim parameters';
          END IF;
          RETURN QUERY
          WITH due AS (
            SELECT item.id FROM public.knowledge_import_items AS item
            WHERE (item.status IN ('pending','failed')
                   OR (item.status = 'processing' AND item.lease_expires_at <= clock_timestamp()))
              AND item.next_attempt_at <= clock_timestamp()
              AND item.attempts < item.max_attempts
            ORDER BY item.created_at, item.id FOR UPDATE SKIP LOCKED LIMIT batch_limit
          ), claimed AS (
            UPDATE public.knowledge_import_items AS item
            SET status='processing', attempts=item.attempts+1, lock_token=gen_random_uuid(),
                locked_by=worker_name,
                lease_expires_at=clock_timestamp()+make_interval(secs => lease_seconds),
                error_code=NULL, parse_status='processing',
                publish_status=CASE WHEN item.auto_publish THEN 'pending' ELSE item.publish_status END
            FROM due WHERE item.id=due.id RETURNING item.*
          )
          SELECT claimed.id, claimed.tenant_id, claimed.company_id, claimed.batch_id,
                 claimed.lock_token, claimed.file_name::text, claimed.source_type::text,
                 claimed.content_type::text, claimed.row_number, claimed.auto_publish,
                 claimed.payload_ciphertext, claimed.payload_sha256::text,
                 claimed.encryption_key_ref::text, claimed.attempts, claimed.max_attempts,
                 batch.requested_by
          FROM claimed JOIN public.knowledge_import_batches AS batch
            ON batch.id = claimed.batch_id;
        END $function$
        """
    )


def _drop_source_type_constraint() -> None:
    """Handle databases created by earlier Alembic/SQLAlchemy naming variants."""
    op.execute(
        """
        DO $drop$ DECLARE target text; BEGIN
          SELECT conname INTO target
          FROM pg_constraint
          WHERE conrelid = 'public.knowledge_import_items'::regclass
            AND contype = 'c' AND pg_get_constraintdef(oid) ILIKE '%source_type%'
          LIMIT 1;
          IF target IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE public.knowledge_import_items DROP CONSTRAINT %I', target
            );
          END IF;
        END $drop$
        """
    )


def upgrade() -> None:
    op.add_column(
        "knowledge_import_batches",
        sa.Column("auto_publish", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "knowledge_import_items",
        sa.Column("auto_publish", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "knowledge_import_items",
        sa.Column("parse_status", sa.String(24), server_default="pending", nullable=False),
    )
    op.add_column("knowledge_import_items", sa.Column("publish_status", sa.String(24)))
    op.add_column("knowledge_import_items", sa.Column("published_at", sa.DateTime(timezone=True)))
    _drop_source_type_constraint()
    op.create_check_constraint(
        "source_type_allowed", "knowledge_import_items", f"source_type IN ({_SOURCE_TYPES})"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_knowledge_import_items(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_knowledge_import_items(text, integer, integer)")
    _create_claim_function()
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_knowledge_import_items(text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION app.claim_knowledge_import_items(text, integer, integer)
              TO cf_ai_card_worker;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_knowledge_import_items(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_knowledge_import_items(text, integer, integer)")
    # Restore the V1 claim signature/function before dropping its new columns.
    op.execute(
        """
        CREATE FUNCTION app.claim_knowledge_import_items(worker_name text, batch_limit integer,
        lease_seconds integer) RETURNS TABLE(item_id uuid, tenant_id uuid, company_id uuid,
        batch_id uuid, lock_token uuid, file_name text, source_type text, content_type text,
        row_number integer, payload_ciphertext bytea, payload_sha256 text,
        encryption_key_ref text, attempts integer, max_attempts integer, requested_by uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, app AS $function$
        BEGIN
          RETURN QUERY WITH due AS (
            SELECT item.id FROM public.knowledge_import_items AS item
            WHERE (item.status IN ('pending','failed') OR (item.status='processing' AND
              item.lease_expires_at <= clock_timestamp())) AND item.next_attempt_at <= clock_timestamp()
              AND item.attempts < item.max_attempts ORDER BY item.created_at, item.id
              FOR UPDATE SKIP LOCKED LIMIT batch_limit
          ), claimed AS (
            UPDATE public.knowledge_import_items AS item SET status='processing',
              attempts=item.attempts+1, lock_token=gen_random_uuid(), locked_by=worker_name,
              lease_expires_at=clock_timestamp()+make_interval(secs => lease_seconds), error_code=NULL
            FROM due WHERE item.id=due.id RETURNING item.*
          ) SELECT claimed.id, claimed.tenant_id, claimed.company_id, claimed.batch_id,
            claimed.lock_token, claimed.file_name::text, claimed.source_type::text,
            claimed.content_type::text, claimed.row_number, claimed.payload_ciphertext,
            claimed.payload_sha256::text, claimed.encryption_key_ref::text, claimed.attempts,
            claimed.max_attempts, batch.requested_by FROM claimed JOIN public.knowledge_import_batches
            AS batch ON batch.id=claimed.batch_id;
        END $function$
        """
    )
    _drop_source_type_constraint()
    op.create_check_constraint(
        "source_type_allowed", "knowledge_import_items", "source_type IN ('pdf','docx','csv')"
    )
    op.drop_column("knowledge_import_items", "published_at")
    op.drop_column("knowledge_import_items", "publish_status")
    op.drop_column("knowledge_import_items", "parse_status")
    op.drop_column("knowledge_import_items", "auto_publish")
    op.drop_column("knowledge_import_batches", "auto_publish")

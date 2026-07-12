"""Add secure asynchronous knowledge imports.

Revision ID: 20260712_0012
Revises: 20260712_0011
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0012"
down_revision: str | None = "20260712_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_import_batches",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("pending_items", sa.Integer(), nullable=False),
        sa.Column("succeeded_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','completed_with_errors',"
            "'failed','dead_letter')",
            name="knowledge_import_batch_status",
        ),
        sa.CheckConstraint("total_items > 0", name="total_items_positive"),
        sa.CheckConstraint(
            "pending_items >= 0 AND succeeded_items >= 0 AND failed_items >= 0",
            name="counts_non_negative",
        ),
        sa.CheckConstraint(
            "pending_items + succeeded_items + failed_items = total_items",
            name="counts_match_total",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_knowledge_import_batches_scope_id"
        ),
    )
    op.create_index(
        "ix_knowledge_import_batches_company_created",
        "knowledge_import_batches",
        ["company_id", "created_at"],
    )
    op.create_table(
        "knowledge_import_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("encryption_key_ref", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="6", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lock_token", sa.Uuid(), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source_type IN ('pdf','docx','csv')", name="source_type_allowed"),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed','dead_letter')",
            name="knowledge_import_item_status",
        ),
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0", name="attempts_valid"),
        sa.CheckConstraint("char_length(payload_sha256) = 64", name="payload_sha256"),
        sa.CheckConstraint(
            "status <> 'processing' OR (lock_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="processing_lease",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "batch_id"],
            [
                "knowledge_import_batches.tenant_id",
                "knowledge_import_batches.company_id",
                "knowledge_import_batches.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_import_items_due",
        "knowledge_import_items",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_knowledge_import_items_batch",
        "knowledge_import_items",
        ["batch_id", "created_at"],
    )
    for table in ("knowledge_import_batches", "knowledge_import_items"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_touch_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope_isolation ON {table} "
            "USING (app.scope_matches(tenant_id, company_id)) "
            "WITH CHECK (app.scope_matches(tenant_id, company_id))"
        )
    op.execute(
        """
        CREATE FUNCTION app.claim_knowledge_import_items(
          worker_name text, batch_limit integer, lease_seconds integer
        ) RETURNS TABLE(
          item_id uuid, tenant_id uuid, company_id uuid, batch_id uuid,
          lock_token uuid, file_name text, source_type text, content_type text,
          row_number integer, payload_ciphertext bytea, payload_sha256 text,
          encryption_key_ref text, attempts integer, max_attempts integer,
          requested_by uuid
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
                error_code=NULL
            FROM due WHERE item.id=due.id RETURNING item.*
          )
          SELECT claimed.id, claimed.tenant_id, claimed.company_id, claimed.batch_id,
                 claimed.lock_token, claimed.file_name::text, claimed.source_type::text,
                 claimed.content_type::text, claimed.row_number, claimed.payload_ciphertext,
                 claimed.payload_sha256::text, claimed.encryption_key_ref::text,
                 claimed.attempts, claimed.max_attempts, batch.requested_by
          FROM claimed JOIN public.knowledge_import_batches AS batch
            ON batch.id = claimed.batch_id;
        END $function$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.claim_knowledge_import_items(text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE
              ON knowledge_import_batches, knowledge_import_items TO cf_ai_card_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION
              app.claim_knowledge_import_items(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.platform_actor_allowed() TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON knowledge_import_batches, knowledge_import_items
              TO cf_ai_card_worker;
            GRANT SELECT, INSERT, UPDATE
              ON knowledge_documents, knowledge_versions, knowledge_chunks
              TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON audit_logs TO cf_ai_card_worker;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.claim_knowledge_import_items(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_knowledge_import_items(text, integer, integer)")
    for table in ("knowledge_import_items", "knowledge_import_batches"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_touch_updated_at ON {table}")
        op.drop_table(table)

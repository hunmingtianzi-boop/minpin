"""Add tenant-scoped scheduled publishing jobs.

Revision ID: 20260712_0011
Revises: 20260711_0010
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0011"
down_revision: str | None = "20260711_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_publish_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("knowledge_version_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_by", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="6", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_token", sa.Uuid(), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resource_type IN ('product', 'case_study', 'knowledge_document')",
            name="scheduled_publish_resource_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'cancelled', "
            "'failed', 'dead_letter')",
            name="scheduled_publish_status",
        ),
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0", name="attempts_valid"),
        sa.CheckConstraint(
            "status <> 'processing' OR (lock_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="processing_lease",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL", name="completed_timestamp"
        ),
        sa.CheckConstraint(
            "resource_type = 'knowledge_document' OR knowledge_version_id IS NULL",
            name="knowledge_version_scope",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["scheduled_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_publish_jobs_due",
        "scheduled_publish_jobs",
        ["status", "next_attempt_at", "scheduled_at"],
    )
    op.create_index(
        "ix_scheduled_publish_jobs_company_created",
        "scheduled_publish_jobs",
        ["company_id", "created_at"],
    )
    op.create_index(
        "uq_scheduled_publish_jobs_active_resource",
        "scheduled_publish_jobs",
        ["tenant_id", "company_id", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing', 'failed')"),
    )
    op.execute(
        "CREATE TRIGGER trg_scheduled_publish_jobs_touch_updated_at "
        "BEFORE UPDATE ON scheduled_publish_jobs FOR EACH ROW "
        "EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute("ALTER TABLE scheduled_publish_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_publish_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY scheduled_publish_jobs_scope_isolation ON scheduled_publish_jobs "
        "USING (app.scope_matches(tenant_id, company_id)) "
        "WITH CHECK (app.scope_matches(tenant_id, company_id))"
    )
    op.execute(
        """
        CREATE FUNCTION app.claim_scheduled_publish_jobs(
          worker_name text,
          batch_limit integer,
          lease_seconds integer
        ) RETURNS TABLE(
          job_id uuid, tenant_id uuid, company_id uuid, lock_token uuid,
          resource_type text, resource_id uuid, target_version integer,
          knowledge_version_id uuid, scheduled_by uuid, attempts integer
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $function$
        BEGIN
          IF worker_name IS NULL OR length(worker_name) = 0
             OR batch_limit < 1 OR batch_limit > 100
             OR lease_seconds < 30 OR lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid scheduled publish claim parameters';
          END IF;
          RETURN QUERY
          WITH due AS (
            SELECT job.id
            FROM public.scheduled_publish_jobs AS job
            WHERE (
                job.status IN ('pending', 'failed')
                OR (job.status = 'processing' AND job.lease_expires_at <= clock_timestamp())
              )
              AND job.scheduled_at <= clock_timestamp()
              AND job.next_attempt_at <= clock_timestamp()
              AND job.attempts < job.max_attempts
            ORDER BY job.scheduled_at, job.id
            FOR UPDATE SKIP LOCKED
            LIMIT batch_limit
          ), claimed AS (
            UPDATE public.scheduled_publish_jobs AS job
            SET status = 'processing', attempts = job.attempts + 1,
                lock_token = gen_random_uuid(), locked_by = worker_name,
                lease_expires_at = clock_timestamp() + make_interval(secs => lease_seconds),
                error_code = NULL, error_detail = NULL, version = job.version + 1
            FROM due WHERE job.id = due.id
            RETURNING job.*
          )
          SELECT claimed.id, claimed.tenant_id, claimed.company_id, claimed.lock_token,
                 claimed.resource_type::text, claimed.resource_id, claimed.target_version,
                 claimed.knowledge_version_id, claimed.scheduled_by, claimed.attempts
          FROM claimed;
        END
        $function$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.claim_scheduled_publish_jobs(text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE ON scheduled_publish_jobs TO cf_ai_card_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION app.claim_scheduled_publish_jobs(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.platform_actor_allowed() TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON scheduled_publish_jobs TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON products, case_studies, knowledge_documents,
              knowledge_versions, knowledge_chunks TO cf_ai_card_worker;
            GRANT SELECT, INSERT, UPDATE ON knowledge_index_jobs TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON audit_logs TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.claim_scheduled_publish_jobs(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_scheduled_publish_jobs(text, integer, integer)")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_scheduled_publish_jobs_touch_updated_at "
        "ON scheduled_publish_jobs"
    )
    op.drop_table("scheduled_publish_jobs")

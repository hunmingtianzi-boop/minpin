"""Add durable worker leases, idempotency ledger and result evidence.

Revision ID: 20260711_0007
Revises: 20260711_0006
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260711_0007"
down_revision: str | None = "20260711_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("locked_by", sa.String(length=128)))
    op.add_column(
        "outbox_events",
        sa.Column("lock_token", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "outbox_events",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        """
        UPDATE outbox_events
        SET status = 'failed',
            locked_at = NULL,
            available_at = now(),
            last_error = 'worker_lease_schema_upgrade'
        WHERE status = 'processing'
        """
    )
    op.create_unique_constraint(
        "uq_outbox_events_scope_id",
        "outbox_events",
        ["tenant_id", "company_id", "id"],
    )
    op.create_check_constraint(
        "ck_outbox_events_processing_lease",
        "outbox_events",
        """
        status <> 'processing' OR (
          locked_at IS NOT NULL
          AND locked_by IS NOT NULL
          AND lock_token IS NOT NULL
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at > locked_at
        )
        """,
    )
    op.create_index(
        "ix_outbox_events_lease_recovery",
        "outbox_events",
        ["status", "lease_expires_at", "available_at", "created_at"],
    )

    op.create_table(
        "outbox_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("handler_name", sa.String(length=160), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            ondelete="CASCADE",
            name="fk_outbox_deliveries_event_scope",
        ),
        sa.UniqueConstraint(
            "event_id",
            "handler_name",
            name="uq_outbox_deliveries_event_handler",
        ),
        sa.CheckConstraint(
            "char_length(result_hash) = 64",
            name="ck_outbox_deliveries_result_hash_sha256",
        ),
    )
    op.create_index(
        "ix_outbox_deliveries_company_completed",
        "outbox_deliveries",
        ["company_id", "completed_at"],
    )

    op.create_table(
        "worker_job_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("result_type", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            ondelete="CASCADE",
            name="fk_worker_job_results_event_scope",
        ),
        sa.UniqueConstraint("event_id", name="uq_worker_job_results_event"),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_worker_job_results_schema_version_positive",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'passed', 'failed_gate')",
            name="ck_worker_job_results_status_allowed",
        ),
        sa.CheckConstraint(
            "char_length(report_hash) = 64",
            name="ck_worker_job_results_report_hash_sha256",
        ),
    )
    op.create_index(
        "ix_worker_job_results_company_created",
        "worker_job_results",
        ["company_id", "created_at"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_worker_job_results_touch_updated_at
        BEFORE UPDATE ON worker_job_results
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )

    for table in ("outbox_deliveries", "worker_job_results"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_scope_isolation ON {table}
            FOR ALL
            USING (app.scope_matches(tenant_id, company_id))
            WITH CHECK (app.scope_matches(tenant_id, company_id))
            """
        )

    op.execute(
        """
        CREATE FUNCTION app.claim_outbox_events(
          p_worker_id text,
          p_batch_size integer,
          p_lease_seconds integer
        ) RETURNS TABLE (
          event_id uuid,
          tenant_id uuid,
          company_id uuid,
          lock_token uuid,
          event_type text,
          attempts integer
        )
        LANGUAGE plpgsql
        VOLATILE
        PARALLEL UNSAFE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        BEGIN
          IF p_worker_id IS NULL
             OR length(btrim(p_worker_id)) NOT BETWEEN 1 AND 128
             OR p_batch_size NOT BETWEEN 1 AND 100
             OR p_lease_seconds NOT BETWEEN 30 AND 3600 THEN
            RAISE EXCEPTION 'invalid outbox claim parameters' USING ERRCODE = '22023';
          END IF;

          RETURN QUERY
          WITH candidates AS (
            SELECT item.id
            FROM public.outbox_events AS item
            WHERE (
              item.status IN ('pending', 'failed')
              AND item.available_at <= clock_timestamp()
            ) OR (
              item.status = 'processing'
              AND item.lease_expires_at <= clock_timestamp()
            )
            ORDER BY
              COALESCE(item.lease_expires_at, item.available_at),
              item.created_at,
              item.id
            FOR UPDATE SKIP LOCKED
            LIMIT p_batch_size
          ), claimed AS (
            UPDATE public.outbox_events AS item
            SET status = 'processing',
                attempts = item.attempts + 1,
                locked_at = clock_timestamp(),
                locked_by = btrim(p_worker_id),
                lock_token = gen_random_uuid(),
                lease_expires_at = clock_timestamp()
                  + make_interval(secs => p_lease_seconds),
                last_error = NULL
            FROM candidates
            WHERE item.id = candidates.id
            RETURNING item.id, item.tenant_id, item.company_id,
                      item.lock_token, item.event_type, item.attempts
          )
          SELECT claimed.id, claimed.tenant_id, claimed.company_id,
                 claimed.lock_token, claimed.event_type::text, claimed.attempts
          FROM claimed;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_outbox_events(text, integer, integer) FROM PUBLIC"
    )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT USAGE ON SCHEMA public, app TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.claim_outbox_events(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON outbox_events TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON outbox_deliveries TO cf_ai_card_worker;
            GRANT SELECT, INSERT, UPDATE ON worker_job_results TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON notifications TO cf_ai_card_worker;
            GRANT SELECT ON tenants, companies, memberships, cards, privacy_requests,
              visit_summaries, conversations, knowledge_documents, knowledge_versions,
              knowledge_chunks, prompt_versions, model_configs
              TO cf_ai_card_worker;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT ON outbox_deliveries, worker_job_results TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_outbox_events(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_outbox_events(text, integer, integer)")
    for table in ("worker_job_results", "outbox_deliveries"):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_isolation ON {table}")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_worker_job_results_touch_updated_at ON worker_job_results"
    )
    op.drop_table("worker_job_results")
    op.drop_table("outbox_deliveries")
    op.drop_index("ix_outbox_events_lease_recovery", table_name="outbox_events")
    op.drop_constraint(
        "ck_outbox_events_processing_lease",
        "outbox_events",
        type_="check",
    )
    op.drop_constraint("uq_outbox_events_scope_id", "outbox_events", type_="unique")
    op.drop_column("outbox_events", "lease_expires_at")
    op.drop_column("outbox_events", "lock_token")
    op.drop_column("outbox_events", "locked_by")

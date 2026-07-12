"""Add tenant-scoped audited asynchronous data exports.

Revision ID: 20260711_0009
Revises: 20260711_0008
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0009"
down_revision: str | None = "20260711_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_export_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_role", sa.String(length=40), nullable=False),
        sa.Column("export_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("scope_kind", sa.String(length=24), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "include_sensitive", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("outbox_event_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("encryption_key_ref", sa.String(length=255), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "export_type IN ('visitors', 'leads', 'conversations')",
            name="data_export_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'expired')",
            name="data_export_status",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('company', 'card_owner')",
            name="scope_kind_allowed",
        ),
        sa.CheckConstraint(
            "scope_kind = 'company' OR owner_user_id IS NOT NULL",
            name="owner_scope_requires_user",
        ),
        sa.CheckConstraint(
            "NOT include_sensitive OR scope_kind = 'company'",
            name="sensitive_requires_company_scope",
        ),
        sa.CheckConstraint(
            "row_count IS NULL OR row_count >= 0",
            name="row_count_non_negative",
        ),
        sa.CheckConstraint(
            "file_sha256 IS NULL OR char_length(file_sha256) = 64",
            name="file_sha256",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND file_ciphertext IS NOT NULL AND file_sha256 IS NOT NULL "
            "AND file_name IS NOT NULL AND row_count IS NOT NULL)",
            name="completed_artifact_required",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "outbox_event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            name="fk_data_export_requests_outbox_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outbox_event_id", name="uq_data_export_requests_outbox_event"),
    )
    op.create_index(
        "ix_data_export_requests_requester_created",
        "data_export_requests",
        ["company_id", "requested_by", "created_at"],
    )
    op.create_index(
        "ix_data_export_requests_expiry",
        "data_export_requests",
        ["status", "expires_at"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_data_export_requests_touch_updated_at
        BEFORE UPDATE ON data_export_requests
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    op.execute("ALTER TABLE data_export_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_export_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY data_export_requests_scope_isolation ON data_export_requests
        USING (app.scope_matches(tenant_id, company_id))
        WITH CHECK (app.scope_matches(tenant_id, company_id))
        """
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE ON data_export_requests TO cf_ai_card_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT SELECT, UPDATE ON data_export_requests TO cf_ai_card_worker;
            GRANT SELECT ON visitors, visitor_profiles, visits, leads, messages,
              cards, conversations TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_data_export_requests_touch_updated_at "
        "ON data_export_requests"
    )
    op.drop_table("data_export_requests")

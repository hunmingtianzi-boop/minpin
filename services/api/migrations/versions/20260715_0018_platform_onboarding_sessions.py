"""Add server-bound document-assisted enterprise onboarding sessions.

Revision ID: 20260715_0018
Revises: 20260715_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0018"
down_revision: str | None = "20260715_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_onboarding_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initial_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_slug", sa.String(length=64), nullable=False),
        sa.Column("tenant_name", sa.String(length=200), nullable=True),
        sa.Column("admin_account", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "import_batch_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "confirmed_enterprise",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["admin_membership_id"], ["memberships.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"], ["staff_credentials.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["initial_card_id"], ["cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_platform_onboarding_tenant"),
        sa.UniqueConstraint("company_id", name="uq_platform_onboarding_company"),
        sa.UniqueConstraint("credential_id", name="uq_platform_onboarding_credential"),
        sa.CheckConstraint(
            "status IN ('draft','processing','review','manual_required',"
            "'ready_to_confirm','confirmed','cancelled','expired','failed')",
            name="status_allowed",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="confirmed_state",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="cancelled_state",
        ),
    )
    op.create_index(
        "ix_platform_onboarding_status_created",
        "platform_onboarding_sessions",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_platform_onboarding_expiry",
        "platform_onboarding_sessions",
        ["expires_at"],
        postgresql_where=sa.text(
            "status NOT IN ('confirmed','cancelled','expired','failed')"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_platform_onboarding_touch_updated_at "
        "BEFORE UPDATE ON platform_onboarding_sessions "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute("REVOKE ALL ON TABLE platform_onboarding_sessions FROM PUBLIC")
    op.execute("ALTER TABLE platform_onboarding_sessions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY platform_onboarding_platform_only "
        "ON platform_onboarding_sessions FOR ALL "
        "USING (app.platform_actor_allowed()) "
        "WITH CHECK (app.platform_actor_allowed())"
    )
    # Cross-tenant UPDATE remains limited to resources bound to one live
    # onboarding session. The service updates these rows before moving the
    # session to a terminal status, so no general platform impersonation path
    # is introduced.
    for table, link_column, resource_column in (
        ("tenants", "tenant_id", "id"),
        ("companies", "company_id", "id"),
        ("users", "admin_user_id", "id"),
        ("memberships", "admin_membership_id", "id"),
        ("staff_credentials", "credential_id", "id"),
        ("cards", "initial_card_id", "id"),
    ):
        scope_predicate = (
            "app.platform_actor_allowed() AND EXISTS ("  # noqa: S608
            "SELECT 1 FROM platform_onboarding_sessions AS onboarding "
            f"WHERE onboarding.{link_column} = {table}.{resource_column} "  # noqa: S608
            "AND onboarding.status IN "
            "('draft','processing','review','manual_required','ready_to_confirm')"
            ")"
        )  # noqa: S608 - fixed migration identifiers only
        op.execute(
            # Fixed migration constants above, never runtime/user input.
            f"CREATE POLICY {table}_platform_onboarding_select ON {table} "  # noqa: S608
            f"FOR SELECT USING ({scope_predicate})"
        )
        op.execute(
            # Fixed migration constants above, never runtime/user input.
            f"CREATE POLICY {table}_platform_onboarding_update ON {table} FOR UPDATE "  # noqa: S608
            f"USING ({scope_predicate}) WITH CHECK (app.platform_actor_allowed())"
        )
    op.execute(
        """
        CREATE FUNCTION app.platform_onboarding_imports_settled(p_session_id uuid)
        RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          result boolean;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          SELECT CASE
            WHEN pg_catalog.cardinality(onboarding.import_batch_ids) = 0 THEN true
            ELSE (
              SELECT pg_catalog.count(*) = pg_catalog.cardinality(
                       onboarding.import_batch_ids
                     )
                     AND pg_catalog.bool_and(
                       batch.status NOT IN ('pending', 'processing')
                     )
              FROM public.knowledge_import_batches AS batch
              WHERE batch.id = ANY(onboarding.import_batch_ids)
                AND batch.tenant_id = onboarding.tenant_id
                AND batch.company_id = onboarding.company_id
            )
          END INTO result
          FROM public.platform_onboarding_sessions AS onboarding
          WHERE onboarding.id = p_session_id;
          RETURN pg_catalog.coalesce(result, false);
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.platform_onboarding_imports_settled(uuid) FROM PUBLIC"
    )
    op.execute(
        """
        CREATE FUNCTION app.platform_onboarding_drafts(p_session_id uuid)
        RETURNS TABLE(
          import_item_id uuid,
          file_name text,
          document_id uuid,
          raw_text text
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          RETURN QUERY
          SELECT
            item.id,
            item.file_name::text,
            item.document_id,
            pg_catalog.left(version.raw_text, 20000)
          FROM public.platform_onboarding_sessions AS onboarding
          JOIN public.knowledge_import_items AS item
            ON item.batch_id = ANY(onboarding.import_batch_ids)
           AND item.tenant_id = onboarding.tenant_id
           AND item.company_id = onboarding.company_id
          JOIN public.knowledge_versions AS version
            ON version.id = item.version_id
           AND version.tenant_id = onboarding.tenant_id
           AND version.company_id = onboarding.company_id
          WHERE onboarding.id = p_session_id
            AND onboarding.status IN
              ('processing','review','manual_required','ready_to_confirm')
            AND item.status = 'completed'
          ORDER BY item.created_at, item.id
          LIMIT 10;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.platform_onboarding_drafts(uuid) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE ON platform_onboarding_sessions
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.platform_onboarding_imports_settled(uuid)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.platform_onboarding_drafts(uuid)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM platform_onboarding_sessions"))
    if int(count or 0) > 0:
        raise RuntimeError(
            "refusing to drop platform_onboarding_sessions while onboarding records exist"
        )
    for table in (
        "cards",
        "staff_credentials",
        "memberships",
        "users",
        "companies",
        "tenants",
    ):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_platform_onboarding_update ON {table}"
        )
        op.execute(
            f"DROP POLICY IF EXISTS {table}_platform_onboarding_select ON {table}"
        )
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_onboarding_drafts(uuid)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_onboarding_imports_settled(uuid)"
    )
    op.execute(
        "DROP POLICY IF EXISTS platform_onboarding_platform_only "
        "ON platform_onboarding_sessions"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_onboarding_touch_updated_at "
        "ON platform_onboarding_sessions"
    )
    op.drop_index("ix_platform_onboarding_expiry", table_name="platform_onboarding_sessions")
    op.drop_index(
        "ix_platform_onboarding_status_created",
        table_name="platform_onboarding_sessions",
    )
    op.drop_table("platform_onboarding_sessions")

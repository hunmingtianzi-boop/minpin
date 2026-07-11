"""Add a unique tenant slug and a constrained platform-onboarding RLS path.

Revision ID: 20260711_0006
Revises: 20260711_0005
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0006"
down_revision: str | None = "20260711_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(length=64), nullable=True))
    op.execute(
        """
        UPDATE tenants
        SET slug = COALESCE(
          NULLIF(settings ->> 'slug', ''),
          NULLIF(settings ->> 'seed_slug', ''),
          'tenant-' || replace(id::text, '-', '')
        )
        WHERE slug IS NULL
        """
    )
    op.alter_column("tenants", "slug", existing_type=sa.String(length=64), nullable=False)
    op.create_check_constraint(
        "ck_tenants_slug_format",
        "tenants",
        "slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'",
    )
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"])

    op.execute(
        """
        CREATE FUNCTION app.platform_actor_allowed() RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          SELECT EXISTS (
            SELECT 1
            FROM public.auth_sessions AS auth
            JOIN public.memberships AS membership
              ON membership.user_id = auth.user_id
             AND membership.tenant_id = auth.tenant_id
             AND membership.company_id IS NOT DISTINCT FROM auth.company_id
            WHERE auth.id = NULLIF(current_setting('app.session_id', true), '')::uuid
              AND auth.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
              AND auth.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
              AND auth.company_id IS NOT DISTINCT FROM
                  NULLIF(current_setting('app.company_id', true), '')::uuid
              AND auth.revoked_at IS NULL
              AND auth.expires_at > now()
              AND membership.role = 'platform_admin'
              AND membership.status = 'active'
          )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.platform_actor_allowed() FROM PUBLIC")

    op.execute(
        "CREATE POLICY tenants_platform_select ON tenants FOR SELECT "
        "USING (app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY tenants_platform_insert ON tenants FOR INSERT "
        "WITH CHECK (app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY companies_platform_select ON companies FOR SELECT "
        "USING (app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY companies_platform_insert ON companies FOR INSERT "
        "WITH CHECK (app.platform_actor_allowed())"
    )
    for table in ("users", "memberships", "cards", "outbox_events", "audit_logs"):
        op.execute(
            f"CREATE POLICY {table}_platform_insert ON {table} FOR INSERT "
            "WITH CHECK (app.platform_actor_allowed())"
        )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION app.platform_actor_allowed() TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    for table in ("users", "memberships", "cards", "outbox_events", "audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_platform_insert ON {table}")
    op.execute("DROP POLICY IF EXISTS companies_platform_insert ON companies")
    op.execute("DROP POLICY IF EXISTS companies_platform_select ON companies")
    op.execute("DROP POLICY IF EXISTS tenants_platform_insert ON tenants")
    op.execute("DROP POLICY IF EXISTS tenants_platform_select ON tenants")
    op.execute("DROP FUNCTION IF EXISTS app.platform_actor_allowed()")
    op.drop_constraint("uq_tenants_slug", "tenants", type_="unique")
    op.drop_constraint("ck_tenants_slug_format", "tenants", type_="check")
    op.drop_column("tenants", "slug")

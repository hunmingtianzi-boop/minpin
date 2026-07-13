"""Add enterprise content distribution and per-card presentation overrides.

Revision ID: 20260713_0014
Revises: 20260713_0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260713_0014"
down_revision = "20260713_0013"
branch_labels = None
depends_on = None


def _scope_policy(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_scope_isolation ON {table} "
        "USING (app.scope_matches(tenant_id, company_id)) "
        "WITH CHECK (app.scope_matches(tenant_id, company_id))"
    )


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "enterprise_content_distributions",
        sa.Column("id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", uuid, nullable=False),
        sa.Column(
            "is_default_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["companies.tenant_id", "companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "resource_type",
            "resource_id",
            name="uq_enterprise_content_distributions_resource",
        ),
        sa.CheckConstraint(
            "resource_type IN ('product', 'case_study', 'knowledge_document')",
            name="enterprise_distribution_resource_type",
        ),
    )
    op.create_index(
        "ix_enterprise_content_distributions_company_resource",
        "enterprise_content_distributions",
        ["company_id", "resource_type", "resource_id"],
    )
    op.create_table(
        "card_content_overrides",
        sa.Column("id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("card_id", uuid, nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", uuid, nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("custom_display", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "card_id",
            "resource_type",
            "resource_id",
            name="uq_card_content_overrides_resource",
        ),
        sa.UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_card_content_overrides_scope_id"
        ),
        sa.CheckConstraint(
            "resource_type IN ('product', 'case_study', 'knowledge_document')",
            name="card_override_resource_type",
        ),
        sa.CheckConstraint("mode IN ('inherit', 'hidden', 'custom')", name="card_override_mode"),
        sa.CheckConstraint(
            "(mode = 'custom') OR custom_display = '{}'::jsonb",
            name="card_override_display_only_custom",
        ),
    )
    op.create_index(
        "ix_card_content_overrides_card_resource",
        "card_content_overrides",
        ["card_id", "resource_type", "resource_id"],
    )
    op.create_table(
        "card_content_override_revisions",
        sa.Column("id", uuid, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("override_id", uuid, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("custom_display", jsonb, nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "override_id"],
            [
                "card_content_overrides.tenant_id",
                "card_content_overrides.company_id",
                "card_content_overrides.id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("override_id", "version", name="uq_card_content_override_revision"),
        sa.CheckConstraint(
            "mode IN ('inherit', 'hidden', 'custom')", name="card_override_revision_mode"
        ),
    )
    op.create_index(
        "ix_card_content_override_revisions_override",
        "card_content_override_revisions",
        ["override_id", "version"],
    )
    for table in (
        "enterprise_content_distributions",
        "card_content_overrides",
        "card_content_override_revisions",
    ):
        if table != "card_content_override_revisions":
            trigger = (
                f"CREATE TRIGGER {table}_touch_updated_at BEFORE UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
            )
            op.execute(trigger)
        _scope_policy(table)

    # New tables are created after the baseline "all tables" application-role
    # grant.  Keep the application role able to resolve public catalog/RAG
    # visibility and administer policy records; RLS remains the authorization
    # boundary for every statement.
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON enterprise_content_distributions, card_content_overrides,
                 card_content_override_revisions
              TO cf_ai_card_app;
          END IF;
        END $grant$;
        """
    )


def downgrade() -> None:
    for table in (
        "card_content_override_revisions",
        "card_content_overrides",
        "enterprise_content_distributions",
    ):
        op.drop_table(table)

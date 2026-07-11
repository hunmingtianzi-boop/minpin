"""Add the unscoped staff login credential boundary.

Revision ID: 20260711_0003
Revises: 20260710_0002
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260711_0003"
down_revision: str | None = "20260710_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_normalized", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "failed_attempts",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "account_normalized = lower(btrim(account_normalized)) "
            "AND char_length(account_normalized) BETWEEN 3 AND 200",
            name="ck_staff_credentials_account_normalized",
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0",
            name="ck_staff_credentials_failed_attempts_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            name="fk_staff_credentials_company_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name="fk_staff_credentials_membership",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_staff_credentials_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_staff_credentials_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_staff_credentials"),
        sa.UniqueConstraint(
            "account_normalized",
            name="uq_staff_credentials_account",
        ),
        sa.UniqueConstraint(
            "membership_id",
            name="uq_staff_credentials_membership",
        ),
    )
    op.create_index(
        "ix_staff_credentials_scope",
        "staff_credentials",
        ["tenant_id", "company_id", "user_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE TRIGGER trg_staff_credentials_touch_updated_at
        BEFORE UPDATE ON staff_credentials
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    # This table intentionally has no RLS: login resolves the trusted scope here,
    # verifies scrypt, then installs that exact scope before touching memberships.
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON TABLE staff_credentials TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_staff_credentials_touch_updated_at ON staff_credentials")
    op.drop_index("ix_staff_credentials_scope", table_name="staff_credentials")
    op.drop_table("staff_credentials")

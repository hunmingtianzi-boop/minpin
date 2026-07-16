"""Persist sourced onboarding business profiles for platform review.

Revision ID: 20260715_0020
Revises: 20260715_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0020"
down_revision: str | None = "20260715_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column(
            "business_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_onboarding_sessions", "business_profile")

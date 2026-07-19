"""Add platform-owned LLM behavior controls.

Revision ID: 20260717_0023
Revises: 20260717_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0023"
down_revision: str | None = "20260717_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_llm_profiles",
        sa.Column(
            "allow_general_answers",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "platform_llm_profiles",
        sa.Column(
            "faq_fast_path_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_llm_profiles", "faq_fast_path_enabled")
    op.drop_column("platform_llm_profiles", "allow_general_answers")

"""Allow auditable AI runs for summaries and other non-message resources.

Revision ID: 20260711_0005
Revises: 20260711_0004
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260711_0005"
down_revision: str | None = "20260711_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("ai_runs", "message_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column(
        "ai_runs",
        sa.Column(
            "purpose",
            sa.String(length=80),
            server_default=sa.text("'rag_answer'"),
            nullable=False,
        ),
    )
    op.add_column("ai_runs", sa.Column("resource_type", sa.String(length=80), nullable=True))
    op.add_column(
        "ai_runs",
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_runs_source_reference_required",
        "ai_runs",
        "message_id IS NOT NULL OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
    )
    op.create_index(
        "ix_ai_runs_resource",
        "ai_runs",
        ["company_id", "resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_runs_resource", table_name="ai_runs")
    op.drop_constraint("ck_ai_runs_source_reference_required", "ai_runs", type_="check")
    op.execute("DELETE FROM ai_runs WHERE message_id IS NULL")
    op.drop_column("ai_runs", "resource_id")
    op.drop_column("ai_runs", "resource_type")
    op.drop_column("ai_runs", "purpose")
    op.alter_column("ai_runs", "message_id", existing_type=postgresql.UUID(), nullable=False)

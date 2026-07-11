"""Align legacy generated constraint names with the model contract.

Revision ID: 20260711_0008
Revises: 20260711_0007
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260711_0008"
down_revision: str | None = "20260711_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RENAMES = (
    ("ai_runs", "ai_runs_message_id_key", "uq_ai_runs_message_id"),
    (
        "auth_sessions",
        "auth_sessions_refresh_token_hash_key",
        "uq_auth_sessions_refresh_token_hash",
    ),
    (
        "visitor_profiles",
        "visitor_profiles_visitor_id_key",
        "uq_visitor_profiles_visitor_id",
    ),
)


def upgrade() -> None:
    for table_name, old_name, new_name in _RENAMES:
        op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')


def downgrade() -> None:
    for table_name, old_name, new_name in reversed(_RENAMES):
        op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{new_name}" TO "{old_name}"')

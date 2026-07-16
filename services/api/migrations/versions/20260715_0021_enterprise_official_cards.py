"""Separate enterprise official cards from employee cards.

Revision ID: 20260715_0021
Revises: 20260715_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0021"
down_revision: str | None = "20260715_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cards",
        sa.Column(
            "card_kind",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'employee'"),
        ),
    )
    op.add_column(
        "cards",
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
    )
    op.execute("UPDATE cards SET responsible_user_id = owner_user_id")
    op.alter_column("cards", "responsible_user_id", nullable=False)
    op.create_foreign_key(
        "fk_cards_responsible_user_id_users",
        "cards",
        "users",
        ["responsible_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("cards", "owner_user_id", nullable=True)
    op.create_check_constraint(
        "ck_cards_card_kind",
        "cards",
        "card_kind IN ('enterprise', 'employee')",
    )
    op.create_check_constraint(
        "ck_cards_kind_owner_consistent",
        "cards",
        "(card_kind = 'enterprise' AND owner_user_id IS NULL) OR "
        "(card_kind = 'employee' AND owner_user_id IS NOT NULL "
        "AND responsible_user_id = owner_user_id)",
    )
    op.create_index(
        "ix_cards_company_kind_status_updated",
        "cards",
        ["company_id", "card_kind", "status", "updated_at"],
    )
    # Existing document-assisted onboarding cards already represent the
    # enterprise itself. Promote only those server-bound rows; every other
    # existing card remains an employee card conservatively.
    op.execute(
        "UPDATE cards AS card SET card_kind = 'enterprise', owner_user_id = NULL "
        "FROM platform_onboarding_sessions AS onboarding "
        "WHERE onboarding.initial_card_id = card.id"
    )


def downgrade() -> None:
    unbound_enterprise_cards = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM cards AS card "
            "WHERE card.card_kind = 'enterprise' AND NOT EXISTS ("
            "SELECT 1 FROM platform_onboarding_sessions AS onboarding "
            "WHERE onboarding.initial_card_id = card.id)"
        )
    )
    if int(unbound_enterprise_cards or 0) > 0:
        raise RuntimeError(
            "refusing to remove enterprise card types while independently created "
            "enterprise cards exist"
        )
    op.execute(
        "UPDATE cards AS card SET card_kind = 'employee', "
        "owner_user_id = onboarding.admin_user_id, "
        "responsible_user_id = onboarding.admin_user_id "
        "FROM platform_onboarding_sessions AS onboarding "
        "WHERE onboarding.initial_card_id = card.id"
    )
    null_owner_count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM cards WHERE owner_user_id IS NULL")
    )
    if int(null_owner_count or 0) > 0:
        raise RuntimeError("refusing downgrade because cards without owners remain")
    op.drop_index("ix_cards_company_kind_status_updated", table_name="cards")
    op.drop_constraint("ck_cards_kind_owner_consistent", "cards", type_="check")
    op.drop_constraint("ck_cards_card_kind", "cards", type_="check")
    op.alter_column("cards", "owner_user_id", nullable=False)
    op.drop_constraint(
        "fk_cards_responsible_user_id_users", "cards", type_="foreignkey"
    )
    op.drop_column("cards", "responsible_user_id")
    op.drop_column("cards", "card_kind")

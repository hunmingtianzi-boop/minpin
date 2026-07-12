"""Add consent-gated long-lived visitor profile signals.

Revision ID: 20260711_0010
Revises: 20260711_0009
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0010"
down_revision: str | None = "20260711_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE consent_records DROP CONSTRAINT ck_consent_records_scope")
    op.create_check_constraint(
        op.f("ck_consent_records_consent_scope"),
        "consent_records",
        "scope IN ('browse_notice', 'chat_notice', 'lead_contact', 'profile_personalization')",
    )
    op.create_unique_constraint(
        "uq_visit_summaries_scope_id", "visit_summaries", ["tenant_id", "company_id", "id"]
    )
    op.create_unique_constraint(
        "uq_consent_records_scope_id",
        "consent_records",
        ["tenant_id", "company_id", "id"],
    )
    op.add_column(
        "visit_summaries", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("visit_summaries", sa.Column("approved_by", sa.Uuid(), nullable=True))
    op.create_table(
        "visitor_profile_signals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("visitor_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("label_hmac", sa.String(length=64), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encryption_key_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('interest', 'intent')", name="visitor_profile_signal_kind"),
        sa.CheckConstraint("strength >= 0 AND strength <= 1", name="strength_range"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        sa.CheckConstraint("char_length(label_hmac) = 64", name="label_hmac_sha256"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            name="fk_visitor_profile_signals_visitor",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_visitor_profile_signals_scope_id"
        ),
        sa.UniqueConstraint(
            "visitor_id", "kind", "label_hmac", name="uq_visitor_profile_signals_identity"
        ),
    )
    op.create_index(
        "ix_visitor_profile_signals_visitor_last_seen",
        "visitor_profile_signals",
        ["visitor_id", "last_seen_at"],
    )
    op.create_index(
        "ix_visitor_profile_signals_retention",
        "visitor_profile_signals",
        ["retention_expires_at"],
    )
    op.create_table(
        "visitor_profile_signal_sources",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("consent_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("summary_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("contribution >= 0 AND contribution <= 1", name="contribution_range"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="source_confidence_range"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "signal_id"],
            [
                "visitor_profile_signals.tenant_id",
                "visitor_profile_signals.company_id",
                "visitor_profile_signals.id",
            ],
            name="fk_profile_signal_sources_signal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "consent_id"],
            ["consent_records.tenant_id", "consent_records.company_id", "consent_records.id"],
            name="fk_profile_signal_sources_consent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            name="fk_profile_signal_sources_visit",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            name="fk_profile_signal_sources_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "summary_id"],
            ["visit_summaries.tenant_id", "visit_summaries.company_id", "visit_summaries.id"],
            name="fk_profile_signal_sources_summary",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            name="fk_profile_signal_sources_message",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signal_id", "summary_id", "message_id", name="uq_profile_signal_source_evidence"
        ),
    )
    op.create_index(
        "ix_profile_signal_sources_signal_observed",
        "visitor_profile_signal_sources",
        ["signal_id", "observed_at"],
    )
    for table_name in ("visitor_profile_signals", "visitor_profile_signal_sources"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table_name}_scope_isolation ON {table_name} "
            "FOR ALL USING (app.scope_matches(tenant_id, company_id)) "
            "WITH CHECK (app.scope_matches(tenant_id, company_id))"
        )
    op.execute(
        """
        CREATE TRIGGER trg_visitor_profile_signals_touch_updated_at
        BEFORE UPDATE ON visitor_profile_signals
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.purge_expired_visitor_profiles()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $function$
        DECLARE deleted_count integer := 0;
        BEGIN
          DELETE FROM public.visitor_profile_signal_sources
          WHERE retention_expires_at <= clock_timestamp();
          GET DIAGNOSTICS deleted_count = ROW_COUNT;
          DELETE FROM public.visitor_profile_signals AS signal
          WHERE NOT EXISTS (
              SELECT 1 FROM public.visitor_profile_signal_sources AS source
              WHERE source.tenant_id = signal.tenant_id
                AND source.company_id = signal.company_id
                AND source.signal_id = signal.id
            );
          UPDATE public.visitor_profile_signals AS signal
          SET evidence_count = aggregate.evidence_count,
              strength = aggregate.strength,
              confidence = aggregate.confidence,
              first_seen_at = aggregate.first_seen_at,
              last_seen_at = aggregate.last_seen_at,
              retention_expires_at = aggregate.retention_expires_at
          FROM (
            SELECT signal_id, count(*)::integer AS evidence_count,
              max(contribution) AS strength, max(confidence) AS confidence,
              min(observed_at) AS first_seen_at, max(observed_at) AS last_seen_at,
              max(retention_expires_at) AS retention_expires_at
            FROM public.visitor_profile_signal_sources
            GROUP BY signal_id
          ) AS aggregate
          WHERE signal.id = aggregate.signal_id;
          RETURN deleted_count;
        END
        $function$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.purge_expired_visitor_profiles() FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON visitor_profile_signals
              TO cf_ai_card_app;
            GRANT SELECT, INSERT ON visitor_profile_signal_sources TO cf_ai_card_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION app.purge_expired_visitor_profiles()
              TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION app.purge_expired_visitor_profiles() FROM PUBLIC"
    )
    op.execute("DROP FUNCTION IF EXISTS app.purge_expired_visitor_profiles()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_visitor_profile_signals_touch_updated_at "
        "ON visitor_profile_signals"
    )
    op.drop_table("visitor_profile_signal_sources")
    op.drop_table("visitor_profile_signals")
    op.drop_column("visit_summaries", "approved_by")
    op.drop_column("visit_summaries", "approved_at")
    op.drop_constraint("uq_consent_records_scope_id", "consent_records", type_="unique")
    op.drop_constraint("uq_visit_summaries_scope_id", "visit_summaries", type_="unique")
    op.execute("ALTER TABLE consent_records DROP CONSTRAINT ck_consent_records_consent_scope")
    # This scope did not exist before 0010 and cannot survive the old check.
    op.execute("DELETE FROM consent_records WHERE scope = 'profile_personalization'")
    op.execute(
        "ALTER TABLE consent_records ADD CONSTRAINT ck_consent_records_scope "
        "CHECK (scope IN ('browse_notice', 'chat_notice', 'lead_contact'))"
    )

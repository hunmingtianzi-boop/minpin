"""Add final multi-profile platform Chat configuration.

Revision ID: 20260715_0016
Revises: 20260715_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0016"
down_revision: str | None = "20260715_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_llm_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'chat_main'"),
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.String(length=2_048), nullable=False),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_key_ref", sa.String(length=128), nullable=True),
        sa.Column("api_key_hint", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column(
            "thinking",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'disabled'"),
        ),
        sa.Column(
            "reasoning_effort",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "timeout_seconds",
            sa.Numeric(precision=6, scale=2),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "max_retries",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "max_concurrency",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("20"),
        ),
        sa.Column(
            "max_output_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1000"),
        ),
        sa.Column(
            "temperature",
            sa.Numeric(precision=4, scale=3),
            nullable=False,
            server_default=sa.text("0.1"),
        ),
        sa.Column(
            "daily_budget_cny",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "input_price_cny_per_million",
            sa.Numeric(precision=14, scale=6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_price_cny_per_million",
            sa.Numeric(precision=14, scale=6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "last_test_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'untested'"),
        ),
        sa.Column("last_test_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint("purpose = 'chat_main'", name="purpose_allowed"),
        sa.CheckConstraint(
            "btrim(provider) <> ''",
            name="provider_not_blank",
        ),
        sa.CheckConstraint(
            "btrim(base_url) <> ''",
            name="base_url_not_blank",
        ),
        sa.CheckConstraint("btrim(model) <> ''", name="model_not_blank"),
        sa.CheckConstraint(
            "thinking IN ('enabled', 'disabled')",
            name="thinking_allowed",
        ),
        sa.CheckConstraint(
            "reasoning_effort IS NULL OR reasoning_effort IN ('high', 'max')",
            name="reasoning_effort_allowed",
        ),
        sa.CheckConstraint(
            "timeout_seconds >= 2 AND timeout_seconds <= 120",
            name="timeout_seconds_range",
        ),
        sa.CheckConstraint(
            "max_retries >= 0 AND max_retries <= 5",
            name="max_retries_range",
        ),
        sa.CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 500",
            name="max_concurrency_range",
        ),
        sa.CheckConstraint(
            "max_output_tokens >= 128 AND max_output_tokens <= 8192",
            name="max_output_tokens_range",
        ),
        sa.CheckConstraint(
            "temperature >= 0 AND temperature <= 2",
            name="temperature_range",
        ),
        sa.CheckConstraint(
            "thinking = 'disabled' OR temperature = 0.1",
            name="thinking_temperature_neutral",
        ),
        sa.CheckConstraint(
            "daily_budget_cny >= 0",
            name="daily_budget_non_negative",
        ),
        sa.CheckConstraint(
            "input_price_cny_per_million >= 0",
            name="input_price_non_negative",
        ),
        sa.CheckConstraint(
            "output_price_cny_per_million >= 0",
            name="output_price_non_negative",
        ),
        sa.CheckConstraint(
            "last_test_status IN ('untested', 'succeeded', 'failed')",
            name="last_test_status_allowed",
        ),
        sa.CheckConstraint(
            "(last_test_status = 'untested' AND last_test_latency_ms IS NULL "
            "AND last_tested_at IS NULL) OR "
            "(last_test_status IN ('succeeded', 'failed') "
            "AND last_test_latency_ms >= 0 AND last_tested_at IS NOT NULL)",
            name="last_test_state_consistent",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint(
            "(api_key_ciphertext IS NULL AND api_key_key_ref IS NULL AND api_key_hint IS NULL) "
            "OR (api_key_ciphertext IS NOT NULL AND api_key_key_ref IS NOT NULL "
            "AND api_key_hint IS NOT NULL)",
            name="api_key_state",
        ),
    )
    op.create_index(
        "uq_platform_llm_profiles_name_normalized",
        "platform_llm_profiles",
        [sa.text("lower(btrim(name))")],
        unique=True,
    )
    op.create_index(
        "uq_platform_llm_profiles_one_active",
        "platform_llm_profiles",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.execute(
        "CREATE TRIGGER trg_platform_llm_profiles_touch_updated_at "
        "BEFORE UPDATE ON platform_llm_profiles "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute(
        """
        CREATE FUNCTION app.enforce_platform_llm_profile_active() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          profile_count integer;
          active_count integer;
        BEGIN
          SELECT count(*), count(*) FILTER (WHERE is_active)
          INTO profile_count, active_count
          FROM public.platform_llm_profiles;
          IF profile_count > 0 AND active_count <> 1 THEN
            RAISE EXCEPTION 'platform LLM profiles require exactly one active row'
              USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_platform_llm_profiles_exactly_one_active
        AFTER INSERT OR UPDATE OR DELETE ON platform_llm_profiles
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION app.enforce_platform_llm_profile_active()
        """
    )

    op.execute("REVOKE ALL ON TABLE platform_llm_profiles FROM PUBLIC")
    op.execute("ALTER TABLE platform_llm_profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY platform_llm_profiles_runtime_select "
        "ON platform_llm_profiles FOR SELECT USING (true)"
    )
    op.execute(
        "CREATE POLICY platform_llm_profiles_platform_insert "
        "ON platform_llm_profiles FOR INSERT "
        "WITH CHECK (app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY platform_llm_profiles_platform_update "
        "ON platform_llm_profiles FOR UPDATE "
        "USING (app.platform_actor_allowed()) "
        "WITH CHECK (app.platform_actor_allowed())"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE ON platform_llm_profiles TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    profile_count = op.get_bind().scalar(sa.text("SELECT count(*) FROM platform_llm_profiles"))
    if int(profile_count or 0) > 0:
        raise RuntimeError(
            "refusing to drop platform_llm_profiles while encrypted profiles exist"
        )
    op.execute(
        "DROP POLICY IF EXISTS platform_llm_profiles_platform_update "
        "ON platform_llm_profiles"
    )
    op.execute(
        "DROP POLICY IF EXISTS platform_llm_profiles_platform_insert "
        "ON platform_llm_profiles"
    )
    op.execute(
        "DROP POLICY IF EXISTS platform_llm_profiles_runtime_select "
        "ON platform_llm_profiles"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_llm_profiles_exactly_one_active "
        "ON platform_llm_profiles"
    )
    op.execute("DROP FUNCTION IF EXISTS app.enforce_platform_llm_profile_active()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_llm_profiles_touch_updated_at "
        "ON platform_llm_profiles"
    )
    op.drop_index("uq_platform_llm_profiles_one_active", table_name="platform_llm_profiles")
    op.drop_index(
        "uq_platform_llm_profiles_name_normalized",
        table_name="platform_llm_profiles",
    )
    op.drop_table("platform_llm_profiles")

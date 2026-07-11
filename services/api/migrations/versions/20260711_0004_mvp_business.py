"""Add the V1.0 business workflow tables.

Revision ID: 20260711_0004
Revises: 20260711_0003
Create Date: 2026-07-11

This revision is intentionally additive.  It does not rewrite constraints or
indexes created by the database-core revisions.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260711_0004"
down_revision: str | None = "20260711_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCOPED_TABLES = (
    "products",
    "case_studies",
    "forbidden_topics",
    "card_contact_fields",
    "privacy_requests",
    "leads",
    "lead_followups",
    "notifications",
)

TOUCH_TABLES = (
    "products",
    "case_studies",
    "forbidden_topics",
    "card_contact_fields",
    "privacy_requests",
    "leads",
)


def _execute_batch(sql: str) -> None:
    """Execute simple DDL statements separately for asyncpg compatibility."""

    for statement in sql.split(";"):
        if stripped := statement.strip():
            op.execute(stripped)


def upgrade() -> None:
    op.execute("ALTER TABLE visitor_profiles ADD COLUMN demand_ciphertext bytea NULL")

    _execute_batch(
        """
        CREATE TABLE security_events (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          event_type varchar(80) NOT NULL,
          outcome varchar(24) NOT NULL,
          account_hash varchar(64),
          request_ip_hash varchar(64),
          user_id uuid,
          membership_id uuid,
          tenant_id uuid,
          company_id uuid,
          session_id uuid,
          reason_code varchar(80),
          event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
          occurred_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_security_events_outcome_allowed
            CHECK (outcome IN ('succeeded', 'failed', 'blocked')),
          CONSTRAINT ck_security_events_account_hash
            CHECK (account_hash IS NULL OR char_length(account_hash) = 64),
          CONSTRAINT ck_security_events_ip_hash
            CHECK (request_ip_hash IS NULL OR char_length(request_ip_hash) = 64)
        );
        CREATE INDEX ix_security_events_type_occurred
          ON security_events (event_type, occurred_at);
        CREATE INDEX ix_security_events_account_occurred
          ON security_events (account_hash, occurred_at);
        CREATE INDEX ix_security_events_ip_occurred
          ON security_events (request_ip_hash, occurred_at);
        """
    )

    _execute_batch(
        """
        CREATE TABLE products (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          slug varchar(96) NOT NULL,
          name varchar(200) NOT NULL,
          category varchar(120),
          summary text NOT NULL,
          detail text NOT NULL,
          audience text,
          price_boundary text,
          image_url varchar(2048),
          visibility varchar(20) NOT NULL DEFAULT 'public',
          status varchar(24) NOT NULL DEFAULT 'draft',
          published_at timestamptz,
          sort_order integer NOT NULL DEFAULT 0,
          settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          version integer NOT NULL DEFAULT 1,
          deleted_at timestamptz,
          deleted_by uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_products_company_scope FOREIGN KEY (tenant_id, company_id)
            REFERENCES companies (tenant_id, id) ON DELETE CASCADE,
          CONSTRAINT uq_products_scope_id UNIQUE (tenant_id, company_id, id),
          CONSTRAINT uq_products_company_slug UNIQUE (company_id, slug),
          CONSTRAINT ck_products_slug CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'),
          CONSTRAINT ck_products_name_not_blank CHECK (char_length(btrim(name)) > 0),
          CONSTRAINT ck_products_sort_order_non_negative CHECK (sort_order >= 0),
          CONSTRAINT ck_products_version_positive CHECK (version > 0),
          CONSTRAINT ck_products_visibility CHECK
            (visibility IN ('public', 'authenticated', 'internal')),
          CONSTRAINT ck_products_status CHECK
            (status IN ('draft', 'review_pending', 'published', 'archived')),
          CONSTRAINT ck_products_published_requires_timestamp CHECK
            (status <> 'published' OR published_at IS NOT NULL)
        );
        CREATE INDEX ix_products_company_status_updated
          ON products (company_id, status, updated_at);
        CREATE INDEX ix_products_company_category_order
          ON products (company_id, category, sort_order);
        """
    )

    _execute_batch(
        """
        CREATE TABLE case_studies (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          slug varchar(96) NOT NULL,
          title varchar(240) NOT NULL,
          industry varchar(120),
          background text NOT NULL,
          solution text NOT NULL,
          result text NOT NULL,
          client_display_name varchar(200),
          image_url varchar(2048),
          visibility varchar(20) NOT NULL DEFAULT 'public',
          status varchar(24) NOT NULL DEFAULT 'draft',
          published_at timestamptz,
          sort_order integer NOT NULL DEFAULT 0,
          settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          version integer NOT NULL DEFAULT 1,
          deleted_at timestamptz,
          deleted_by uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_case_studies_company_scope FOREIGN KEY (tenant_id, company_id)
            REFERENCES companies (tenant_id, id) ON DELETE CASCADE,
          CONSTRAINT uq_case_studies_scope_id UNIQUE (tenant_id, company_id, id),
          CONSTRAINT uq_case_studies_company_slug UNIQUE (company_id, slug),
          CONSTRAINT ck_case_studies_slug CHECK
            (slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'),
          CONSTRAINT ck_case_studies_title_not_blank CHECK (char_length(btrim(title)) > 0),
          CONSTRAINT ck_case_studies_sort_order_non_negative CHECK (sort_order >= 0),
          CONSTRAINT ck_case_studies_version_positive CHECK (version > 0),
          CONSTRAINT ck_case_studies_visibility CHECK
            (visibility IN ('public', 'authenticated', 'internal')),
          CONSTRAINT ck_case_studies_status CHECK
            (status IN ('draft', 'review_pending', 'published', 'archived')),
          CONSTRAINT ck_case_studies_published_requires_timestamp CHECK
            (status <> 'published' OR published_at IS NOT NULL)
        );
        CREATE INDEX ix_case_studies_company_status_updated
          ON case_studies (company_id, status, updated_at);
        CREATE INDEX ix_case_studies_company_industry_order
          ON case_studies (company_id, industry, sort_order);
        """
    )

    _execute_batch(
        """
        CREATE TABLE forbidden_topics (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          topic varchar(240) NOT NULL,
          match_terms varchar(160)[] NOT NULL DEFAULT '{}'::varchar[],
          action varchar(32) NOT NULL DEFAULT 'refuse',
          safe_response text,
          is_active boolean NOT NULL DEFAULT true,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_forbidden_topics_company_scope FOREIGN KEY (tenant_id, company_id)
            REFERENCES companies (tenant_id, id) ON DELETE CASCADE,
          CONSTRAINT uq_forbidden_topics_scope_id UNIQUE (tenant_id, company_id, id),
          CONSTRAINT ck_forbidden_topics_topic_not_blank CHECK (char_length(btrim(topic)) > 0),
          CONSTRAINT ck_forbidden_topics_action_allowed
            CHECK (action IN ('refuse', 'handoff', 'safe_template')),
          CONSTRAINT ck_forbidden_topics_version_positive CHECK (version > 0)
        );
        CREATE INDEX ix_forbidden_topics_company_active
          ON forbidden_topics (company_id, is_active, updated_at);
        """
    )

    _execute_batch(
        """
        CREATE TABLE card_contact_fields (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          card_id uuid NOT NULL,
          field_type varchar(40) NOT NULL,
          label varchar(80) NOT NULL,
          value_ciphertext bytea NOT NULL,
          value_hmac varchar(64) NOT NULL,
          visibility varchar(20) NOT NULL DEFAULT 'public',
          sort_order integer NOT NULL DEFAULT 0,
          is_active boolean NOT NULL DEFAULT true,
          encryption_key_ref varchar(255) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_card_contact_fields_card_scope
            FOREIGN KEY (tenant_id, company_id, card_id)
            REFERENCES cards (tenant_id, company_id, id) ON DELETE CASCADE,
          CONSTRAINT uq_card_contact_fields_card_type
            UNIQUE (tenant_id, company_id, card_id, field_type),
          CONSTRAINT ck_card_contact_fields_value_hmac
            CHECK (char_length(value_hmac) = 64),
          CONSTRAINT ck_card_contact_fields_sort_order_non_negative CHECK (sort_order >= 0),
          CONSTRAINT ck_card_contact_fields_visibility CHECK
            (visibility IN ('public', 'authenticated', 'internal'))
        );
        CREATE INDEX ix_card_contact_fields_card_order
          ON card_contact_fields (card_id, sort_order, id);
        """
    )

    _execute_batch(
        """
        CREATE TABLE privacy_requests (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          visitor_id uuid NOT NULL,
          request_type varchar(32) NOT NULL,
          status varchar(24) NOT NULL DEFAULT 'pending',
          note_ciphertext bytea,
          encryption_key_ref varchar(255) NOT NULL,
          verification_method varchar(80),
          handled_by uuid,
          completed_at timestamptz,
          evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_privacy_requests_visitor_scope
            FOREIGN KEY (tenant_id, company_id, visitor_id)
            REFERENCES visitors (tenant_id, company_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_privacy_requests_handled_by FOREIGN KEY (handled_by)
            REFERENCES users (id) ON DELETE SET NULL,
          CONSTRAINT ck_privacy_requests_type CHECK
            (request_type IN ('access', 'correction', 'deletion', 'withdraw_consent')),
          CONSTRAINT ck_privacy_requests_status CHECK
            (status IN ('pending', 'verified', 'in_progress', 'completed', 'rejected'))
        );
        CREATE INDEX ix_privacy_requests_company_status_created
          ON privacy_requests (company_id, status, created_at);
        CREATE INDEX ix_privacy_requests_visitor_created
          ON privacy_requests (visitor_id, created_at);
        """
    )

    _execute_batch(
        """
        CREATE TABLE leads (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          card_id uuid NOT NULL,
          visitor_id uuid NOT NULL,
          conversation_id uuid,
          owner_user_id uuid NOT NULL,
          status varchar(24) NOT NULL DEFAULT 'new',
          priority varchar(20) NOT NULL DEFAULT 'medium',
          requirement_ciphertext bytea NOT NULL,
          encryption_key_ref varchar(255) NOT NULL,
          interest_tags varchar(160)[] NOT NULL DEFAULT '{}'::varchar[],
          viewed_at timestamptz,
          closed_at timestamptz,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_leads_card_scope FOREIGN KEY (tenant_id, company_id, card_id)
            REFERENCES cards (tenant_id, company_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_leads_visitor_scope FOREIGN KEY (tenant_id, company_id, visitor_id)
            REFERENCES visitors (tenant_id, company_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_leads_conversation_scope
            FOREIGN KEY (tenant_id, company_id, conversation_id)
            REFERENCES conversations (tenant_id, company_id, id) ON DELETE RESTRICT,
          CONSTRAINT fk_leads_owner FOREIGN KEY (owner_user_id)
            REFERENCES users (id) ON DELETE RESTRICT,
          CONSTRAINT uq_leads_scope_id UNIQUE (tenant_id, company_id, id),
          CONSTRAINT ck_leads_status CHECK
            (status IN ('new', 'viewed', 'following', 'won', 'lost', 'invalid')),
          CONSTRAINT ck_leads_priority_allowed CHECK (priority IN ('low', 'medium', 'high')),
          CONSTRAINT ck_leads_version_positive CHECK (version > 0)
        );
        CREATE INDEX ix_leads_company_status_created
          ON leads (company_id, status, created_at);
        CREATE INDEX ix_leads_owner_status_created
          ON leads (owner_user_id, status, created_at);
        """
    )

    _execute_batch(
        """
        CREATE TABLE lead_followups (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          lead_id uuid NOT NULL,
          actor_user_id uuid NOT NULL,
          followup_type varchar(32) NOT NULL,
          content_ciphertext bytea NOT NULL,
          encryption_key_ref varchar(255) NOT NULL,
          next_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_lead_followups_lead_scope
            FOREIGN KEY (tenant_id, company_id, lead_id)
            REFERENCES leads (tenant_id, company_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_lead_followups_actor FOREIGN KEY (actor_user_id)
            REFERENCES users (id) ON DELETE RESTRICT,
          CONSTRAINT ck_lead_followups_type_allowed
            CHECK (followup_type IN ('note', 'call', 'message', 'meeting', 'status_change'))
        );
        CREATE INDEX ix_lead_followups_lead_created
          ON lead_followups (lead_id, created_at);
        """
    )

    _execute_batch(
        """
        CREATE TABLE notifications (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          recipient_user_id uuid NOT NULL,
          notification_type varchar(80) NOT NULL,
          title varchar(200) NOT NULL,
          body text NOT NULL,
          resource_type varchar(80),
          resource_id uuid,
          read_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_notifications_company_scope FOREIGN KEY (tenant_id, company_id)
            REFERENCES companies (tenant_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_notifications_recipient FOREIGN KEY (recipient_user_id)
            REFERENCES users (id) ON DELETE CASCADE
        );
        CREATE INDEX ix_notifications_recipient_read_created
          ON notifications (recipient_user_id, read_at, created_at);
        """
    )

    op.execute(
        """
        CREATE FUNCTION app.erase_visitor_lead_followups(
          p_tenant_id uuid,
          p_company_id uuid,
          p_visitor_id uuid
        ) RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          affected bigint;
        BEGIN
          IF NOT app.scope_matches(p_tenant_id, p_company_id) THEN
            RAISE EXCEPTION 'scope mismatch' USING ERRCODE = '42501';
          END IF;
          UPDATE public.lead_followups AS followup
          SET content_ciphertext = decode('00', 'hex'),
              encryption_key_ref = 'erased'
          FROM public.leads AS lead
          WHERE lead.id = followup.lead_id
            AND lead.tenant_id = p_tenant_id
            AND lead.company_id = p_company_id
            AND lead.visitor_id = p_visitor_id
            AND followup.tenant_id = p_tenant_id
            AND followup.company_id = p_company_id;
          GET DIAGNOSTICS affected = ROW_COUNT;
          RETURN affected;
        END;
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.erase_visitor_lead_followups(uuid, uuid, uuid) FROM PUBLIC"
    )

    for table in TOUCH_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_touch_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
            """
        )

    for table in SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_scope_isolation ON {table}
            USING (app.scope_matches(tenant_id, company_id))
            WITH CHECK (app.scope_matches(tenant_id, company_id))
            """
        )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
              'REVOKE ALL ON TABLES FROM cf_ai_card_app';
            REVOKE ALL PRIVILEGES ON TABLE lead_followups, security_events
              FROM cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON TABLE products, case_studies, forbidden_topics,
                card_contact_fields, privacy_requests, leads, notifications
                TO cf_ai_card_app;
            GRANT SELECT, INSERT ON TABLE lead_followups TO cf_ai_card_app;
            GRANT INSERT ON TABLE security_events TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.erase_visitor_lead_followups(uuid, uuid, uuid)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    for table in SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_isolation ON {table}")

    for table in TOUCH_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_touch_updated_at ON {table}")

    op.execute(
        "DROP FUNCTION IF EXISTS app.erase_visitor_lead_followups(uuid, uuid, uuid)"
    )

    for table in (
        "notifications",
        "lead_followups",
        "leads",
        "privacy_requests",
        "card_contact_fields",
        "forbidden_topics",
        "case_studies",
        "products",
        "security_events",
    ):
        op.execute(f"DROP TABLE {table}")

    op.execute("ALTER TABLE visitor_profiles DROP COLUMN demand_ciphertext")
    # Compatibility cleanup for an unreleased development draft of this revision.
    op.execute("DROP FUNCTION IF EXISTS app.reject_append_only_mutation()")

# ruff: noqa: E501
"""Create the tenant-isolated database and RAG core.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10
"""

from collections.abc import Iterable, Sequence

from alembic import op

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def execute_all(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


CORE_TABLE_DDL = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE SCHEMA IF NOT EXISTS app",
    """
    CREATE FUNCTION app.current_tenant_id() RETURNS uuid
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
      SELECT nullif(current_setting('app.tenant_id', true), '')::uuid
    $$
    """,
    """
    CREATE FUNCTION app.current_company_id() RETURNS uuid
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
      SELECT nullif(current_setting('app.company_id', true), '')::uuid
    $$
    """,
    """
    CREATE FUNCTION app.current_card_slug() RETURNS text
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
      SELECT nullif(current_setting('app.card_slug', true), '')
    $$
    """,
    """
    CREATE FUNCTION app.scope_matches(row_tenant_id uuid, row_company_id uuid)
    RETURNS boolean
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
      SELECT row_tenant_id = app.current_tenant_id()
         AND row_company_id = app.current_company_id()
    $$
    """,
    """
    CREATE TABLE tenants (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      name varchar(200) NOT NULL,
      type varchar(20) NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'active',
      settings jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz,
      deleted_by uuid,
      CONSTRAINT ck_tenants_name_not_blank CHECK (char_length(btrim(name)) > 0),
      CONSTRAINT ck_tenants_type CHECK (type IN ('chamber', 'enterprise')),
      CONSTRAINT ck_tenants_status CHECK (status IN ('active', 'suspended', 'disabled'))
    )
    """,
    """
    CREATE TABLE companies (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
      name varchar(200) NOT NULL,
      normalized_name varchar(200) NOT NULL,
      industry varchar(120),
      status varchar(20) NOT NULL DEFAULT 'active',
      settings jsonb NOT NULL DEFAULT '{}'::jsonb,
      version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz,
      deleted_by uuid,
      CONSTRAINT uq_companies_tenant_id_id UNIQUE (tenant_id, id),
      CONSTRAINT uq_companies_tenant_id_normalized_name UNIQUE (tenant_id, normalized_name),
      CONSTRAINT ck_companies_name_not_blank CHECK (char_length(btrim(name)) > 0),
      CONSTRAINT ck_companies_status CHECK (status IN ('active', 'suspended', 'disabled')),
      CONSTRAINT ck_companies_version_positive CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE users (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      email_ciphertext bytea,
      email_hmac varchar(64),
      mobile_ciphertext bytea,
      mobile_hmac varchar(64),
      display_name varchar(120) NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'active',
      version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz,
      deleted_by uuid,
      CONSTRAINT ck_users_status CHECK (status IN ('active', 'suspended', 'disabled')),
      CONSTRAINT ck_users_version_positive CHECK (version > 0)
    )
    """,
    "CREATE UNIQUE INDEX uq_users_email_hmac ON users(email_hmac) WHERE email_hmac IS NOT NULL",
    "CREATE UNIQUE INDEX uq_users_mobile_hmac ON users(mobile_hmac) WHERE mobile_hmac IS NOT NULL",
    """
    CREATE TABLE memberships (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      company_id uuid,
      role varchar(32) NOT NULL,
      permissions varchar(80)[] NOT NULL DEFAULT '{}'::varchar[],
      status varchar(20) NOT NULL DEFAULT 'active',
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_memberships_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_memberships_user_scope
        UNIQUE NULLS NOT DISTINCT (user_id, tenant_id, company_id),
      CONSTRAINT ck_memberships_role
        CHECK (role IN ('platform_admin', 'company_admin', 'card_owner')),
      CONSTRAINT ck_memberships_status CHECK (status IN ('active', 'suspended', 'disabled'))
    )
    """,
    """
    CREATE TABLE auth_sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      company_id uuid,
      refresh_token_hash varchar(128) NOT NULL UNIQUE,
      expires_at timestamptz NOT NULL,
      revoked_at timestamptz,
      revoke_reason varchar(120),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_auth_sessions_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE cards (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      slug varchar(96) NOT NULL,
      display_name varchar(160) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'draft',
      published_at timestamptz,
      settings jsonb NOT NULL DEFAULT '{}'::jsonb,
      version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz,
      deleted_by uuid,
      CONSTRAINT fk_cards_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_cards_slug UNIQUE (slug),
      CONSTRAINT uq_cards_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT ck_cards_slug_trimmed CHECK (slug = btrim(slug)),
      CONSTRAINT ck_cards_slug_public_format
        CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'),
      CONSTRAINT ck_cards_status
        CHECK (status IN ('draft', 'review_pending', 'published', 'archived')),
      CONSTRAINT ck_cards_published_at
        CHECK (status <> 'published' OR published_at IS NOT NULL),
      CONSTRAINT ck_cards_version_positive CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE visitors (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      anonymous_hash varchar(64) NOT NULL,
      first_seen_at timestamptz NOT NULL DEFAULT now(),
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_visitors_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_visitors_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_visitors_scope_anonymous_hash
        UNIQUE (tenant_id, company_id, anonymous_hash),
      CONSTRAINT ck_visitors_anonymous_hash_sha256 CHECK (char_length(anonymous_hash) = 64)
    )
    """,
    """
    CREATE TABLE visitor_profiles (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      visitor_id uuid NOT NULL UNIQUE,
      name_ciphertext bytea,
      mobile_ciphertext bytea,
      mobile_hmac varchar(64),
      email_ciphertext bytea,
      email_hmac varchar(64),
      wechat_ciphertext bytea,
      company_name varchar(200),
      encryption_key_ref varchar(255) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_visitor_profiles_visitor
        FOREIGN KEY (tenant_id, company_id, visitor_id)
        REFERENCES visitors(tenant_id, company_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE consent_records (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      visitor_id uuid NOT NULL,
      scope varchar(32) NOT NULL,
      policy_version varchar(80) NOT NULL,
      granted boolean NOT NULL,
      recorded_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz,
      evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
      CONSTRAINT fk_consent_records_visitor
        FOREIGN KEY (tenant_id, company_id, visitor_id)
        REFERENCES visitors(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT ck_consent_records_scope
        CHECK (scope IN ('browse_notice', 'chat_notice', 'lead_contact'))
    )
    """,
    """
    CREATE TABLE visits (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      card_id uuid NOT NULL,
      visitor_id uuid NOT NULL,
      source varchar(120),
      started_at timestamptz NOT NULL DEFAULT now(),
      ended_at timestamptz,
      context jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_visits_card
        FOREIGN KEY (tenant_id, company_id, card_id)
        REFERENCES cards(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_visits_visitor
        FOREIGN KEY (tenant_id, company_id, visitor_id)
        REFERENCES visitors(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_visits_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT ck_visits_time_order CHECK (ended_at IS NULL OR ended_at >= started_at)
    )
    """,
    """
    CREATE TABLE visit_events (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      visit_id uuid NOT NULL,
      event_type varchar(80) NOT NULL,
      object_type varchar(80),
      object_id varchar(160),
      occurred_at timestamptz NOT NULL DEFAULT now(),
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      CONSTRAINT fk_visit_events_visit
        FOREIGN KEY (tenant_id, company_id, visit_id)
        REFERENCES visits(tenant_id, company_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE conversations (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      card_id uuid NOT NULL,
      visitor_id uuid NOT NULL,
      visit_id uuid,
      status varchar(20) NOT NULL DEFAULT 'active',
      primary_intent varchar(80),
      started_at timestamptz NOT NULL DEFAULT now(),
      last_activity_at timestamptz NOT NULL DEFAULT now(),
      closed_at timestamptz,
      risk_level varchar(20) NOT NULL DEFAULT 'low',
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_conversations_card
        FOREIGN KEY (tenant_id, company_id, card_id)
        REFERENCES cards(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_conversations_visitor
        FOREIGN KEY (tenant_id, company_id, visitor_id)
        REFERENCES visitors(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_conversations_visit
        FOREIGN KEY (tenant_id, company_id, visit_id)
        REFERENCES visits(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT uq_conversations_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT ck_conversations_status
        CHECK (status IN ('active', 'closed', 'expired', 'blocked')),
      CONSTRAINT ck_conversations_close_state
        CHECK ((status = 'active' AND closed_at IS NULL) OR status <> 'active')
    )
    """,
    """
    CREATE TABLE messages (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      role varchar(20) NOT NULL,
      content text NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'completed',
      content_redacted boolean NOT NULL DEFAULT false,
      client_message_id varchar(120),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_messages_conversation
        FOREIGN KEY (tenant_id, company_id, conversation_id)
        REFERENCES conversations(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_messages_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT ck_messages_role CHECK (role IN ('system', 'user', 'assistant', 'human')),
      CONSTRAINT ck_messages_status
        CHECK (status IN ('pending', 'completed', 'refused', 'failed'))
    )
    """,
)


AI_AND_KNOWLEDGE_DDL = (
    """
    CREATE TABLE prompt_versions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      name varchar(120) NOT NULL,
      purpose varchar(120) NOT NULL,
      version_number integer NOT NULL,
      content text NOT NULL,
      content_hash varchar(64) NOT NULL,
      change_summary text,
      evaluation_result jsonb NOT NULL DEFAULT '{}'::jsonb,
      status varchar(20) NOT NULL DEFAULT 'draft',
      published_by uuid REFERENCES users(id) ON DELETE RESTRICT,
      published_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_prompt_versions_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_prompt_versions_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_prompt_versions_name_version
        UNIQUE (tenant_id, company_id, name, version_number),
      CONSTRAINT ck_prompt_versions_version_positive CHECK (version_number > 0),
      CONSTRAINT ck_prompt_versions_content_hash_sha256 CHECK (char_length(content_hash) = 64),
      CONSTRAINT ck_prompt_versions_status CHECK (status IN ('draft', 'published', 'retired')),
      CONSTRAINT ck_prompt_versions_publish_state
        CHECK (status <> 'published' OR (published_at IS NOT NULL AND published_by IS NOT NULL))
    )
    """,
    """
    CREATE TABLE model_configs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      purpose varchar(80) NOT NULL,
      provider varchar(80) NOT NULL,
      model_name varchar(160) NOT NULL,
      endpoint_region varchar(80),
      secret_ref varchar(255) NOT NULL,
      timeout_ms integer NOT NULL DEFAULT 30000,
      max_retries smallint NOT NULL DEFAULT 2,
      max_concurrency integer NOT NULL DEFAULT 10,
      daily_budget_cny numeric(12, 2) NOT NULL DEFAULT 0,
      data_retention varchar(40) NOT NULL DEFAULT 'no_training',
      enabled boolean NOT NULL DEFAULT true,
      parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
      version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_model_configs_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_model_configs_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_model_configs_purpose_provider
        UNIQUE (tenant_id, company_id, purpose, provider),
      CONSTRAINT ck_model_configs_timeout_positive CHECK (timeout_ms > 0),
      CONSTRAINT ck_model_configs_retries_non_negative CHECK (max_retries >= 0),
      CONSTRAINT ck_model_configs_concurrency_positive CHECK (max_concurrency > 0),
      CONSTRAINT ck_model_configs_budget_non_negative CHECK (daily_budget_cny >= 0),
      CONSTRAINT ck_model_configs_version_positive CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE ai_runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      message_id uuid NOT NULL UNIQUE,
      prompt_version_id uuid NOT NULL,
      model_config_id uuid NOT NULL,
      provider varchar(80) NOT NULL,
      model varchar(160) NOT NULL,
      endpoint_region varchar(80),
      trace_id varchar(128) NOT NULL,
      input_hash varchar(64) NOT NULL,
      output_hash varchar(64),
      input_tokens integer NOT NULL DEFAULT 0,
      output_tokens integer NOT NULL DEFAULT 0,
      first_token_latency_ms integer,
      total_latency_ms integer NOT NULL DEFAULT 0,
      estimated_cost_cny numeric(14, 6) NOT NULL DEFAULT 0,
      retry_count smallint NOT NULL DEFAULT 0,
      status varchar(20) NOT NULL DEFAULT 'pending',
      safety_result jsonb NOT NULL DEFAULT '{}'::jsonb,
      retrieval_result jsonb NOT NULL DEFAULT '{}'::jsonb,
      error_code varchar(80),
      started_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_ai_runs_message
        FOREIGN KEY (tenant_id, company_id, message_id)
        REFERENCES messages(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_ai_runs_prompt
        FOREIGN KEY (tenant_id, company_id, prompt_version_id)
        REFERENCES prompt_versions(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT fk_ai_runs_model
        FOREIGN KEY (tenant_id, company_id, model_config_id)
        REFERENCES model_configs(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT ck_ai_runs_input_hash_sha256 CHECK (char_length(input_hash) = 64),
      CONSTRAINT ck_ai_runs_output_hash_sha256
        CHECK (output_hash IS NULL OR char_length(output_hash) = 64),
      CONSTRAINT ck_ai_runs_tokens_non_negative CHECK (input_tokens >= 0 AND output_tokens >= 0),
      CONSTRAINT ck_ai_runs_latency_non_negative
        CHECK (total_latency_ms >= 0 AND first_token_latency_ms >= 0),
      CONSTRAINT ck_ai_runs_retry_non_negative CHECK (retry_count >= 0),
      CONSTRAINT ck_ai_runs_status
        CHECK (status IN ('pending', 'completed', 'refused', 'failed'))
    )
    """,
    """
    CREATE TABLE knowledge_documents (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      source_type varchar(80) NOT NULL,
      source_id varchar(160) NOT NULL,
      title varchar(500) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'draft',
      current_version_id uuid,
      version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_knowledge_documents_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_knowledge_documents_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_knowledge_documents_source
        UNIQUE (tenant_id, company_id, source_type, source_id),
      CONSTRAINT ck_knowledge_documents_status
        CHECK (status IN ('draft', 'review_pending', 'published', 'archived')),
      CONSTRAINT ck_knowledge_documents_version_positive CHECK (version > 0),
      CONSTRAINT ck_knowledge_documents_active_version
        CHECK (status <> 'published' OR current_version_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE knowledge_versions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      document_id uuid NOT NULL,
      version_number integer NOT NULL,
      raw_text text NOT NULL,
      content_hash varchar(64) NOT NULL,
      review_status varchar(24) NOT NULL DEFAULT 'draft',
      reviewed_by uuid REFERENCES users(id) ON DELETE RESTRICT,
      reviewed_at timestamptz,
      published_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_knowledge_versions_document
        FOREIGN KEY (tenant_id, company_id, document_id)
        REFERENCES knowledge_documents(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_knowledge_versions_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_knowledge_versions_document_scope_id
        UNIQUE (tenant_id, company_id, document_id, id),
      CONSTRAINT uq_knowledge_versions_document_version UNIQUE (document_id, version_number),
      CONSTRAINT ck_knowledge_versions_version_positive CHECK (version_number > 0),
      CONSTRAINT ck_knowledge_versions_content_hash_sha256 CHECK (char_length(content_hash) = 64),
      CONSTRAINT ck_knowledge_versions_review_status
        CHECK (review_status IN ('draft', 'review_pending', 'approved', 'rejected', 'archived')),
      CONSTRAINT ck_knowledge_versions_approval_state
        CHECK (review_status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )
    """,
    """
    ALTER TABLE knowledge_documents
      ADD CONSTRAINT fk_knowledge_documents_current_version
      FOREIGN KEY (tenant_id, company_id, id, current_version_id)
      REFERENCES knowledge_versions(tenant_id, company_id, document_id, id)
      ON DELETE RESTRICT
      DEFERRABLE INITIALLY DEFERRED
    """,
    """
    CREATE TABLE knowledge_chunks (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      document_id uuid NOT NULL,
      version_id uuid NOT NULL,
      ordinal integer NOT NULL,
      title varchar(500) NOT NULL,
      text text NOT NULL,
      token_count integer NOT NULL,
      search_tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('simple', coalesce(text, ''))) STORED,
      embedding vector(1024),
      embedding_model varchar(160),
      visibility varchar(24) NOT NULL DEFAULT 'public',
      is_active boolean NOT NULL DEFAULT false,
      source_type varchar(80) NOT NULL,
      source_id varchar(160) NOT NULL,
      content_hash varchar(64) NOT NULL,
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_knowledge_chunks_document
        FOREIGN KEY (tenant_id, company_id, document_id)
        REFERENCES knowledge_documents(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_knowledge_chunks_version
        FOREIGN KEY (tenant_id, company_id, document_id, version_id)
        REFERENCES knowledge_versions(tenant_id, company_id, document_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_knowledge_chunks_scope_id UNIQUE (tenant_id, company_id, id),
      CONSTRAINT uq_knowledge_chunks_version_ordinal UNIQUE (version_id, ordinal),
      CONSTRAINT ck_knowledge_chunks_ordinal_non_negative CHECK (ordinal >= 0),
      CONSTRAINT ck_knowledge_chunks_token_count_positive CHECK (token_count > 0),
      CONSTRAINT ck_knowledge_chunks_content_hash_sha256 CHECK (char_length(content_hash) = 64),
      CONSTRAINT ck_knowledge_chunks_visibility
        CHECK (visibility IN ('public', 'authenticated', 'internal')),
      CONSTRAINT ck_knowledge_chunks_embedding_metadata
        CHECK ((embedding IS NULL) = (embedding_model IS NULL))
    )
    """,
    """
    CREATE TABLE message_citations (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      message_id uuid NOT NULL,
      chunk_id uuid NOT NULL,
      rank smallint NOT NULL,
      score double precision NOT NULL,
      snapshot_text text NOT NULL,
      snapshot_hash varchar(64) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_message_citations_message
        FOREIGN KEY (tenant_id, company_id, message_id)
        REFERENCES messages(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_message_citations_chunk
        FOREIGN KEY (tenant_id, company_id, chunk_id)
        REFERENCES knowledge_chunks(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT uq_message_citations_message_chunk UNIQUE (message_id, chunk_id),
      CONSTRAINT ck_message_citations_rank_positive CHECK (rank > 0),
      CONSTRAINT ck_message_citations_score_cosine_range CHECK (score >= -1 AND score <= 1),
      CONSTRAINT ck_message_citations_snapshot_hash_sha256 CHECK (char_length(snapshot_hash) = 64)
    )
    """,
    """
    CREATE TABLE knowledge_index_jobs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      version_id uuid NOT NULL,
      embedding_model varchar(160) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'pending',
      attempt integer NOT NULL DEFAULT 0,
      error_code varchar(80),
      error_detail text,
      started_at timestamptz,
      completed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_knowledge_index_jobs_version
        FOREIGN KEY (tenant_id, company_id, version_id)
        REFERENCES knowledge_versions(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_knowledge_index_jobs_version_model UNIQUE (version_id, embedding_model),
      CONSTRAINT ck_knowledge_index_jobs_status
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
      CONSTRAINT ck_knowledge_index_jobs_attempt_non_negative CHECK (attempt >= 0)
    )
    """,
    """
    CREATE TABLE knowledge_gaps (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      normalized_question_hash varchar(64) NOT NULL,
      question text NOT NULL,
      reason varchar(120) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'pending',
      suggested_answer text,
      occurrence_count integer NOT NULL DEFAULT 1,
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      approved_version_id uuid,
      evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_knowledge_gaps_conversation
        FOREIGN KEY (tenant_id, company_id, conversation_id)
        REFERENCES conversations(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_knowledge_gaps_approved_version
        FOREIGN KEY (tenant_id, company_id, approved_version_id)
        REFERENCES knowledge_versions(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT ck_knowledge_gaps_question_hash_sha256
        CHECK (char_length(normalized_question_hash) = 64),
      CONSTRAINT ck_knowledge_gaps_occurrence_count_positive CHECK (occurrence_count > 0),
      CONSTRAINT ck_knowledge_gaps_status
        CHECK (status IN ('pending', 'drafted', 'approved', 'indexing', 'indexed', 'rejected', 'failed')),
      CONSTRAINT ck_knowledge_gaps_indexed_version
        CHECK (status <> 'indexed' OR approved_version_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE visit_summaries (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      conversation_id uuid NOT NULL,
      last_message_id uuid NOT NULL,
      prompt_version_id uuid NOT NULL,
      summary text NOT NULL,
      interests varchar(160)[] NOT NULL DEFAULT '{}'::varchar[],
      strength varchar(40),
      next_step text,
      risk_notes text,
      source_message_ids uuid[] NOT NULL,
      is_current boolean NOT NULL DEFAULT true,
      stale_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_visit_summaries_conversation
        FOREIGN KEY (tenant_id, company_id, conversation_id)
        REFERENCES conversations(tenant_id, company_id, id) ON DELETE CASCADE,
      CONSTRAINT fk_visit_summaries_last_message
        FOREIGN KEY (tenant_id, company_id, last_message_id)
        REFERENCES messages(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT fk_visit_summaries_prompt
        FOREIGN KEY (tenant_id, company_id, prompt_version_id)
        REFERENCES prompt_versions(tenant_id, company_id, id) ON DELETE RESTRICT,
      CONSTRAINT uq_visit_summaries_idempotency
        UNIQUE (conversation_id, last_message_id, prompt_version_id),
      CONSTRAINT ck_visit_summaries_current_state
        CHECK ((is_current AND stale_at IS NULL) OR (NOT is_current AND stale_at IS NOT NULL))
    )
    """,
)


RELIABILITY_DDL = (
    """
    CREATE TABLE idempotency_keys (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      scope varchar(120) NOT NULL,
      key varchar(200) NOT NULL,
      request_hash varchar(64) NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'processing',
      response_status_code integer,
      response_body jsonb,
      resource_type varchar(120),
      resource_id uuid,
      locked_until timestamptz,
      expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_idempotency_keys_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE CASCADE,
      CONSTRAINT uq_idempotency_keys_scope_key
        UNIQUE (tenant_id, company_id, scope, key),
      CONSTRAINT ck_idempotency_keys_request_hash_sha256 CHECK (char_length(request_hash) = 64),
      CONSTRAINT ck_idempotency_keys_status
        CHECK (status IN ('processing', 'completed', 'failed')),
      CONSTRAINT ck_idempotency_keys_response_code
        CHECK (response_status_code IS NULL OR response_status_code BETWEEN 100 AND 599),
      CONSTRAINT ck_idempotency_keys_expiry CHECK (expires_at > created_at)
    )
    """,
    """
    CREATE TABLE audit_logs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
      action varchar(120) NOT NULL,
      resource_type varchar(120) NOT NULL,
      resource_id uuid,
      reason text,
      trace_id varchar(128),
      request_ip_hash varchar(64),
      event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
      previous_hash varchar(64),
      entry_hash varchar(64) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_audit_logs_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE RESTRICT,
      CONSTRAINT ck_audit_logs_entry_hash_sha256 CHECK (char_length(entry_hash) = 64),
      CONSTRAINT ck_audit_logs_previous_hash_sha256
        CHECK (previous_hash IS NULL OR char_length(previous_hash) = 64),
      CONSTRAINT ck_audit_logs_request_ip_hash_sha256
        CHECK (request_ip_hash IS NULL OR char_length(request_ip_hash) = 64)
    )
    """,
    """
    CREATE TABLE outbox_events (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id uuid NOT NULL,
      company_id uuid NOT NULL,
      aggregate_type varchar(120) NOT NULL,
      aggregate_id uuid NOT NULL,
      aggregate_version integer,
      event_type varchar(160) NOT NULL,
      payload jsonb NOT NULL,
      headers jsonb NOT NULL DEFAULT '{}'::jsonb,
      deduplication_key varchar(200) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'pending',
      attempts integer NOT NULL DEFAULT 0,
      available_at timestamptz NOT NULL DEFAULT now(),
      locked_at timestamptz,
      published_at timestamptz,
      last_error text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT fk_outbox_events_company
        FOREIGN KEY (tenant_id, company_id)
        REFERENCES companies(tenant_id, id) ON DELETE RESTRICT,
      CONSTRAINT uq_outbox_events_deduplication_key
        UNIQUE (tenant_id, company_id, deduplication_key),
      CONSTRAINT ck_outbox_events_status
        CHECK (status IN ('pending', 'processing', 'published', 'failed', 'dead_letter')),
      CONSTRAINT ck_outbox_events_attempts_non_negative CHECK (attempts >= 0),
      CONSTRAINT ck_outbox_events_aggregate_version
        CHECK (aggregate_version IS NULL OR aggregate_version > 0),
      CONSTRAINT ck_outbox_events_published_state
        CHECK (status <> 'published' OR published_at IS NOT NULL)
    )
    """,
)


INDEX_DDL = (
    "CREATE INDEX ix_companies_tenant_status_updated ON companies(tenant_id, status, updated_at DESC)",
    "CREATE INDEX ix_memberships_scope_status ON memberships(tenant_id, company_id, status)",
    "CREATE INDEX ix_auth_sessions_user_expires ON auth_sessions(user_id, expires_at DESC)",
    "CREATE INDEX ix_cards_company_status_updated ON cards(company_id, status, updated_at DESC)",
    """
    CREATE INDEX ix_cards_public_slug ON cards(slug)
    WHERE status = 'published' AND deleted_at IS NULL
    """,
    "CREATE INDEX ix_visitors_company_last_seen ON visitors(company_id, last_seen_at DESC)",
    """
    CREATE INDEX ix_consent_records_visitor_scope_recorded
    ON consent_records(visitor_id, scope, recorded_at DESC)
    """,
    "CREATE INDEX ix_visits_card_started ON visits(card_id, started_at DESC)",
    "CREATE INDEX ix_visits_company_started ON visits(company_id, started_at DESC)",
    "CREATE INDEX ix_visit_events_visit_occurred ON visit_events(visit_id, occurred_at)",
    """
    CREATE INDEX ix_visit_events_company_type_occurred
    ON visit_events(company_id, event_type, occurred_at DESC)
    """,
    "CREATE INDEX ix_conversations_card_started ON conversations(card_id, started_at DESC)",
    """
    CREATE INDEX ix_conversations_company_status_updated
    ON conversations(company_id, status, updated_at DESC)
    """,
    "CREATE INDEX ix_messages_conversation_created ON messages(conversation_id, created_at)",
    """
    CREATE UNIQUE INDEX uq_messages_client_message
    ON messages(conversation_id, client_message_id)
    WHERE client_message_id IS NOT NULL
    """,
    """
    CREATE INDEX ix_prompt_versions_company_status_updated
    ON prompt_versions(company_id, status, updated_at DESC)
    """,
    "CREATE INDEX ix_ai_runs_company_created ON ai_runs(company_id, created_at DESC)",
    "CREATE INDEX ix_ai_runs_trace_id ON ai_runs(trace_id)",
    """
    CREATE INDEX ix_knowledge_documents_company_status_updated
    ON knowledge_documents(company_id, status, updated_at DESC)
    """,
    """
    CREATE INDEX ix_knowledge_documents_title_trgm
    ON knowledge_documents USING gin(title gin_trgm_ops)
    """,
    """
    CREATE INDEX ix_knowledge_versions_raw_text_fts
    ON knowledge_versions USING gin(to_tsvector('simple', coalesce(raw_text, '')))
    """,
    """
    CREATE INDEX ix_knowledge_chunks_scope_filter
    ON knowledge_chunks(company_id, visibility, is_active, version_id)
    """,
    """
    CREATE INDEX ix_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw(embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding IS NOT NULL
    """,
    "CREATE INDEX ix_knowledge_chunks_text_fts ON knowledge_chunks USING gin(search_tsv)",
    """
    CREATE INDEX ix_knowledge_chunks_text_trgm
    ON knowledge_chunks USING gin(text gin_trgm_ops)
    """,
    "CREATE INDEX ix_message_citations_message_rank ON message_citations(message_id, rank)",
    """
    CREATE INDEX ix_knowledge_index_jobs_company_status_created
    ON knowledge_index_jobs(company_id, status, created_at)
    """,
    """
    CREATE INDEX ix_knowledge_gaps_company_status_updated
    ON knowledge_gaps(company_id, status, updated_at DESC)
    """,
    """
    CREATE INDEX ix_knowledge_gaps_company_question_hash
    ON knowledge_gaps(company_id, normalized_question_hash)
    """,
    """
    CREATE INDEX ix_knowledge_gaps_question_trgm
    ON knowledge_gaps USING gin(question gin_trgm_ops)
    """,
    """
    CREATE UNIQUE INDEX uq_visit_summaries_current_conversation
    ON visit_summaries(conversation_id) WHERE is_current
    """,
    "CREATE INDEX ix_idempotency_keys_expires_at ON idempotency_keys(expires_at)",
    "CREATE INDEX ix_audit_logs_company_created ON audit_logs(company_id, created_at DESC)",
    """
    CREATE INDEX ix_audit_logs_resource
    ON audit_logs(company_id, resource_type, resource_id)
    """,
    "CREATE INDEX ix_audit_logs_trace_id ON audit_logs(trace_id)",
    """
    CREATE INDEX ix_outbox_events_dispatch
    ON outbox_events(status, available_at, created_at)
    """,
    """
    CREATE INDEX ix_outbox_events_aggregate
    ON outbox_events(company_id, aggregate_type, aggregate_id)
    """,
)


TRIGGER_DDL = (
    """
    CREATE FUNCTION app.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.updated_at := now();
      RETURN NEW;
    END
    $$
    """,
    """
    CREATE FUNCTION app.guard_immutable_content() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF TG_TABLE_NAME = 'knowledge_versions' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
        NEW.company_id IS DISTINCT FROM OLD.company_id OR
        NEW.document_id IS DISTINCT FROM OLD.document_id OR
        NEW.version_number IS DISTINCT FROM OLD.version_number OR
        NEW.raw_text IS DISTINCT FROM OLD.raw_text OR
        NEW.content_hash IS DISTINCT FROM OLD.content_hash
      ) THEN
        RAISE EXCEPTION 'knowledge version content is immutable'
          USING ERRCODE = '55000';
      END IF;

      IF TG_TABLE_NAME = 'knowledge_chunks' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
        NEW.company_id IS DISTINCT FROM OLD.company_id OR
        NEW.document_id IS DISTINCT FROM OLD.document_id OR
        NEW.version_id IS DISTINCT FROM OLD.version_id OR
        NEW.ordinal IS DISTINCT FROM OLD.ordinal OR
        NEW.title IS DISTINCT FROM OLD.title OR
        NEW.text IS DISTINCT FROM OLD.text OR
        NEW.token_count IS DISTINCT FROM OLD.token_count OR
        NEW.source_type IS DISTINCT FROM OLD.source_type OR
        NEW.source_id IS DISTINCT FROM OLD.source_id OR
        NEW.content_hash IS DISTINCT FROM OLD.content_hash OR
        NEW.metadata IS DISTINCT FROM OLD.metadata
      ) THEN
        RAISE EXCEPTION 'knowledge chunk source content is immutable'
          USING ERRCODE = '55000';
      END IF;

      IF TG_TABLE_NAME = 'knowledge_chunks' AND OLD.is_active AND (
        NEW.embedding IS DISTINCT FROM OLD.embedding OR
        NEW.embedding_model IS DISTINCT FROM OLD.embedding_model
      ) THEN
        RAISE EXCEPTION 'active knowledge chunk embedding is immutable'
          USING ERRCODE = '55000';
      END IF;

      IF TG_TABLE_NAME = 'prompt_versions' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
        NEW.company_id IS DISTINCT FROM OLD.company_id OR
        NEW.name IS DISTINCT FROM OLD.name OR
        NEW.purpose IS DISTINCT FROM OLD.purpose OR
        NEW.version_number IS DISTINCT FROM OLD.version_number OR
        NEW.content IS DISTINCT FROM OLD.content OR
        NEW.content_hash IS DISTINCT FROM OLD.content_hash
      ) THEN
        RAISE EXCEPTION 'prompt version content is immutable'
          USING ERRCODE = '55000';
      END IF;

      RETURN NEW;
    END
    $$
    """,
    """
    CREATE FUNCTION app.enforce_knowledge_activation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      selected_review_status varchar(24);
      selected_published_at timestamptz;
    BEGIN
      IF NEW.status = 'published' THEN
        SELECT review_status, published_at
          INTO selected_review_status, selected_published_at
        FROM knowledge_versions
        WHERE tenant_id = NEW.tenant_id
          AND company_id = NEW.company_id
          AND document_id = NEW.id
          AND id = NEW.current_version_id;

        IF selected_review_status IS DISTINCT FROM 'approved'
           OR selected_published_at IS NULL THEN
          RAISE EXCEPTION 'published document requires its own approved version'
            USING ERRCODE = '23514';
        END IF;

        IF NOT EXISTS (
          SELECT 1
          FROM knowledge_chunks
          WHERE tenant_id = NEW.tenant_id
            AND company_id = NEW.company_id
            AND document_id = NEW.id
            AND version_id = NEW.current_version_id
        ) THEN
          RAISE EXCEPTION 'published document requires indexed chunks'
            USING ERRCODE = '23514';
        END IF;

        UPDATE knowledge_chunks
        SET is_active = (version_id = NEW.current_version_id)
        WHERE tenant_id = NEW.tenant_id
          AND company_id = NEW.company_id
          AND document_id = NEW.id;
      ELSIF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
        UPDATE knowledge_chunks
        SET is_active = false
        WHERE tenant_id = NEW.tenant_id
          AND company_id = NEW.company_id
          AND document_id = NEW.id;
      END IF;

      RETURN NEW;
    END
    $$
    """,
    """
    CREATE FUNCTION app.reject_audit_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      RAISE EXCEPTION 'audit logs are append-only'
        USING ERRCODE = '55000';
    END
    $$
    """,
    """
    CREATE TRIGGER trg_knowledge_versions_immutable
    BEFORE UPDATE ON knowledge_versions
    FOR EACH ROW EXECUTE FUNCTION app.guard_immutable_content()
    """,
    """
    CREATE TRIGGER trg_knowledge_chunks_immutable
    BEFORE UPDATE ON knowledge_chunks
    FOR EACH ROW EXECUTE FUNCTION app.guard_immutable_content()
    """,
    """
    CREATE TRIGGER trg_prompt_versions_immutable
    BEFORE UPDATE ON prompt_versions
    FOR EACH ROW EXECUTE FUNCTION app.guard_immutable_content()
    """,
    """
    CREATE TRIGGER trg_knowledge_documents_activation
    BEFORE INSERT OR UPDATE OF status, current_version_id ON knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION app.enforce_knowledge_activation()
    """,
    """
    CREATE TRIGGER trg_audit_logs_append_only
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION app.reject_audit_mutation()
    """,
)


UPDATED_AT_TABLES = (
    "tenants",
    "companies",
    "users",
    "memberships",
    "auth_sessions",
    "cards",
    "visitors",
    "visitor_profiles",
    "visits",
    "conversations",
    "prompt_versions",
    "model_configs",
    "knowledge_documents",
    "knowledge_versions",
    "knowledge_chunks",
    "knowledge_index_jobs",
    "knowledge_gaps",
    "visit_summaries",
    "idempotency_keys",
    "outbox_events",
)


COMPANY_SCOPED_TABLES = (
    "cards",
    "visitors",
    "visitor_profiles",
    "consent_records",
    "visits",
    "visit_events",
    "conversations",
    "messages",
    "prompt_versions",
    "model_configs",
    "ai_runs",
    "knowledge_documents",
    "knowledge_versions",
    "knowledge_chunks",
    "message_citations",
    "knowledge_index_jobs",
    "knowledge_gaps",
    "visit_summaries",
    "idempotency_keys",
    "audit_logs",
    "outbox_events",
)


def create_updated_at_triggers() -> None:
    for table_name in UPDATED_AT_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_touch_updated_at
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
            """
        )


def create_rls_policies() -> None:
    execute_all(
        (
            "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
            """
            CREATE POLICY tenants_scope_isolation ON tenants
            FOR ALL
            USING (id = app.current_tenant_id())
            WITH CHECK (id = app.current_tenant_id())
            """,
            "ALTER TABLE companies ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE companies FORCE ROW LEVEL SECURITY",
            """
            CREATE POLICY companies_scope_isolation ON companies
            FOR ALL
            USING (app.scope_matches(tenant_id, id))
            WITH CHECK (app.scope_matches(tenant_id, id))
            """,
            "ALTER TABLE memberships ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE memberships FORCE ROW LEVEL SECURITY",
            """
            CREATE POLICY memberships_scope_isolation ON memberships
            FOR ALL
            USING (
              tenant_id = app.current_tenant_id()
              AND company_id IS NOT DISTINCT FROM app.current_company_id()
            )
            WITH CHECK (
              tenant_id = app.current_tenant_id()
              AND company_id IS NOT DISTINCT FROM app.current_company_id()
            )
            """,
            "ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE auth_sessions FORCE ROW LEVEL SECURITY",
            """
            CREATE POLICY auth_sessions_scope_isolation ON auth_sessions
            FOR ALL
            USING (
              tenant_id = app.current_tenant_id()
              AND company_id IS NOT DISTINCT FROM app.current_company_id()
            )
            WITH CHECK (
              tenant_id = app.current_tenant_id()
              AND company_id IS NOT DISTINCT FROM app.current_company_id()
            )
            """,
        )
    )

    for table_name in COMPANY_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_scope_isolation ON {table_name}
            FOR ALL
            USING (app.scope_matches(tenant_id, company_id))
            WITH CHECK (app.scope_matches(tenant_id, company_id))
            """
        )

    op.execute(
        """
        CREATE POLICY cards_public_slug_select ON cards
        FOR SELECT
        USING (
          status = 'published'
          AND deleted_at IS NULL
          AND published_at IS NOT NULL
          AND published_at <= now()
          AND slug = app.current_card_slug()
        )
        """
    )


def grant_local_runtime_role_if_present() -> None:
    """Grant the non-owner local runtime role access without bypassing RLS.

    Hosted environments may use a differently named workload identity and apply
    equivalent grants outside this migration. The conditional block remains safe
    when the local role does not exist.
    """

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT USAGE ON SCHEMA public, app TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON ALL TABLES IN SCHEMA public TO cf_ai_card_app;
            GRANT USAGE, SELECT
              ON ALL SEQUENCES IN SCHEMA public TO cf_ai_card_app;
            GRANT EXECUTE
              ON ALL FUNCTIONS IN SCHEMA app TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def upgrade() -> None:
    execute_all(CORE_TABLE_DDL)
    execute_all(AI_AND_KNOWLEDGE_DDL)
    execute_all(RELIABILITY_DDL)
    execute_all(INDEX_DDL)
    execute_all(TRIGGER_DDL)
    create_updated_at_triggers()
    create_rls_policies()
    grant_local_runtime_role_if_present()


DROP_TABLES = (
    "outbox_events",
    "audit_logs",
    "idempotency_keys",
    "visit_summaries",
    "knowledge_gaps",
    "knowledge_index_jobs",
    "message_citations",
    "knowledge_chunks",
    "ai_runs",
    "model_configs",
    "prompt_versions",
    "messages",
    "conversations",
    "visit_events",
    "visits",
    "consent_records",
    "visitor_profiles",
    "visitors",
    "cards",
    "auth_sessions",
    "memberships",
    "users",
    "knowledge_versions",
    "knowledge_documents",
    "companies",
    "tenants",
)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS "
        "fk_knowledge_documents_current_version"
    )
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")

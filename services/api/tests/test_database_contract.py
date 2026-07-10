from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import ForeignKeyConstraint

from app.db.base import Base
from app.db.models import EMBEDDING_DIMENSION

API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"
MIGRATIONS = API_ROOT / "migrations"

REQUIRED_TABLES = {
    "tenants",
    "companies",
    "users",
    "memberships",
    "auth_sessions",
    "cards",
    "visitors",
    "visitor_profiles",
    "consent_records",
    "visits",
    "visit_events",
    "conversations",
    "messages",
    "ai_runs",
    "message_citations",
    "knowledge_documents",
    "knowledge_versions",
    "knowledge_chunks",
    "knowledge_index_jobs",
    "knowledge_gaps",
    "visit_summaries",
    "prompt_versions",
    "model_configs",
    "idempotency_keys",
    "audit_logs",
    "outbox_events",
}

COMPANY_SCOPED_TABLES = REQUIRED_TABLES - {
    "tenants",
    "companies",
    "users",
    "memberships",
    "auth_sessions",
}


@pytest.fixture(scope="module")
def migration_sql() -> str:
    """Render the complete migration using PostgreSQL's offline dialect.

    Alembic compiles every operation, model imports are exercised, and no
    database connection is opened.
    """

    output = StringIO()
    config = Config(str(ALEMBIC_INI), output_buffer=output)
    config.set_main_option("script_location", str(MIGRATIONS))
    offline_url = "postgresql+asyncpg://contract:contract@localhost/contract"
    with patch.dict(os.environ, {"DATABASE_URL": offline_url}):
        command.upgrade(config, "head", sql=True)
    return " ".join(output.getvalue().lower().split())


def test_model_metadata_covers_database_core() -> None:
    assert REQUIRED_TABLES <= set(Base.metadata.tables)


def test_company_owned_models_always_carry_both_scope_columns() -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        columns = set(Base.metadata.tables[table_name].columns.keys())
        assert {"tenant_id", "company_id"} <= columns, table_name


def test_cross_resource_links_use_composite_scope_foreign_keys() -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        table = Base.metadata.tables[table_name]
        scoped_fks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and {"tenant_id", "company_id"} <= {column.name for column in constraint.columns}
        ]
        assert scoped_fks, f"{table_name} lacks a tenant/company composite FK"


def test_hybrid_knowledge_chunk_model_contract() -> None:
    chunk = Base.metadata.tables["knowledge_chunks"]
    assert {"document_id", "version_id", "ordinal", "search_tsv"} <= set(chunk.columns.keys())
    assert EMBEDDING_DIMENSION == 1024
    assert chunk.c.embedding.type.dim == 1024
    assert chunk.c.embedding.nullable
    assert chunk.c.embedding_model.nullable
    assert chunk.c.search_tsv.computed is not None
    assert chunk.c.search_tsv.computed.persisted is True


def test_offline_migration_creates_required_extensions_and_tables(migration_sql: str) -> None:
    for extension in ("pgcrypto", "vector", "pg_trgm"):
        assert f"create extension if not exists {extension}" in migration_sql
    for table_name in REQUIRED_TABLES:
        assert f"create table {table_name}" in migration_sql


def test_offline_migration_freezes_hybrid_retrieval_contract(migration_sql: str) -> None:
    assert "embedding vector(1024)" in migration_sql
    assert "search_tsv tsvector generated always as" in migration_sql
    assert "using hnsw(embedding vector_cosine_ops)" in migration_sql
    assert "where embedding is not null" in migration_sql
    assert "using gin(search_tsv)" in migration_sql
    assert "gin_trgm_ops" in migration_sql


def test_rls_is_enabled_and_forced_for_every_company_table(migration_sql: str) -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        assert f"alter table {table_name} enable row level security" in migration_sql
        assert f"alter table {table_name} force row level security" in migration_sql
        assert f"create policy {table_name}_scope_isolation on {table_name}" in migration_sql
    assert "app.scope_matches(tenant_id, company_id)" in migration_sql


def test_public_card_policy_is_exact_slug_scope(migration_sql: str) -> None:
    assert "slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'" in migration_sql
    assert "create policy cards_public_slug_select on cards for select" in migration_sql
    assert "slug = app.current_card_slug()" in migration_sql
    public_policy = migration_sql.split("create policy cards_public_slug_select", 1)[1]
    public_policy = public_policy.split(";", 1)[0]
    assert " like " not in public_policy
    assert "status = 'published'" in public_policy


def test_active_document_requires_its_own_approved_version(migration_sql: str) -> None:
    assert "foreign key (tenant_id, company_id, id, current_version_id)" in migration_sql
    assert "references knowledge_versions(tenant_id, company_id, document_id, id)" in migration_sql
    assert "published document requires its own approved version" in migration_sql
    assert "selected_review_status is distinct from 'approved'" in migration_sql
    assert "new.status = 'published'" in migration_sql


def test_immutable_knowledge_and_append_only_audit_guards(migration_sql: str) -> None:
    assert "create trigger trg_knowledge_versions_immutable" in migration_sql
    assert "create trigger trg_knowledge_chunks_immutable" in migration_sql
    assert "new_row := to_jsonb(new)" in migration_sql
    assert "old_row := to_jsonb(old)" in migration_sql
    assert "knowledge version content is immutable" in migration_sql
    assert "active knowledge chunk embedding is immutable" in migration_sql
    assert "create trigger trg_audit_logs_append_only" in migration_sql
    assert "audit logs are append-only" in migration_sql


def test_reliability_tables_have_deduplication_contracts(migration_sql: str) -> None:
    assert "uq_idempotency_keys_scope_key" in migration_sql
    assert "uq_outbox_events_deduplication_key" in migration_sql
    assert "ck_outbox_events_published_state" in migration_sql
    assert "entry_hash varchar(64) not null" in migration_sql

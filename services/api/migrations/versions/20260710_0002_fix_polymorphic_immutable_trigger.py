"""Make the shared immutable-content trigger safe for every table row type.

Revision ID: 20260710_0002
Revises: 20260710_0001
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260710_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SAFE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION app.guard_immutable_content() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  new_row jsonb;
  old_row jsonb;
BEGIN
  -- NEW and OLD have a different composite type for each trigger target.
  -- Convert them once so a branch never tries to resolve a column that does
  -- not exist on another target table.
  new_row := to_jsonb(NEW);
  old_row := to_jsonb(OLD);

  IF TG_TABLE_NAME = 'knowledge_versions' AND (
    new_row -> 'tenant_id' IS DISTINCT FROM old_row -> 'tenant_id' OR
    new_row -> 'company_id' IS DISTINCT FROM old_row -> 'company_id' OR
    new_row -> 'document_id' IS DISTINCT FROM old_row -> 'document_id' OR
    new_row -> 'version_number' IS DISTINCT FROM old_row -> 'version_number' OR
    new_row -> 'raw_text' IS DISTINCT FROM old_row -> 'raw_text' OR
    new_row -> 'content_hash' IS DISTINCT FROM old_row -> 'content_hash'
  ) THEN
    RAISE EXCEPTION 'knowledge version content is immutable'
      USING ERRCODE = '55000';
  END IF;

  IF TG_TABLE_NAME = 'knowledge_chunks' AND (
    new_row -> 'tenant_id' IS DISTINCT FROM old_row -> 'tenant_id' OR
    new_row -> 'company_id' IS DISTINCT FROM old_row -> 'company_id' OR
    new_row -> 'document_id' IS DISTINCT FROM old_row -> 'document_id' OR
    new_row -> 'version_id' IS DISTINCT FROM old_row -> 'version_id' OR
    new_row -> 'ordinal' IS DISTINCT FROM old_row -> 'ordinal' OR
    new_row -> 'title' IS DISTINCT FROM old_row -> 'title' OR
    new_row -> 'text' IS DISTINCT FROM old_row -> 'text' OR
    new_row -> 'token_count' IS DISTINCT FROM old_row -> 'token_count' OR
    new_row -> 'source_type' IS DISTINCT FROM old_row -> 'source_type' OR
    new_row -> 'source_id' IS DISTINCT FROM old_row -> 'source_id' OR
    new_row -> 'content_hash' IS DISTINCT FROM old_row -> 'content_hash' OR
    new_row -> 'metadata' IS DISTINCT FROM old_row -> 'metadata'
  ) THEN
    RAISE EXCEPTION 'knowledge chunk source content is immutable'
      USING ERRCODE = '55000';
  END IF;

  IF TG_TABLE_NAME = 'knowledge_chunks'
     AND COALESCE((old_row ->> 'is_active')::boolean, false)
     AND (
       new_row -> 'embedding' IS DISTINCT FROM old_row -> 'embedding' OR
       new_row -> 'embedding_model' IS DISTINCT FROM old_row -> 'embedding_model'
     ) THEN
    RAISE EXCEPTION 'active knowledge chunk embedding is immutable'
      USING ERRCODE = '55000';
  END IF;

  IF TG_TABLE_NAME = 'prompt_versions' AND (
    new_row -> 'tenant_id' IS DISTINCT FROM old_row -> 'tenant_id' OR
    new_row -> 'company_id' IS DISTINCT FROM old_row -> 'company_id' OR
    new_row -> 'name' IS DISTINCT FROM old_row -> 'name' OR
    new_row -> 'purpose' IS DISTINCT FROM old_row -> 'purpose' OR
    new_row -> 'version_number' IS DISTINCT FROM old_row -> 'version_number' OR
    new_row -> 'content' IS DISTINCT FROM old_row -> 'content' OR
    new_row -> 'content_hash' IS DISTINCT FROM old_row -> 'content_hash'
  ) THEN
    RAISE EXCEPTION 'prompt version content is immutable'
      USING ERRCODE = '55000';
  END IF;

  RETURN NEW;
END
$$
"""


LEGACY_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION app.guard_immutable_content() RETURNS trigger
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
    RAISE EXCEPTION 'knowledge version content is immutable' USING ERRCODE = '55000';
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
    RAISE EXCEPTION 'knowledge chunk source content is immutable' USING ERRCODE = '55000';
  END IF;
  IF TG_TABLE_NAME = 'knowledge_chunks' AND OLD.is_active AND (
    NEW.embedding IS DISTINCT FROM OLD.embedding OR
    NEW.embedding_model IS DISTINCT FROM OLD.embedding_model
  ) THEN
    RAISE EXCEPTION 'active knowledge chunk embedding is immutable' USING ERRCODE = '55000';
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
    RAISE EXCEPTION 'prompt version content is immutable' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END
$$
"""


def upgrade() -> None:
    op.execute(SAFE_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(LEGACY_TRIGGER_FUNCTION)

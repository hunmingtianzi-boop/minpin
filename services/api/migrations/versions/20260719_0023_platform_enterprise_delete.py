"""Add a safe platform operation for removing an enterprise.

Revision ID: 20260719_0023
Revises: 20260717_0022
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260719_0023"
down_revision: str | None = "20260717_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_delete_enterprise(
          p_company_id uuid,
          p_expected_version integer
        ) RETURNS jsonb
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE
          target record;
          previous_audit_hash text;
          changed_at timestamptz := pg_catalog.now();
          actor_user_id uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF p_expected_version IS NULL OR p_expected_version < 1 THEN
            RAISE EXCEPTION 'invalid enterprise version'
              USING ERRCODE = '22023';
          END IF;

          PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('platform-enterprise-delete:' || p_company_id, 0)
          );
          SELECT tenant.id AS tenant_id, company.version
            INTO target
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
           WHERE company.id = p_company_id
             AND tenant.type = 'enterprise'
             AND tenant.deleted_at IS NULL
             AND company.deleted_at IS NULL
             AND COALESCE(tenant.settings ->> 'onboarding_status', '') <> 'provisional'
             AND COALESCE(company.settings ->> 'onboarding_status', '') <> 'provisional'
           FOR UPDATE OF company, tenant;

          IF NOT FOUND THEN
            RETURN pg_catalog.jsonb_build_object('outcome', 'not_found');
          END IF;
          IF target.version <> p_expected_version THEN
            RETURN pg_catalog.jsonb_build_object('outcome', 'version_conflict');
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.companies AS sibling
            WHERE sibling.tenant_id = target.tenant_id
              AND sibling.id <> p_company_id
              AND sibling.deleted_at IS NULL
          ) THEN
            RETURN pg_catalog.jsonb_build_object('outcome', 'shared_tenant');
          END IF;

          UPDATE public.knowledge_import_items
             SET status = 'dead_letter',
                 parse_status = CASE
                   WHEN parse_status = 'completed' THEN parse_status ELSE 'failed'
                 END,
                 error_code = 'IMPORT_ENTERPRISE_DELETED',
                 completed_at = changed_at,
                 lock_token = NULL,
                 locked_by = NULL,
                 lease_expires_at = NULL,
                 updated_at = changed_at
           WHERE company_id = p_company_id
             AND status IN ('pending', 'processing');
          UPDATE public.knowledge_import_batches AS batch
             SET status = 'dead_letter',
                 pending_items = 0,
                 failed_items = batch.total_items - batch.succeeded_items,
                 completed_at = changed_at,
                 updated_at = changed_at
           WHERE batch.company_id = p_company_id
             AND batch.status IN ('pending', 'processing');
          UPDATE public.auth_sessions
             SET revoked_at = changed_at,
                 revoke_reason = 'enterprise_deleted',
                 updated_at = changed_at
           WHERE company_id = p_company_id
             AND revoked_at IS NULL;
          UPDATE public.staff_credentials
             SET is_enabled = false,
                 locked_until = NULL,
                 updated_at = changed_at
           WHERE company_id = p_company_id;
          UPDATE public.memberships
             SET status = 'disabled',
                 updated_at = changed_at
           WHERE company_id = p_company_id;
          UPDATE public.cards
             SET status = 'archived',
                 published_at = NULL,
                 deleted_at = changed_at,
                 deleted_by = actor_user_id,
                 version = version + 1,
                 updated_at = changed_at
           WHERE company_id = p_company_id
             AND deleted_at IS NULL;
          UPDATE public.companies
             SET status = 'disabled',
                 deleted_at = changed_at,
                 deleted_by = actor_user_id,
                 version = version + 1,
                 updated_at = changed_at
           WHERE id = p_company_id;
          UPDATE public.tenants
             SET status = 'disabled',
                 deleted_at = changed_at,
                 deleted_by = actor_user_id,
                 updated_at = changed_at
           WHERE id = target.tenant_id;

          PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(
              target.tenant_id::text || pg_catalog.chr(58)
              || p_company_id::text || pg_catalog.chr(58) || 'audit', 0
            )
          );
          SELECT audit.entry_hash INTO previous_audit_hash
            FROM public.audit_logs AS audit
           WHERE audit.tenant_id = target.tenant_id
             AND audit.company_id = p_company_id
           ORDER BY audit.created_at DESC, audit.id DESC
           LIMIT 1;

          RETURN pg_catalog.jsonb_build_object(
            'outcome', 'succeeded',
            'tenant_id', target.tenant_id,
            'company_id', p_company_id,
            'version', target.version + 1,
            'deleted_at', changed_at,
            'previous_audit_hash', previous_audit_hash
          );
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_delete_enterprise(uuid, integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION app.platform_operations_delete_enterprise(uuid, integer)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_operations_delete_enterprise(uuid, integer)"
    )

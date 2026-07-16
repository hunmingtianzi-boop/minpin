"""Bind platform onboarding sessions to their creating administrator.

Revision ID: 20260717_0022
Revises: 20260715_0021
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260717_0022"
down_revision: str | None = "20260715_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESOURCE_LINKS = (
    ("tenants", "tenant_id", "id"),
    ("companies", "company_id", "id"),
    ("users", "admin_user_id", "id"),
    ("memberships", "admin_membership_id", "id"),
    ("staff_credentials", "credential_id", "id"),
    ("cards", "initial_card_id", "id"),
)
_OWNER_PREDICATE = (
    "created_by = NULLIF(current_setting('app.user_id', true), '')::uuid"
)


def _replace_policies(*, owner_scoped: bool) -> None:
    op.execute(
        "DROP POLICY platform_onboarding_platform_only "
        "ON platform_onboarding_sessions"
    )
    predicate = "app.platform_actor_allowed()"
    if owner_scoped:
        predicate += f" AND {_OWNER_PREDICATE}"
    op.execute(
        "CREATE POLICY platform_onboarding_platform_only "
        "ON platform_onboarding_sessions FOR ALL "
        f"USING ({predicate}) WITH CHECK ({predicate})"  # noqa: S608
    )

    for table, link_column, resource_column in _RESOURCE_LINKS:
        select_policy = f"{table}_platform_onboarding_select"
        update_policy = f"{table}_platform_onboarding_update"
        op.execute(f"DROP POLICY {select_policy} ON {table}")  # noqa: S608
        op.execute(f"DROP POLICY {update_policy} ON {table}")  # noqa: S608
        scope_predicate = (
            "app.platform_actor_allowed() AND EXISTS ("  # noqa: S608
            "SELECT 1 FROM platform_onboarding_sessions AS onboarding "
            f"WHERE onboarding.{link_column} = {table}.{resource_column} "  # noqa: S608
            "AND onboarding.status IN "
            "('draft','processing','review','manual_required','ready_to_confirm')"
        )
        if owner_scoped:
            scope_predicate += (
                " AND onboarding.created_by = "
                "NULLIF(current_setting('app.user_id', true), '')::uuid"
            )
        scope_predicate += ")"
        op.execute(
            f"CREATE POLICY {select_policy} ON {table} FOR SELECT "  # noqa: S608
            f"USING ({scope_predicate})"  # noqa: S608
        )
        op.execute(
            f"CREATE POLICY {update_policy} ON {table} FOR UPDATE "  # noqa: S608
            f"USING ({scope_predicate}) "  # noqa: S608
            f"WITH CHECK ({scope_predicate if owner_scoped else predicate})"  # noqa: S608
        )


def _replace_functions(*, owner_scoped: bool) -> None:
    owner_clause = ""
    if owner_scoped:
        owner_clause = (
            " AND onboarding.created_by = "
            "NULLIF(current_setting('app.user_id', true), '')::uuid"
        )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION app.platform_onboarding_imports_settled(
          p_session_id uuid
        )
        RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          result boolean;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          SELECT CASE
            WHEN pg_catalog.cardinality(onboarding.import_batch_ids) = 0 THEN true
            ELSE (
              SELECT pg_catalog.count(*) = pg_catalog.cardinality(
                       onboarding.import_batch_ids
                     )
                     AND pg_catalog.bool_and(
                       batch.status NOT IN ('pending', 'processing')
                     )
              FROM public.knowledge_import_batches AS batch
              WHERE batch.id = ANY(onboarding.import_batch_ids)
                AND batch.tenant_id = onboarding.tenant_id
                AND batch.company_id = onboarding.company_id
            )
          END INTO result
          FROM public.platform_onboarding_sessions AS onboarding
          WHERE onboarding.id = p_session_id{owner_clause};
          RETURN COALESCE(result, false);
        END
        $$
        """  # noqa: S608
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION app.platform_onboarding_drafts(p_session_id uuid)
        RETURNS TABLE(
          import_item_id uuid,
          file_name text,
          document_id uuid,
          raw_text text
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          RETURN QUERY
          SELECT
            item.id,
            item.file_name::text,
            item.document_id,
            pg_catalog.left(version.raw_text, 20000)
          FROM public.platform_onboarding_sessions AS onboarding
          JOIN public.knowledge_import_items AS item
            ON item.batch_id = ANY(onboarding.import_batch_ids)
           AND item.tenant_id = onboarding.tenant_id
           AND item.company_id = onboarding.company_id
          JOIN public.knowledge_versions AS version
            ON version.id = item.version_id
           AND version.tenant_id = onboarding.tenant_id
           AND version.company_id = onboarding.company_id
          WHERE onboarding.id = p_session_id{owner_clause}
            AND onboarding.status IN
              ('processing','review','manual_required','ready_to_confirm')
            AND item.status = 'completed'
          ORDER BY item.created_at, item.id
          LIMIT 10;
        END
        $$
        """  # noqa: S608
    )


def upgrade() -> None:
    _replace_policies(owner_scoped=True)
    _replace_functions(owner_scoped=True)


def downgrade() -> None:
    _replace_policies(owner_scoped=False)
    _replace_functions(owner_scoped=False)

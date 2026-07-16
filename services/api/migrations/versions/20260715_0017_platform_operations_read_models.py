"""Add allowlisted platform operations read models.

Revision ID: 20260715_0017
Revises: 20260715_0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260715_0017"
down_revision: str | None = "20260715_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_overview() RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          SELECT pg_catalog.jsonb_build_object(
            'generated_at', pg_catalog.now(),
            'enterprise_count', (
              SELECT pg_catalog.count(*)
              FROM public.companies AS company
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE tenant.type = 'enterprise'
                AND tenant.deleted_at IS NULL
                AND company.deleted_at IS NULL
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'active_enterprise_count', (
              SELECT pg_catalog.count(*)
              FROM public.companies AS company
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE tenant.type = 'enterprise'
                AND tenant.deleted_at IS NULL
                AND company.deleted_at IS NULL
                AND company.status = 'active'
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'onboarding_count', (
              SELECT pg_catalog.count(*)
              FROM public.companies AS company
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE tenant.type = 'enterprise'
                AND tenant.deleted_at IS NULL
                AND company.deleted_at IS NULL
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', 'not_started'
                ) NOT IN ('completed', 'active')
            ),
            'published_card_count', (
              SELECT pg_catalog.count(*)
              FROM public.cards AS card
              JOIN public.companies AS company ON company.id = card.company_id
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE card.deleted_at IS NULL
                AND tenant.type = 'enterprise'
                AND company.deleted_at IS NULL
                AND tenant.deleted_at IS NULL
                AND card.status = 'published'
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'visits_30d', (
              SELECT pg_catalog.count(*)
              FROM public.visits AS visit
              JOIN public.companies AS company ON company.id = visit.company_id
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE visit.started_at >= pg_catalog.now() - interval '30 days'
                AND tenant.type = 'enterprise'
                AND company.deleted_at IS NULL
                AND tenant.deleted_at IS NULL
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'conversations_30d', (
              SELECT pg_catalog.count(*)
              FROM public.conversations AS conversation
              JOIN public.companies AS company ON company.id = conversation.company_id
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE conversation.started_at >= pg_catalog.now() - interval '30 days'
                AND tenant.type = 'enterprise'
                AND company.deleted_at IS NULL
                AND tenant.deleted_at IS NULL
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'leads_30d', (
              SELECT pg_catalog.count(*)
              FROM public.leads AS lead
              JOIN public.companies AS company ON company.id = lead.company_id
              JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
              WHERE lead.created_at >= pg_catalog.now() - interval '30 days'
                AND tenant.type = 'enterprise'
                AND company.deleted_at IS NULL
                AND tenant.deleted_at IS NULL
                AND pg_catalog.coalesce(
                  tenant.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
                AND pg_catalog.coalesce(
                  company.settings ->> 'onboarding_status', ''
                ) <> 'provisional'
            ),
            'failed_task_count', (
              (SELECT pg_catalog.count(*)
               FROM public.outbox_events AS event
               JOIN public.companies AS company ON company.id = event.company_id
               JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
               WHERE event.status IN ('failed', 'dead_letter')
                 AND tenant.type = 'enterprise'
                 AND company.deleted_at IS NULL
                 AND tenant.deleted_at IS NULL
                 AND pg_catalog.coalesce(
                   tenant.settings ->> 'onboarding_status', ''
                 ) <> 'provisional'
                 AND pg_catalog.coalesce(
                   company.settings ->> 'onboarding_status', ''
                 ) <> 'provisional')
              +
              (SELECT pg_catalog.count(*)
               FROM public.knowledge_import_batches AS batch
               JOIN public.companies AS company ON company.id = batch.company_id
               JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
               WHERE batch.status IN ('failed', 'dead_letter')
                 AND tenant.type = 'enterprise'
                 AND company.deleted_at IS NULL
                 AND tenant.deleted_at IS NULL
                 AND pg_catalog.coalesce(
                   tenant.settings ->> 'onboarding_status', ''
                 ) <> 'provisional'
                 AND pg_catalog.coalesce(
                   company.settings ->> 'onboarding_status', ''
                 ) <> 'provisional')
            ),
            'llm_ready', (
              SELECT EXISTS (
                SELECT 1 FROM public.platform_llm_profiles AS profile
                WHERE profile.enabled AND profile.is_active
              )
            ),
            'import_ready', (
              pg_catalog.to_regclass('public.knowledge_import_batches') IS NOT NULL
            )
          ) INTO result;
          RETURN result;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_enterprises(
          p_search text,
          p_status text,
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          result jsonb;
          normalized_search text := pg_catalog.nullif(pg_catalog.btrim(p_search), '');
          normalized_status text := pg_catalog.nullif(pg_catalog.btrim(p_status), '');
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF p_limit IS NULL OR p_offset IS NULL
             OR p_limit < 1 OR p_limit > 100 OR p_offset < 0 THEN
            RAISE EXCEPTION 'invalid platform enterprise pagination'
              USING ERRCODE = '22023';
          END IF;
          IF pg_catalog.length(pg_catalog.coalesce(p_search, '')) > 200 THEN
            RAISE EXCEPTION 'platform enterprise search is too long'
              USING ERRCODE = '22023';
          END IF;
          IF normalized_status IS NOT NULL
             AND normalized_status NOT IN ('active', 'suspended', 'disabled') THEN
            RAISE EXCEPTION 'invalid platform enterprise status'
              USING ERRCODE = '22023';
          END IF;

          WITH matching AS (
            SELECT
              tenant.id AS tenant_id,
              tenant.slug AS tenant_slug,
              tenant.name AS tenant_name,
              company.id AS company_id,
              company.name AS company_name,
              company.status::text AS status,
              company.created_at
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND tenant.deleted_at IS NULL
              AND company.deleted_at IS NULL
              AND pg_catalog.coalesce(
                tenant.settings ->> 'onboarding_status', ''
              ) <> 'provisional'
              AND pg_catalog.coalesce(
                company.settings ->> 'onboarding_status', ''
              ) <> 'provisional'
              AND (
                normalized_status IS NULL
                OR company.status::text = normalized_status
              )
              AND (
                normalized_search IS NULL
                OR pg_catalog.strpos(
                  pg_catalog.lower(tenant.name), pg_catalog.lower(normalized_search)
                ) > 0
                OR pg_catalog.strpos(
                  pg_catalog.lower(tenant.slug), pg_catalog.lower(normalized_search)
                ) > 0
                OR pg_catalog.strpos(
                  pg_catalog.lower(company.name), pg_catalog.lower(normalized_search)
                ) > 0
              )
          ), page AS (
            SELECT * FROM matching
            ORDER BY created_at DESC, company_id DESC
            LIMIT p_limit OFFSET p_offset
          )
          SELECT pg_catalog.jsonb_build_object(
            'data', pg_catalog.coalesce(
              (
                SELECT pg_catalog.jsonb_agg(
                  pg_catalog.jsonb_build_object(
                    'tenant_id', row.tenant_id,
                    'tenant_slug', row.tenant_slug,
                    'tenant_name', row.tenant_name,
                    'company_id', row.company_id,
                    'company_name', row.company_name,
                    'status', row.status,
                    'created_at', row.created_at
                  ) ORDER BY row.created_at DESC, row.company_id DESC
                ) FROM page AS row
              ),
              '[]'::jsonb
            ),
            'total', (SELECT pg_catalog.count(*) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_enterprise_detail(
          p_company_id uuid,
          p_public_card_base_url text
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          result jsonb;
          normalized_base_url text := pg_catalog.rtrim(p_public_card_base_url, '/');
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF normalized_base_url IS NULL
             OR normalized_base_url = ''
             OR pg_catalog.length(normalized_base_url) > 2048
             OR normalized_base_url !~ '^https?://[^/]+'
             OR normalized_base_url ~ '[[:space:]@?#]' THEN
            RAISE EXCEPTION 'invalid public card base URL'
              USING ERRCODE = '22023';
          END IF;

          WITH target AS (
            SELECT
              tenant.id AS tenant_id,
              tenant.slug AS tenant_slug,
              tenant.name AS tenant_name,
              company.id AS company_id,
              company.name AS company_name,
              company.status::text AS status,
              company.version,
              company.industry,
              company.settings,
              company.created_at,
              company.updated_at
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE company.id = p_company_id
              AND tenant.type = 'enterprise'
              AND tenant.deleted_at IS NULL
              AND company.deleted_at IS NULL
              AND pg_catalog.coalesce(
                tenant.settings ->> 'onboarding_status', ''
              ) <> 'provisional'
              AND pg_catalog.coalesce(
                company.settings ->> 'onboarding_status', ''
              ) <> 'provisional'
          )
          SELECT pg_catalog.jsonb_build_object(
            'tenant_id', target.tenant_id,
            'tenant_slug', target.tenant_slug,
            'tenant_name', target.tenant_name,
            'company_id', target.company_id,
            'company_name', target.company_name,
            'status', target.status,
            'version', target.version,
            'onboarding_status', pg_catalog.coalesce(
              target.settings ->> 'onboarding_status', 'not_started'
            ),
            'profile_completion',
              (CASE WHEN pg_catalog.btrim(target.company_name) <> '' THEN 20 ELSE 0 END)
              + (CASE WHEN pg_catalog.nullif(pg_catalog.btrim(target.industry), '')
                        IS NOT NULL THEN 20 ELSE 0 END)
              + (CASE WHEN pg_catalog.nullif(
                          pg_catalog.btrim(target.settings ->> 'summary'), ''
                        ) IS NOT NULL THEN 20 ELSE 0 END)
              + (CASE WHEN pg_catalog.nullif(
                          pg_catalog.btrim(target.settings ->> 'website'), ''
                        ) IS NOT NULL THEN 20 ELSE 0 END)
              + (CASE WHEN pg_catalog.nullif(
                          pg_catalog.btrim(target.settings ->> 'logo_url'), ''
                        ) IS NOT NULL THEN 20 ELSE 0 END),
            'employee_count', (
              SELECT pg_catalog.count(*) FROM public.memberships AS membership
              WHERE membership.company_id = target.company_id
                AND membership.status = 'active'
            ),
            'card_count', (
              SELECT pg_catalog.count(*) FROM public.cards AS card
              WHERE card.company_id = target.company_id AND card.deleted_at IS NULL
            ),
            'published_card_count', (
              SELECT pg_catalog.count(*) FROM public.cards AS card
              WHERE card.company_id = target.company_id
                AND card.deleted_at IS NULL AND card.status = 'published'
            ),
            'visits_30d', (
              SELECT pg_catalog.count(*) FROM public.visits AS visit
              WHERE visit.company_id = target.company_id
                AND visit.started_at >= pg_catalog.now() - interval '30 days'
            ),
            'conversations_30d', (
              SELECT pg_catalog.count(*) FROM public.conversations AS conversation
              WHERE conversation.company_id = target.company_id
                AND conversation.started_at >= pg_catalog.now() - interval '30 days'
            ),
            'leads_30d', (
              SELECT pg_catalog.count(*) FROM public.leads AS lead
              WHERE lead.company_id = target.company_id
                AND lead.created_at >= pg_catalog.now() - interval '30 days'
            ),
            'cards', pg_catalog.coalesce(
              (
                SELECT pg_catalog.jsonb_agg(
                  pg_catalog.jsonb_build_object(
                    'id', card.id,
                    'display_name', card.display_name,
                    'title', pg_catalog.coalesce(card.settings ->> 'title', ''),
                    'status', card.status::text,
                    'updated_at', card.updated_at,
                    'share_url', CASE WHEN card.status = 'published'
                      THEN normalized_base_url || '/c/' || card.slug
                      ELSE NULL
                    END
                  ) ORDER BY card.updated_at DESC, card.id DESC
                )
                FROM public.cards AS card
                WHERE card.company_id = target.company_id AND card.deleted_at IS NULL
              ),
              '[]'::jsonb
            ),
            'created_at', target.created_at,
            'updated_at', target.updated_at
          ) INTO result
          FROM target;
          RETURN result;
        END
        $$
        """
    )

    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_company_aggregates(
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF p_limit IS NULL OR p_offset IS NULL
             OR p_limit < 1 OR p_limit > 100 OR p_offset < 0 THEN
            RAISE EXCEPTION 'invalid platform aggregate pagination'
              USING ERRCODE = '22023';
          END IF;
          WITH matching AS (
            SELECT
              company.id AS company_id,
              company.name AS company_name,
              pg_catalog.count(DISTINCT membership.id) FILTER (
                WHERE membership.status = 'active'
              ) AS employee_count,
              pg_catalog.count(DISTINCT visit.id) FILTER (
                WHERE visit.started_at >= pg_catalog.now() - interval '30 days'
              ) AS visits_30d,
              pg_catalog.count(DISTINCT visit.visitor_id) FILTER (
                WHERE visit.started_at >= pg_catalog.now() - interval '30 days'
              ) AS unique_visitors_30d,
              pg_catalog.max(visit.started_at) AS last_visit_at
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            LEFT JOIN public.memberships AS membership
              ON membership.company_id = company.id
            LEFT JOIN public.visits AS visit ON visit.company_id = company.id
            WHERE tenant.type = 'enterprise'
              AND tenant.deleted_at IS NULL
              AND company.deleted_at IS NULL
              AND pg_catalog.coalesce(tenant.settings ->> 'onboarding_status', '')
                <> 'provisional'
              AND pg_catalog.coalesce(company.settings ->> 'onboarding_status', '')
                <> 'provisional'
            GROUP BY company.id, company.name
          ), page AS (
            SELECT * FROM matching
            ORDER BY company_name, company_id
            LIMIT p_limit OFFSET p_offset
          )
          SELECT pg_catalog.jsonb_build_object(
            'data', pg_catalog.coalesce(
              (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT pg_catalog.count(*) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_tasks(
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          WITH tasks AS (
            SELECT event.id, 'outbox'::text AS task_type,
              CASE
                WHEN event.event_type = 'enterprise.created.v1' THEN '企业创建事件'
                ELSE '业务事件投递'
              END AS business_label,
              event.status::text AS status,
              company.id AS company_id, company.name AS company_name,
              CASE WHEN event.status IN ('failed','dead_letter')
                THEN 'DELIVERY_FAILED' ELSE NULL END AS error_code,
              event.created_at, event.updated_at
            FROM public.outbox_events AS event
            JOIN public.companies AS company ON company.id = event.company_id
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND company.deleted_at IS NULL AND tenant.deleted_at IS NULL
              AND pg_catalog.coalesce(company.settings ->> 'onboarding_status', '')
                <> 'provisional'
            UNION ALL
            SELECT batch.id, 'knowledge_import'::text, '资料导入',
              batch.status::text, company.id, company.name,
              CASE WHEN batch.status IN ('failed','dead_letter')
                THEN 'IMPORT_FAILED' ELSE NULL END,
              batch.created_at, batch.updated_at
            FROM public.knowledge_import_batches AS batch
            JOIN public.companies AS company ON company.id = batch.company_id
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND company.deleted_at IS NULL AND tenant.deleted_at IS NULL
              AND pg_catalog.coalesce(company.settings ->> 'onboarding_status', '')
                <> 'provisional'
          ), page AS (
            SELECT * FROM tasks
            ORDER BY created_at DESC, id DESC
            LIMIT p_limit OFFSET p_offset
          )
          SELECT pg_catalog.jsonb_build_object(
            'data', pg_catalog.coalesce(
              (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT pg_catalog.count(*) FROM tasks)
          ) INTO result;
          RETURN result;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_audit(
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          WITH entries AS (
            SELECT audit.id,
              CASE WHEN audit.action LIKE 'platform.%'
                THEN '平台管理员' ELSE '企业成员' END AS actor_display_name,
              audit.action,
              CASE
                WHEN audit.action = 'platform.enterprise.create' THEN '创建企业'
                WHEN audit.action = 'platform.onboarding.start' THEN '开始资料建企'
                WHEN audit.action = 'platform.onboarding.confirm' THEN '确认资料建企'
                WHEN audit.action = 'platform.onboarding.cancel' THEN '取消资料建企'
                WHEN audit.action = 'platform.enterprise.suspend' THEN '暂停企业'
                WHEN audit.action = 'platform.enterprise.resume' THEN '恢复企业'
                ELSE '业务操作'
              END AS business_label,
              audit.resource_type, audit.resource_id,
              'recorded'::text AS result, audit.created_at
            FROM public.audit_logs AS audit
            JOIN public.companies AS company ON company.id = audit.company_id
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND company.deleted_at IS NULL AND tenant.deleted_at IS NULL
              AND pg_catalog.coalesce(company.settings ->> 'onboarding_status', '')
                <> 'provisional'
          ), page AS (
            SELECT * FROM entries
            ORDER BY created_at DESC, id DESC
            LIMIT p_limit OFFSET p_offset
          )
          SELECT pg_catalog.jsonb_build_object(
            'data', pg_catalog.coalesce(
              (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT pg_catalog.count(*) FROM entries)
          ) INTO result;
          RETURN result;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.platform_operations_transition_enterprise(
          p_company_id uuid,
          p_expected_version integer,
          p_target_status text
        ) RETURNS jsonb
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE
          target record;
          previous_audit_hash text;
          changed_at timestamptz := pg_catalog.now();
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF p_expected_version IS NULL OR p_expected_version < 1
             OR p_target_status IS NULL
             OR p_target_status NOT IN ('active', 'suspended') THEN
            RAISE EXCEPTION 'invalid enterprise lifecycle transition'
              USING ERRCODE = '22023';
          END IF;

          PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('platform-enterprise-lifecycle:' || p_company_id, 0)
          );
          SELECT tenant.id AS tenant_id, company.status::text AS current_status,
                 company.version
            INTO target
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
           WHERE company.id = p_company_id
             AND tenant.type = 'enterprise'
             AND tenant.deleted_at IS NULL
             AND company.deleted_at IS NULL
             AND pg_catalog.coalesce(tenant.settings ->> 'onboarding_status', '')
                 <> 'provisional'
             AND pg_catalog.coalesce(company.settings ->> 'onboarding_status', '')
                 <> 'provisional'
           FOR UPDATE OF company, tenant;

          IF NOT FOUND THEN
            RETURN pg_catalog.jsonb_build_object('outcome', 'not_found');
          END IF;
          IF target.version <> p_expected_version THEN
            RETURN pg_catalog.jsonb_build_object(
              'outcome', 'version_conflict',
              'current_status', target.current_status,
              'current_version', target.version
            );
          END IF;
          IF target.current_status = p_target_status THEN
            RETURN pg_catalog.jsonb_build_object(
              'outcome', 'unchanged',
              'tenant_id', target.tenant_id,
              'company_id', p_company_id,
              'previous_status', target.current_status,
              'status', target.current_status,
              'version', target.version,
              'updated_at', changed_at
            );
          END IF;

          UPDATE public.companies
             SET status = p_target_status::public.company_status,
                 version = version + 1,
                 updated_at = changed_at
           WHERE id = p_company_id;
          UPDATE public.tenants
             SET status = p_target_status::public.tenant_status,
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
            'previous_status', target.current_status,
            'status', p_target_status,
            'version', target.version + 1,
            'updated_at', changed_at,
            'previous_audit_hash', previous_audit_hash
          );
        END
        $$
        """
    )

    op.execute(
        "REVOKE ALL ON FUNCTION app.platform_operations_overview() FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_company_aggregates(integer, integer) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_tasks(integer, integer) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_audit(integer, integer) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_transition_enterprise(uuid, integer, text) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_enterprises(text, text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_enterprise_detail(uuid, text) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION app.platform_operations_overview()
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_company_aggregates(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_tasks(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_audit(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_transition_enterprise(uuid, integer, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_enterprises(text, text, integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_enterprise_detail(uuid, text)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "app.platform_operations_transition_enterprise(uuid, integer, text)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_operations_audit(integer, integer)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_operations_tasks(integer, integer)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "app.platform_operations_company_aggregates(integer, integer)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.platform_operations_enterprise_detail(uuid, text)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "app.platform_operations_enterprises(text, text, integer, integer)"
    )
    op.execute("DROP FUNCTION IF EXISTS app.platform_operations_overview()")

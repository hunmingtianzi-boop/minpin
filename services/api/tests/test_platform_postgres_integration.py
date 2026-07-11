from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.errors import ApiError
from app.api.platform_schemas import CreateEnterpriseRequest
from app.core.config import Settings
from app.services.platform_store import PlatformActor, PlatformStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
        reason="set RUN_PLATFORM_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_platform_admin_can_onboard_a_login_ready_enterprise_through_rls() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    actor_tenant_id, actor_company_id, actor_user_id, membership_id, session_id = [
        uuid.uuid4() for _ in range(5)
    ]
    actor_slug = f"platform-integration-{uuid.uuid4().hex[:10]}"
    enterprise_slug = f"enterprise-integration-{uuid.uuid4().hex[:10]}"
    try:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO tenants(id,slug,name,type,status,settings) "
                    "VALUES (:id,:slug,'Platform Integration','chamber','active','{}')"
                ),
                {"id": actor_tenant_id, "slug": actor_slug},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) "
                    "VALUES (:id,:tenant_id,'Platform Integration',"
                    "'platform integration','active','{}')"
                ),
                {"id": actor_company_id, "tenant_id": actor_tenant_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,'Platform Integration','active')"
                ),
                {"id": actor_user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO memberships("
                    "id,user_id,tenant_id,company_id,role,permissions,status) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,'platform_admin',"
                    "ARRAY['*'],'active')"
                ),
                {
                    "id": membership_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions(id,user_id,tenant_id,company_id,"
                    "refresh_token_hash,expires_at) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:token_hash,:expires_at)"
                ),
                {
                    "id": session_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                    "token_hash": uuid.uuid4().hex,
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )

        store = PlatformStore(sessions, settings)
        actor = PlatformActor(
            user_id=actor_user_id,
            tenant_id=actor_tenant_id,
            company_id=actor_company_id,
            session_id=session_id,
            role="platform_admin",
        )
        body = CreateEnterpriseRequest(
            tenant_slug=enterprise_slug,
            tenant_name="Integration Enterprise",
            company_name="Integration Enterprise Co",
            industry="AI",
            admin_account=f"{enterprise_slug}@example.test",
            admin_display_name="Integration Admin",
            admin_password=SecretStr("Integration-Password-2026!"),
            initial_card_title="Integration Card",
        )
        created = await store.create_enterprise(
            actor=actor,
            body=body,
            trace_id="platform-postgres-integration",
        )
        rows, _ = await store.list_enterprises(actor=actor, limit=100, offset=0)
        assert enterprise_slug in {row.tenant_slug for row in rows}
        with pytest.raises(ApiError) as duplicate:
            await store.create_enterprise(
                actor=actor,
                body=body.model_copy(
                    update={"admin_account": f"other-{enterprise_slug}@example.test"}
                ),
                trace_id="platform-postgres-integration-duplicate",
            )
        assert duplicate.value.code == "TENANT_SLUG_CONFLICT"

        async with owner.connect() as connection:
            counts = (
                await connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM cards WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM memberships WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM staff_credentials WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM outbox_events WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM audit_logs WHERE company_id=:company_id)"
                    ),
                    {"company_id": created.company_id},
                )
            ).one()
        assert tuple(counts) == (1, 1, 1, 1, 1)
    finally:
        await runtime.dispose()
        await owner.dispose()

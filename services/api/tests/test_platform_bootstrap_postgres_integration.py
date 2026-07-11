from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli.bootstrap_platform_admin import (
    PlatformBootstrapInput,
    bootstrap_platform_admin,
)
from app.core.config import Settings
from app.db.models import AuditLog
from app.services.auth_store import AuthStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
        reason="set RUN_PLATFORM_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_audited_and_login_ready() -> None:
    settings = Settings()
    suffix = uuid.uuid4().hex[:12]
    account = f"platform-{suffix}@example.test"
    password = "Integration-Platform-Password-2026!"  # noqa: S105
    bootstrap = PlatformBootstrapInput(
        _env_file=None,
        tenant_slug="template",
        account=account,
        password=password,
        display_name="Platform Integration Admin",
        confirm="CREATE_FIRST_PLATFORM_ADMIN",
    )

    first = await bootstrap_platform_admin(settings, bootstrap)
    second = await bootstrap_platform_admin(settings, bootstrap)

    assert first.created is True
    assert second.created is False
    assert second.tenant_id == first.tenant_id
    assert second.company_id == first.company_id
    assert second.user_id == first.user_id
    assert second.membership_id == first.membership_id

    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    try:
        authentication = await AuthStore(
            async_sessionmaker(runtime, expire_on_commit=False),
            settings,
        ).login(account=account, credential=password)
        assert authentication.identity.role == "platform_admin"
        assert authentication.identity.permissions == ("*",)

        async with owner.connect() as connection:
            action = await connection.scalar(
                select(AuditLog.action).where(
                    AuditLog.resource_id == uuid.UUID(first.membership_id)
                )
            )
        assert action == "platform.admin.bootstrap"
    finally:
        await runtime.dispose()
        await owner.dispose()

# ruff: noqa: E501
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cf_worker.config import WorkerSettings
from cf_worker.repository import PostgresOutboxRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_SCHEDULED_PUBLISH_INTEGRATION") != "1",
        reason="set RUN_SCHEDULED_PUBLISH_INTEGRATION=1 against a migrated database",
    ),
]


@pytest.mark.asyncio
async def test_worker_claims_due_scoped_job_and_publishes_exact_catalog_version() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    worker = PostgresOutboxRepository(
        WorkerSettings(
            worker_id="scheduled-publish-integration",
            scheduled_publish_batch_size=10,
            scheduled_publish_lease_seconds=30,
        )
    )
    ids = [uuid.uuid4() for _ in range(7)]
    tenant_id, company_id, user_id, membership_id, product_id, job_id, other_job_id = ids
    other_tenant_id, other_company_id, other_product_id = (uuid.uuid4() for _ in range(3))
    now = datetime.now(UTC)
    try:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO tenants(id,slug,name,type,status,settings) VALUES (:id,:slug,:slug,'enterprise','active','{}')"
                ),
                {"id": tenant_id, "slug": f"sched-{tenant_id.hex[:10]}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) VALUES (:id,:tenant,:name,:name,'active','{}')"
                ),
                {"id": company_id, "tenant": tenant_id, "name": f"company-{company_id.hex}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,'Scheduled Publisher','active')"
                ),
                {"id": user_id},
            )
            await connection.execute(
                text(
                        "INSERT INTO memberships(id,tenant_id,company_id,user_id,role,status,permissions) "
                        "VALUES (:id,:tenant,:company,:user,'company_admin','active','{}')"
                ),
                {"id": membership_id, "tenant": tenant_id, "company": company_id, "user": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO products(id,tenant_id,company_id,slug,name,summary,detail,status,visibility,version,settings) VALUES (:id,:tenant,:company,:slug,'产品','摘要','详情','draft','public',3,'{}')"
                ),
                {
                    "id": product_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "slug": f"product-{product_id.hex[:8]}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO scheduled_publish_jobs(id,tenant_id,company_id,resource_type,resource_id,target_version,scheduled_by,scheduled_at,next_attempt_at,status,created_at,updated_at) VALUES (:id,:tenant,:company,'product',:resource,3,:user,:due,:due,'pending',:created,:created)"
                ),
                {
                    "id": job_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "resource": product_id,
                    "user": user_id,
                    "due": now - timedelta(seconds=1),
                    "created": now - timedelta(seconds=2),
                },
            )
            # A second tenant proves that the claimed tenant/company context cannot see it.
            await connection.execute(
                text(
                    "INSERT INTO tenants(id,slug,name,type,status,settings) VALUES (:id,:slug,:slug,'enterprise','active','{}')"
                ),
                {"id": other_tenant_id, "slug": f"other-{other_tenant_id.hex[:10]}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) VALUES (:id,:tenant,:name,:name,'active','{}')"
                ),
                {
                    "id": other_company_id,
                    "tenant": other_tenant_id,
                    "name": f"company-{other_company_id.hex}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO products(id,tenant_id,company_id,slug,name,summary,detail,status,visibility,version,settings) VALUES (:id,:tenant,:company,:slug,'产品','摘要','详情','draft','public',3,'{}')"
                ),
                {
                    "id": other_product_id,
                    "tenant": other_tenant_id,
                    "company": other_company_id,
                    "slug": f"product-{other_product_id.hex[:8]}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO scheduled_publish_jobs(id,tenant_id,company_id,resource_type,resource_id,target_version,scheduled_by,scheduled_at,next_attempt_at,status) VALUES (:id,:tenant,:company,'product',:resource,3,:user,:future,:future,'pending')"
                ),
                {
                    "id": other_job_id,
                    "tenant": other_tenant_id,
                    "company": other_company_id,
                    "resource": other_product_id,
                    "user": user_id,
                    "future": now + timedelta(hours=1),
                },
            )

        claims = await worker.claim_scheduled_publishes()
        claim = next(item for item in claims if item.id == job_id)
        await worker.publish_scheduled_catalog(claim)
        assert await worker.complete_scheduled_publish(claim)
        async with owner.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT status, version, published_at FROM products WHERE id=:id"),
                    {"id": product_id},
                )
            ).one()
            assert row.status == "published" and row.version == 4 and row.published_at is not None
    finally:
        await worker.close()
        async with owner.begin() as connection:
            await connection.execute(
                text("DELETE FROM scheduled_publish_jobs WHERE tenant_id IN (:one,:two)"),
                {"one": tenant_id, "two": other_tenant_id},
            )
            await connection.execute(
                text("DELETE FROM products WHERE tenant_id IN (:one,:two)"),
                {"one": tenant_id, "two": other_tenant_id},
            )
        await owner.dispose()

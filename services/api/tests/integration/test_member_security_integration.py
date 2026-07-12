from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.api.errors import ApiError
from app.api.member_schemas import UpdateMemberAccessRequest
from app.core.config import Settings
from app.db.session import set_rls_context
from app.services.member_store import MemberScope, MemberStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MEMBER_INTEGRATION") != "1",
        reason="set RUN_MEMBER_INTEGRATION=1 against a disposable migrated database",
    ),
]


@dataclass(frozen=True, slots=True)
class SeededMember:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    session_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SeededCompany:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    members: tuple[SeededMember, ...]


async def _seed_company(
    owner: AsyncEngine,
    *,
    roles: tuple[str, ...],
) -> SeededCompany:
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]
    members: list[SeededMember] = []
    async with owner.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO tenants(id,slug,name,type,status,settings) "
                "VALUES (:id,:slug,:name,'enterprise','active','{}')"
            ),
            {
                "id": tenant_id,
                "slug": f"member-security-{suffix}",
                "name": f"Member Security {suffix}",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) "
                "VALUES (:id,:tenant_id,:name,:normalized_name,'active','{}')"
            ),
            {
                "id": company_id,
                "tenant_id": tenant_id,
                "name": f"Member Security {suffix}",
                "normalized_name": f"member security {suffix}",
            },
        )
        for index, role in enumerate(roles):
            user_id = uuid.uuid4()
            membership_id = uuid.uuid4()
            session_id = uuid.uuid4()
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,:display_name,'active')"
                ),
                {"id": user_id, "display_name": f"Integration Member {index}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO memberships("
                    "id,user_id,tenant_id,company_id,role,permissions,status) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:role,"
                    "ARRAY['members.manage'],'active')"
                ),
                {
                    "id": membership_id,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "role": role,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO staff_credentials("
                    "id,user_id,membership_id,tenant_id,company_id,account_normalized,"
                    "password_hash,is_enabled) "
                    "VALUES (:id,:user_id,:membership_id,:tenant_id,:company_id,:account,"
                    ":password_hash,true)"
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "membership_id": membership_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "account": f"member-{index}-{suffix}@example.test",
                    "password_hash": "integration-only-password-hash",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions("
                    "id,user_id,tenant_id,company_id,refresh_token_hash,expires_at) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:token_hash,:expires_at)"
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "token_hash": uuid.uuid4().hex,
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )
            members.append(SeededMember(user_id, membership_id, session_id))
    return SeededCompany(tenant_id, company_id, tuple(members))


def _scope(company: SeededCompany) -> MemberScope:
    actor = company.members[0]
    return MemberScope(
        tenant_id=company.tenant_id,
        company_id=company.company_id,
        actor_user_id=actor.user_id,
        actor_session_id=actor.session_id,
        actor_role="company_admin",
        actor_permissions=("members.manage",),
    )


@pytest.mark.asyncio
async def test_concurrent_admin_demotions_cannot_remove_every_company_admin() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    try:
        company = await _seed_company(
            owner,
            roles=("company_admin", "company_admin"),
        )
        store = MemberStore(sessions, settings)
        results = await asyncio.gather(
            *(
                store.update_access(
                    scope=_scope(company),
                    membership_id=member.membership_id,
                    body=UpdateMemberAccessRequest(role="card_owner"),
                    trace_id=f"concurrent-admin-demotion-{index}",
                )
                for index, member in enumerate(company.members)
            ),
            return_exceptions=True,
        )

        failures = [result for result in results if isinstance(result, ApiError)]
        assert len(failures) == 1, repr(results)
        assert failures[0].code == "LAST_COMPANY_ADMIN_REQUIRED"
        async with owner.connect() as connection:
            active_admins = await connection.scalar(
                text(
                    "SELECT count(*) FROM memberships AS membership "
                    "JOIN staff_credentials AS credential "
                    "ON credential.membership_id=membership.id "
                    "WHERE membership.tenant_id=:tenant_id "
                    "AND membership.company_id=:company_id "
                    "AND membership.role='company_admin' "
                    "AND membership.status='active' AND credential.is_enabled"
                ),
                {"tenant_id": company.tenant_id, "company_id": company.company_id},
            )
        assert active_admins == 1
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_membership_rls_blocks_cross_company_reads_and_updates() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    try:
        first = await _seed_company(owner, roles=("company_admin",))
        second = await _seed_company(owner, roles=("company_admin",))
        foreign_membership_id = second.members[0].membership_id

        async with sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=first.tenant_id,
                company_id=first.company_id,
                actor_user_id=first.members[0].user_id,
                actor_session_id=first.members[0].session_id,
            )
            visible = await session.scalar(
                text("SELECT id FROM memberships WHERE id=:id"),
                {"id": foreign_membership_id},
            )
            updated = await session.execute(
                text("UPDATE memberships SET status='disabled' WHERE id=:id"),
                {"id": foreign_membership_id},
            )

        assert visible is None
        assert updated.rowcount == 0
        async with owner.connect() as connection:
            status = await connection.scalar(
                text("SELECT status FROM memberships WHERE id=:id"),
                {"id": foreign_membership_id},
            )
        assert status == "active"
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_disable_and_password_reset_revoke_existing_auth_sessions() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    try:
        company = await _seed_company(
            owner,
            roles=("company_admin", "card_owner", "card_owner"),
        )
        store = MemberStore(sessions, settings)
        disabled_member = company.members[1]
        reset_member = company.members[2]

        await store.set_status(
            scope=_scope(company),
            membership_id=disabled_member.membership_id,
            status="disabled",
            trace_id="disable-session-revocation",
        )
        reset = await store.reset_password(
            scope=_scope(company),
            membership_id=reset_member.membership_id,
            password="Integration-Reset-Password-2026!",  # noqa: S106
            revoke_sessions=True,
            trace_id="password-reset-session-revocation",
        )

        assert reset.sessions_revoked == 1
        async with owner.connect() as connection:
            revoked = (
                await connection.execute(
                    text(
                        "SELECT id,revoke_reason FROM auth_sessions "
                        "WHERE id IN (:disabled_session,:reset_session)"
                    ),
                    {
                        "disabled_session": disabled_member.session_id,
                        "reset_session": reset_member.session_id,
                    },
                )
            ).all()
        reasons = {row.id: row.revoke_reason for row in revoked}
        assert reasons == {
            disabled_member.session_id: "member_disabled",
            reset_member.session_id: "password_reset_by_admin",
        }
    finally:
        await runtime.dispose()
        await owner.dispose()

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.api.errors import ApiError
from app.api.schemas import ConsentRequest, CreateVisitRequest
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.tokens import VisitorPrincipal, issue_profile_link_token
from app.db.models import Conversation, VisitSummary
from app.db.session import set_rls_context
from app.services.crm_store import CrmStore
from app.services.public_store import PublicStore
from app.services.visitor_profile_store import VisitorProfileScope, VisitorProfileStore
from app.services.workflow_store import WorkflowScope, WorkflowStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VISITOR_PROFILE_INTEGRATION") != "1",
        reason=(
            "set RUN_VISITOR_PROFILE_INTEGRATION=1 against a disposable migrated database"
        ),
    ),
]


@dataclass(frozen=True, slots=True)
class ProfileGraph:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    owner_user_id: uuid.UUID
    card_id: uuid.UUID
    visitor_id: uuid.UUID
    visit_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    summary_id: uuid.UUID
    signal_id: uuid.UUID
    source_id: uuid.UUID
    consent_id: uuid.UUID
    slug: str


async def _seed_graph(
    owner: AsyncEngine,
    settings: Settings,
    *,
    source_expired: bool = False,
) -> ProfileGraph:
    ids = [uuid.uuid4() for _ in range(10)]
    (
        tenant_id,
        company_id,
        owner_user_id,
        card_id,
        visitor_id,
        visit_id,
        conversation_id,
        message_id,
        summary_id,
        signal_id,
    ) = ids
    source_id = uuid.uuid4()
    consent_id = uuid.uuid4()
    prompt_id = uuid.uuid4()
    slug = f"profile-integration-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)
    consent_expiry = now + timedelta(days=30)
    source_expiry = now - timedelta(seconds=1) if source_expired else now + timedelta(days=30)
    cipher = PiiCipher.from_settings(settings)
    policy_settings = json.dumps(
        {"policy_versions": {"profile_personalization": "profile-v1"}}
    )
    label = "工业节能"
    label_hmac = cipher.hmac(
        f"profile-signal:{tenant_id}:{company_id}:interest:{label.casefold()}"
    )

    async with owner.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO tenants(id,slug,name,type,status,settings) "
                "VALUES (:id,:slug,:name,'enterprise','active','{}')"
            ),
            {"id": tenant_id, "slug": slug, "name": slug},
        )
        await connection.execute(
            text(
                "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) "
                "VALUES (:id,:tenant_id,:name,:name,'active',CAST(:settings AS jsonb))"
            ),
            {
                "id": company_id,
                "tenant_id": tenant_id,
                "name": slug,
                "settings": policy_settings,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO users(id,display_name,status) "
                "VALUES (:id,:name,'active')"
            ),
            {"id": owner_user_id, "name": "画像验收管理员"},
        )
        await connection.execute(
            text(
                "INSERT INTO cards(id,tenant_id,company_id,owner_user_id,slug,"
                "display_name,status,published_at,settings) VALUES "
                "(:id,:tenant_id,:company_id,:owner_user_id,:slug,:name,'published',"
                ":now,'{}')"
            ),
            {
                "id": card_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "owner_user_id": owner_user_id,
                "slug": slug,
                "name": "画像验收名片",
                "now": now,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO visitors(id,tenant_id,company_id,anonymous_hash) "
                "VALUES (:id,:tenant_id,:company_id,:anonymous_hash)"
            ),
            {
                "id": visitor_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "anonymous_hash": hashlib.sha256(str(visitor_id).encode()).hexdigest(),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO visits(id,tenant_id,company_id,card_id,visitor_id,source,context) "
                "VALUES (:id,:tenant_id,:company_id,:card_id,:visitor_id,'integration',"
                "'{\"campaign\":\"private-campaign\","
                "\"privacy_notice_version\":\"privacy-v1\"}')"
            ),
            {
                "id": visit_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "card_id": card_id,
                "visitor_id": visitor_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO conversations(id,tenant_id,company_id,card_id,visitor_id,"
                "visit_id,status,primary_intent) VALUES "
                "(:id,:tenant_id,:company_id,:card_id,:visitor_id,:visit_id,'active',"
                "'product_evaluation')"
            ),
            {
                "id": conversation_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "card_id": card_id,
                "visitor_id": visitor_id,
                "visit_id": visit_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO messages(id,tenant_id,company_id,conversation_id,role,content,"
                "status) VALUES (:id,:tenant_id,:company_id,:conversation_id,'user',"
                "'已脱敏的画像验收消息','completed')"
            ),
            {
                "id": message_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "conversation_id": conversation_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO prompt_versions(id,tenant_id,company_id,name,purpose,"
                "version_number,content,content_hash,status,published_by,published_at) "
                "VALUES (:id,:tenant_id,:company_id,'integration-summary','visit_summary',1,"
                "'integration',:content_hash,'published',:published_by,:now)"
            ),
            {
                "id": prompt_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "content_hash": "a" * 64,
                "published_by": owner_user_id,
                "now": now,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO visit_summaries(id,tenant_id,company_id,conversation_id,"
                "last_message_id,prompt_version_id,summary,interests,strength,"
                "source_message_ids,is_current,approved_at,approved_by) VALUES "
                "(:id,:tenant_id,:company_id,:conversation_id,:message_id,:prompt_id,"
                "'访客关注工业节能',ARRAY['工业节能'],'high',"
                "ARRAY[CAST(:message_id AS uuid)],"
                "true,:now,:approved_by)"
            ),
            {
                "id": summary_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "prompt_id": prompt_id,
                "now": now,
                "approved_by": owner_user_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO consent_records(id,tenant_id,company_id,visitor_id,scope,"
                "policy_version,granted,recorded_at,expires_at,evidence) VALUES "
                "(:id,:tenant_id,:company_id,:visitor_id,'profile_personalization',"
                "'profile-v1',true,:now,:expires,'{}')"
            ),
            {
                "id": consent_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "visitor_id": visitor_id,
                "now": now,
                "expires": consent_expiry,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO visitor_profile_signals(id,tenant_id,company_id,visitor_id,kind,"
                "label_ciphertext,label_hmac,strength,confidence,first_seen_at,last_seen_at,"
                "evidence_count,retention_expires_at,encryption_key_ref) VALUES "
                "(:id,:tenant_id,:company_id,:visitor_id,'interest',:ciphertext,:hmac,0.8,0.8,"
                ":now,:now,1,:expires,:key_ref)"
            ),
            {
                "id": signal_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "visitor_id": visitor_id,
                "ciphertext": cipher.encrypt(label),
                "hmac": label_hmac,
                "now": now,
                "expires": source_expiry,
                "key_ref": cipher.key_ref,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO visitor_profile_signal_sources(id,tenant_id,company_id,signal_id,"
                "consent_id,visit_id,conversation_id,summary_id,message_id,contribution,"
                "confidence,observed_at,retention_expires_at) VALUES "
                "(:id,:tenant_id,:company_id,:signal_id,:consent_id,:visit_id,"
                ":conversation_id,:summary_id,:message_id,0.8,0.8,:now,:expires)"
            ),
            {
                "id": source_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "signal_id": signal_id,
                "consent_id": consent_id,
                "visit_id": visit_id,
                "conversation_id": conversation_id,
                "summary_id": summary_id,
                "message_id": message_id,
                "now": now,
                "expires": source_expiry,
            },
        )
    return ProfileGraph(
        tenant_id=tenant_id,
        company_id=company_id,
        owner_user_id=owner_user_id,
        card_id=card_id,
        visitor_id=visitor_id,
        visit_id=visit_id,
        conversation_id=conversation_id,
        message_id=message_id,
        summary_id=summary_id,
        signal_id=signal_id,
        source_id=source_id,
        consent_id=consent_id,
        slug=slug,
    )


@pytest.mark.asyncio
async def test_profile_rls_concurrent_revoke_and_physical_retention_purge() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    graphs: list[ProfileGraph] = []
    try:
        active = await _seed_graph(owner, settings)
        expired = await _seed_graph(owner, settings, source_expired=True)
        erased = await _seed_graph(owner, settings)
        graphs.extend((active, expired, erased))

        profile_store = VisitorProfileStore(sessions, settings)
        items, total = await profile_store.list(
            scope=VisitorProfileScope(
                active.tenant_id,
                active.company_id,
                active.owner_user_id,
                "company_admin",
            ),
            limit=20,
            offset=0,
        )
        assert total == 1
        assert items[0].top_interests[0].label == "工业节能"
        async with owner.connect() as connection:
            hmacs = (
                await connection.execute(
                    text(
                        "SELECT label_hmac FROM visitor_profile_signals "
                        "WHERE id IN (:active_id,:expired_id)"
                    ),
                    {
                        "active_id": active.signal_id,
                        "expired_id": expired.signal_id,
                    },
                )
            ).scalars().all()
        assert len(set(hmacs)) == 2

        async with sessions() as session, session.begin():
            await set_rls_context(
                session, tenant_id=active.tenant_id, company_id=active.company_id
            )
            assert await session.scalar(
                text("SELECT id FROM visitor_profile_signals WHERE id=:id"),
                {"id": expired.signal_id},
            ) is None

        workflow = WorkflowStore(sessions, settings)
        public = PublicStore(sessions, settings)
        profile_token, _ = issue_profile_link_token(
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
            ttl_seconds=settings.profile_link_token_ttl_seconds,
            visitor_id=active.visitor_id,
            tenant_id=active.tenant_id,
            company_id=active.company_id,
            consent_id=active.consent_id,
        )
        linked_visit_request = CreateVisitRequest(
            source="integration",
            privacy_notice_version="privacy-v1",
            profile_link_token=profile_token,
        )
        linked_visit_key = f"profile-link-{uuid.uuid4().hex}"
        linked_visit = await public.create_visit(
            slug=active.slug,
            request=linked_visit_request,
            idempotency_key=linked_visit_key,
        )
        assert linked_visit.visit_id != active.visit_id

        async def aggregate() -> None:
            async with sessions() as session, session.begin():
                await set_rls_context(
                    session,
                    tenant_id=active.tenant_id,
                    company_id=active.company_id,
                    actor_user_id=active.owner_user_id,
                )
                conversation = await session.scalar(
                    select(Conversation).where(Conversation.id == active.conversation_id)
                )
                summary = await session.scalar(
                    select(VisitSummary).where(VisitSummary.id == active.summary_id)
                )
                assert conversation is not None and summary is not None
                await workflow._aggregate_profile_signals(  # noqa: SLF001
                    session,
                    scope=WorkflowScope(
                        active.tenant_id,
                        active.company_id,
                        active.owner_user_id,
                        "company_admin",
                    ),
                    conversation=conversation,
                    summary=summary,
                )

        async def revoke() -> None:
            now = datetime.now(UTC)
            await public.record_consent(
                slug=active.slug,
                principal=VisitorPrincipal(
                    visitor_id=active.visitor_id,
                    visit_id=active.visit_id,
                    tenant_id=active.tenant_id,
                    company_id=active.company_id,
                    card_id=active.card_id,
                    token_id=uuid.uuid4(),
                    issued_at=int(now.timestamp()),
                    issued_at_ms=int(now.timestamp() * 1_000),
                ),
                request=ConsentRequest(
                    scope="profile_personalization",
                    policy_version="profile-v1",
                    granted=False,
                ),
                idempotency_key=f"profile-revoke-{uuid.uuid4().hex}",
            )

        await asyncio.gather(aggregate(), revoke())
        stale_now = datetime.now(UTC) - timedelta(seconds=1)
        stale_principal = VisitorPrincipal(
            visitor_id=active.visitor_id,
            visit_id=active.visit_id,
            tenant_id=active.tenant_id,
            company_id=active.company_id,
            card_id=active.card_id,
            token_id=uuid.uuid4(),
            issued_at=int(stale_now.timestamp()),
            issued_at_ms=int(stale_now.timestamp() * 1_000),
        )
        with pytest.raises(ApiError) as stale_grant:
            await public.record_consent(
                slug=active.slug,
                principal=stale_principal,
                request=ConsentRequest(
                    scope="profile_personalization",
                    policy_version="profile-v1",
                    granted=True,
                ),
                idempotency_key=f"stale-grant-{uuid.uuid4().hex}",
            )
        assert stale_grant.value.code == "VISITOR_SESSION_STALE"
        with pytest.raises(ApiError) as replay:
            await public.create_visit(
                slug=active.slug,
                request=linked_visit_request,
                idempotency_key=linked_visit_key,
            )
        assert replay.value.code == "PROFILE_LINK_REPLAY_INVALID"

        crm = CrmStore(sessions, settings)
        async with sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=erased.tenant_id,
                company_id=erased.company_id,
                actor_user_id=erased.owner_user_id,
            )
            await crm._delete_visitor_personal_data(  # noqa: SLF001
                session,
                tenant_id=erased.tenant_id,
                company_id=erased.company_id,
                visitor_id=erased.visitor_id,
            )
        async with owner.begin() as connection:
            remaining = await connection.scalar(
                text(
                    "SELECT count(*) FROM visitor_profile_signals "
                    "WHERE visitor_id=:visitor_id"
                ),
                {"visitor_id": active.visitor_id},
            )
            assert remaining == 0
            deleted = await connection.scalar(
                text("SELECT app.purge_expired_visitor_profiles()")
            )
            assert int(deleted or 0) >= 1
            assert await connection.scalar(
                text("SELECT id FROM visitor_profile_signal_sources WHERE id=:id"),
                {"id": expired.source_id},
            ) is None
            assert await connection.scalar(
                text("SELECT id FROM visitor_profile_signals WHERE id=:id"),
                {"id": expired.signal_id},
            ) is None
            erased_summary = (
                await connection.execute(
                    text(
                        "SELECT summary,interests,source_message_ids,approved_at "
                        "FROM visit_summaries WHERE id=:id"
                    ),
                    {"id": erased.summary_id},
                )
            ).one()
            assert erased_summary.summary == "[已根据访客隐私请求删除]"
            assert erased_summary.interests == []
            assert erased_summary.source_message_ids == []
            assert erased_summary.approved_at is None
            assert await connection.scalar(
                text("SELECT primary_intent FROM conversations WHERE id=:id"),
                {"id": erased.conversation_id},
            ) is None
            erased_message = (
                await connection.execute(
                    text("SELECT content,content_redacted FROM messages WHERE id=:id"),
                    {"id": erased.message_id},
                )
            ).one()
            assert erased_message.content == "[已根据访客隐私请求删除]"
            assert erased_message.content_redacted is True
            context = await connection.scalar(
                text("SELECT context FROM visits WHERE id=:id"),
                {"id": erased.visit_id},
            )
            assert context == {"privacy_notice_version": "privacy-v1"}
            assert await connection.scalar(
                text(
                    "SELECT id FROM visitor_profile_signals "
                    "WHERE visitor_id=:visitor_id"
                ),
                {"visitor_id": erased.visitor_id},
            ) is None
    finally:
        async with owner.begin() as connection:
            for graph in graphs:
                await connection.execute(
                    text("DELETE FROM visitor_profile_signals WHERE company_id=:id"),
                    {"id": graph.company_id},
                )
                await connection.execute(
                    text("DELETE FROM visit_summaries WHERE company_id=:id"),
                    {"id": graph.company_id},
                )
                await connection.execute(
                    text("DELETE FROM companies WHERE id=:id"),
                    {"id": graph.company_id},
                )
                await connection.execute(
                    text("DELETE FROM users WHERE id=:id"),
                    {"id": graph.owner_user_id},
                )
                await connection.execute(
                    text("DELETE FROM tenants WHERE id=:id"),
                    {"id": graph.tenant_id},
                )
        await runtime.dispose()
        await owner.dispose()

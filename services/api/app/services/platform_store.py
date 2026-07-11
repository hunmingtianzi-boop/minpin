from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.platform_schemas import (
    CreateEnterpriseRequest,
    EnterpriseListItem,
    EnterpriseRecord,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.db.models import (
    AuditLog,
    Card,
    Company,
    ContentStatus,
    LifecycleStatus,
    Membership,
    MembershipRole,
    OutboxEvent,
    OutboxStatus,
    StaffCredential,
    Tenant,
    TenantType,
    User,
)
from app.db.session import set_rls_context


@dataclass(frozen=True, slots=True)
class PlatformActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


_COMPANY_ADMIN_PERMISSIONS = [
    "company.manage",
    "card.manage",
    "knowledge.manage",
    "knowledge.publish",
    "catalog.manage",
    "conversations.read",
    "summaries.write",
    "leads.read",
    "leads.write",
    "privacy.manage",
    "analytics.read",
]


class PlatformStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._cipher = PiiCipher.from_settings(settings)

    async def create_enterprise(
        self,
        *,
        actor: PlatformActor,
        body: CreateEnterpriseRequest,
        trace_id: str | None,
    ) -> EnterpriseRecord:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可开通企业")
        account = normalize_staff_account(body.admin_account)
        tenant_id = uuid.uuid4()
        company_id = uuid.uuid4()
        user_id = uuid.uuid4()
        membership_id = uuid.uuid4()
        credential_id = uuid.uuid4()
        card_id = uuid.uuid4()
        card_slug = f"c-{secrets.token_hex(16)}"
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"platform-enterprise:{body.tenant_slug}"},
            )
            duplicate_tenant = await session.scalar(
                select(Tenant.id).where(Tenant.slug == body.tenant_slug)
            )
            if duplicate_tenant is not None:
                raise ApiError(409, "TENANT_SLUG_CONFLICT", "企业租户标识已存在")
            duplicate_account = await session.scalar(
                select(StaffCredential.id).where(StaffCredential.account_normalized == account)
            )
            if duplicate_account is not None:
                raise ApiError(409, "ACCOUNT_CONFLICT", "管理员登录账号已存在")
            tenant = Tenant(
                id=tenant_id,
                slug=body.tenant_slug,
                name=body.tenant_name,
                tenant_type=TenantType.ENTERPRISE,
                status=LifecycleStatus.ACTIVE,
                settings={"slug": body.tenant_slug, "onboarding_status": "initialized"},
            )
            company = Company(
                id=company_id,
                tenant_id=tenant_id,
                name=body.company_name,
                normalized_name=" ".join(body.company_name.casefold().split()),
                industry=body.industry,
                status=LifecycleStatus.ACTIVE,
                settings={
                    "summary": "",
                    "region": None,
                    "website": None,
                    "logo_url": None,
                    "onboarding_status": "content_pending",
                },
            )
            email = account if "@" in account else None
            user = User(
                id=user_id,
                display_name=body.admin_display_name,
                email_ciphertext=self._cipher.encrypt(email) if email else None,
                email_hmac=self._cipher.hmac(email) if email else None,
                status=LifecycleStatus.ACTIVE,
            )
            membership_values = {
                "id": membership_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "role": MembershipRole.COMPANY_ADMIN,
                "permissions": _COMPANY_ADMIN_PERMISSIONS,
                "status": LifecycleStatus.ACTIVE,
            }
            credential = StaffCredential(
                id=credential_id,
                user_id=user_id,
                membership_id=membership_id,
                tenant_id=tenant_id,
                company_id=company_id,
                account_normalized=account,
                password_hash=hash_staff_password(body.admin_password.get_secret_value()),
                is_enabled=True,
            )
            card_values = {
                "id": card_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "owner_user_id": user_id,
                "slug": card_slug,
                "display_name": body.admin_display_name,
                "status": ContentStatus.DRAFT,
                "settings": {
                    "title": body.initial_card_title or body.admin_display_name,
                    "assistant_name": "企业 AI 接待",
                    "welcome_message": "您好，我可以根据企业已审核资料为您介绍业务。",
                    "suggested_questions": [],
                    "policy_versions": {
                        "privacy": "privacy-v1",
                        "chat_notice": "chat-notice-v1",
                        "lead_consent": "lead-consent-v1",
                    },
                },
            }
            # These mappers intentionally do not expose ORM relationships. Flush in
            # foreign-key order so SQLAlchemy cannot emit a child row before its
            # parent while onboarding a completely new tenant.
            session.add_all([tenant, user])
            await session.flush()
            session.add(company)
            await session.flush()
            # Avoid INSERT .. RETURNING here. PostgreSQL correctly applies SELECT
            # RLS policies to RETURNING rows, while this onboarding capability is
            # intentionally INSERT-only for cross-tenant membership/card/event/audit
            # data.
            await session.execute(insert(Membership).values(**membership_values))
            await session.execute(insert(Card).values(**card_values))
            session.add(credential)
            await session.flush()
            await session.execute(
                insert(OutboxEvent).values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    aggregate_type="company",
                    aggregate_id=company_id,
                    aggregate_version=1,
                    event_type="enterprise.created.v1",
                    payload={
                        "tenant_id": str(tenant_id),
                        "company_id": str(company_id),
                        "admin_user_id": str(user_id),
                    },
                    headers={"contains_pii": False},
                    deduplication_key=f"enterprise.created:{company_id}",
                    status=OutboxStatus.PENDING,
                )
            )
            audit_event = {
                "tenant_slug": body.tenant_slug,
                "admin_membership_id": str(membership_id),
                "initial_card_id": str(card_id),
            }
            audit_payload = {
                "tenant_id": str(tenant_id),
                "company_id": str(company_id),
                "actor_user_id": str(actor.user_id),
                "action": "platform.enterprise.create",
                "resource_type": "company",
                "resource_id": str(company_id),
                "trace_id": trace_id,
                "event_data": audit_event,
                "previous_hash": None,
            }
            await session.execute(
                insert(AuditLog).values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    actor_user_id=actor.user_id,
                    action="platform.enterprise.create",
                    resource_type="company",
                    resource_id=company_id,
                    trace_id=trace_id,
                    event_data=audit_event,
                    previous_hash=None,
                    entry_hash=hashlib.sha256(
                        json.dumps(
                            audit_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )
            return EnterpriseRecord(
                tenant_id=tenant_id,
                tenant_slug=body.tenant_slug,
                tenant_name=tenant.name,
                company_id=company_id,
                company_name=company.name,
                company_status=company.status.value,
                admin_user_id=user_id,
                admin_membership_id=membership_id,
                initial_card_id=card_id,
                initial_card_slug=card_slug,
                created_at=now,
            )

    async def list_enterprises(
        self,
        *,
        actor: PlatformActor,
        limit: int,
        offset: int,
    ) -> tuple[list[EnterpriseListItem], int]:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看企业清单")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            filters = (
                Tenant.tenant_type == TenantType.ENTERPRISE,
                Tenant.deleted_at.is_(None),
                Company.deleted_at.is_(None),
            )
            total = int(
                await session.scalar(
                    select(func.count(Company.id))
                    .select_from(Company)
                    .join(Tenant, Tenant.id == Company.tenant_id)
                    .where(*filters)
                )
                or 0
            )
            rows = (
                await session.execute(
                    select(Tenant, Company)
                    .join(Company, Company.tenant_id == Tenant.id)
                    .where(*filters)
                    .order_by(Company.created_at.desc(), Company.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                EnterpriseListItem(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    tenant_name=tenant.name,
                    company_id=company.id,
                    company_name=company.name,
                    status=company.status.value,
                    created_at=company.created_at,
                )
                for tenant, company in rows
            ], total


__all__ = ["PlatformActor", "PlatformStore"]

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings, get_settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.db.models import (
    Company,
    LifecycleStatus,
    Membership,
    MembershipRole,
    StaffCredential,
    Tenant,
    User,
)
from app.services.audit import append_audit


class PlatformBootstrapInput(BaseSettings):
    """Explicit, one-time platform identity input loaded only by this CLI."""

    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_BOOTSTRAP_",
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    tenant_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    company_id: uuid.UUID | None = None
    account: str = Field(min_length=3, max_length=200)
    password: SecretStr = Field(min_length=12, max_length=200)
    display_name: str = Field(default="平台管理员", min_length=1, max_length=120)
    confirm: Literal["CREATE_FIRST_PLATFORM_ADMIN"]

    @field_validator("account", "display_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("platform bootstrap text cannot be blank")
        return normalized


@dataclass(frozen=True, slots=True)
class PlatformBootstrapResult:
    created: bool
    tenant_id: str
    company_id: str
    user_id: str
    membership_id: str


async def bootstrap_platform_admin(
    settings: Settings,
    bootstrap: PlatformBootstrapInput,
) -> PlatformBootstrapResult:
    database_url = settings.migration_database_url
    if not database_url:
        raise ValueError("MIGRATION_DATABASE_URL is required for platform bootstrap")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            return await _bootstrap(session, settings=settings, bootstrap=bootstrap)
    finally:
        await engine.dispose()


async def _bootstrap(
    session: AsyncSession,
    *,
    settings: Settings,
    bootstrap: PlatformBootstrapInput,
) -> PlatformBootstrapResult:
    account = normalize_staff_account(bootstrap.account)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"platform-bootstrap:{account}"},
    )
    tenant = await session.scalar(
        select(Tenant).where(
            Tenant.slug == bootstrap.tenant_slug,
            Tenant.status == LifecycleStatus.ACTIVE,
            Tenant.deleted_at.is_(None),
        )
    )
    if tenant is None:
        raise ValueError("platform bootstrap tenant does not exist or is inactive")
    company_query = select(Company).where(
        Company.tenant_id == tenant.id,
        Company.status == LifecycleStatus.ACTIVE,
        Company.deleted_at.is_(None),
    )
    if bootstrap.company_id is not None:
        company_query = company_query.where(Company.id == bootstrap.company_id)
    companies = list((await session.scalars(company_query.order_by(Company.id))).all())
    if not companies:
        raise ValueError("platform bootstrap company does not exist or is inactive")
    if len(companies) != 1:
        raise ValueError("PLATFORM_BOOTSTRAP_COMPANY_ID is required for a multi-company tenant")
    company = companies[0]

    existing = await session.scalar(
        select(StaffCredential).where(StaffCredential.account_normalized == account)
    )
    if existing is not None:
        membership = await session.scalar(
            select(Membership).where(Membership.id == existing.membership_id)
        )
        if (
            membership is not None
            and membership.tenant_id == tenant.id
            and membership.company_id == company.id
            and membership.role == MembershipRole.PLATFORM_ADMIN
            and membership.status == LifecycleStatus.ACTIVE
            and existing.is_enabled
        ):
            return PlatformBootstrapResult(
                created=False,
                tenant_id=str(tenant.id),
                company_id=str(company.id),
                user_id=str(existing.user_id),
                membership_id=str(existing.membership_id),
            )
        raise ValueError("platform bootstrap account is already assigned to another identity")

    cipher = PiiCipher.from_settings(settings)
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    credential_id = uuid.uuid4()
    email = account if "@" in account else None
    session.add(
        User(
            id=user_id,
            display_name=bootstrap.display_name,
            email_ciphertext=cipher.encrypt(email) if email else None,
            email_hmac=cipher.hmac(email) if email else None,
            status=LifecycleStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(
        Membership(
            id=membership_id,
            user_id=user_id,
            tenant_id=tenant.id,
            company_id=company.id,
            role=MembershipRole.PLATFORM_ADMIN,
            permissions=["*"],
            status=LifecycleStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(
        StaffCredential(
            id=credential_id,
            user_id=user_id,
            membership_id=membership_id,
            tenant_id=tenant.id,
            company_id=company.id,
            account_normalized=account,
            password_hash=hash_staff_password(bootstrap.password.get_secret_value()),
            is_enabled=True,
        )
    )
    await append_audit(
        session,
        tenant_id=tenant.id,
        company_id=company.id,
        actor_user_id=user_id,
        action="platform.admin.bootstrap",
        resource_type="membership",
        resource_id=membership_id,
        trace_id="platform-bootstrap-cli",
        event_data={
            "role": MembershipRole.PLATFORM_ADMIN.value,
            "bootstrap_method": "operator_cli",
        },
    )
    await session.flush()
    return PlatformBootstrapResult(
        created=True,
        tenant_id=str(tenant.id),
        company_id=str(company.id),
        user_id=str(user_id),
        membership_id=str(membership_id),
    )


def main() -> None:
    result = asyncio.run(
        bootstrap_platform_admin(
            get_settings(),
            PlatformBootstrapInput(),
        )
    )
    print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

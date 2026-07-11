from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class DatabaseScope:
    tenant_id: UUID
    company_id: UUID
    card_id: UUID | None = None
    card_slug: str | None = None
    actor_user_id: UUID | None = None
    actor_session_id: UUID | None = None


def build_async_engine(database_url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        database_url or settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.database_statement_timeout_ms),
                "application_name": settings.app_name,
            }
        },
    )


engine = build_async_engine()
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def set_rls_context(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    company_id: UUID,
    card_slug: str | None = None,
    actor_user_id: UUID | None = None,
    actor_session_id: UUID | None = None,
) -> DatabaseScope:
    """Set transaction-local trusted scope consumed by PostgreSQL RLS policies."""

    await session.execute(
        text(
            """
            SELECT
              set_config('app.tenant_id', :tenant_id, true),
              set_config('app.company_id', :company_id, true),
              set_config('app.card_slug', :card_slug, true),
              set_config('app.user_id', :actor_user_id, true),
              set_config('app.session_id', :actor_session_id, true)
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "card_slug": card_slug or "",
            "actor_user_id": str(actor_user_id) if actor_user_id else "",
            "actor_session_id": str(actor_session_id) if actor_session_id else "",
        },
    )
    return DatabaseScope(
        tenant_id=tenant_id,
        company_id=company_id,
        card_slug=card_slug,
        actor_user_id=actor_user_id,
        actor_session_id=actor_session_id,
    )


async def resolve_public_card_scope(session: AsyncSession, slug: str) -> DatabaseScope | None:
    """Resolve only the exact published card selected by the public route slug.

    The slug is first installed as a transaction-local RLS input. The cards table
    has a SELECT-only policy using strict equality, so wildcard or prefix scope
    expansion is impossible even if a caller accidentally changes this query.
    """

    normalized_slug = slug.strip()
    if not normalized_slug or len(normalized_slug) > 96:
        return None

    await session.execute(
        text("SELECT set_config('app.card_slug', :card_slug, true)"),
        {"card_slug": normalized_slug},
    )
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT id, tenant_id, company_id
                FROM cards
                WHERE slug = :card_slug
                  AND status = 'published'
                  AND deleted_at IS NULL
                  AND published_at IS NOT NULL
                  AND published_at <= now()
                LIMIT 1
                """
                ),
                {"card_slug": normalized_slug},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None

    scope = await set_rls_context(
        session,
        tenant_id=row["tenant_id"],
        company_id=row["company_id"],
        card_slug=normalized_slug,
    )
    return DatabaseScope(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
        card_id=row["id"],
        card_slug=normalized_slug,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency; transaction ownership remains with the use case."""

    async with async_session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Open an application-owned transaction and commit it atomically."""

    async with async_session_factory() as session, session.begin():
        yield session


__all__ = [
    "DatabaseScope",
    "async_session_factory",
    "build_async_engine",
    "engine",
    "get_db_session",
    "resolve_public_card_scope",
    "session_scope",
    "set_rls_context",
]

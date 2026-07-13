from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.enterprise_schemas import (
    DistributionRecord,
    DistributionWriteRequest,
    OverrideRecord,
    OverrideRevisionRecord,
    OverrideWriteRequest,
    PublicRecommendation,
    RecommendationEvidence,
)
from app.api.errors import ApiError
from app.db.models import (
    Card,
    CardContentOverride,
    CardContentOverrideMode,
    CardContentOverrideRevision,
    CaseStudy,
    ContentStatus,
    DistributedContentType,
    EnterpriseContentDistribution,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Product,
    ReviewStatus,
    Visibility,
)
from app.db.session import DatabaseScope, resolve_public_card_scope, set_rls_context
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class EnterpriseContentScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


def _require_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "资源已被其他操作更新，请刷新后重试",
            details={"current_version": current},
        )


def _managed_card_filters(scope: EnterpriseContentScope) -> tuple[Any, ...]:
    filters: list[Any] = [
        Card.tenant_id == scope.tenant_id,
        Card.company_id == scope.company_id,
        Card.deleted_at.is_(None),
    ]
    if scope.is_card_owner:
        filters.append(Card.owner_user_id == scope.actor_user_id)
    return tuple(filters)


ResourceType = Literal["product", "case_study", "knowledge_document"]


@dataclass(frozen=True, slots=True)
class EffectiveOverride:
    visible: bool
    mode: str
    custom_display: dict[str, Any]


async def effective_overrides(
    session: AsyncSession,
    *,
    scope: DatabaseScope,
    resource_type: ResourceType,
    resource_ids: list[uuid.UUID],
) -> dict[uuid.UUID, EffectiveOverride]:
    """Return visibility/presentation after company default then card override.

    Missing company rules intentionally default to visible, preserving existing
    published catalog behaviour while allowing admins to opt a source out.
    A hidden override always wins; custom only affects public display fields.
    """

    if not resource_ids or scope.card_id is None:
        return {}
    type_value = DistributedContentType(resource_type)
    distributions = {
        row.resource_id: row
        for row in (
            await session.scalars(
                select(EnterpriseContentDistribution).where(
                    EnterpriseContentDistribution.tenant_id == scope.tenant_id,
                    EnterpriseContentDistribution.company_id == scope.company_id,
                    EnterpriseContentDistribution.resource_type == type_value,
                    EnterpriseContentDistribution.resource_id.in_(resource_ids),
                )
            )
        ).all()
    }
    overrides = {
        row.resource_id: row
        for row in (
            await session.scalars(
                select(CardContentOverride).where(
                    CardContentOverride.tenant_id == scope.tenant_id,
                    CardContentOverride.company_id == scope.company_id,
                    CardContentOverride.card_id == scope.card_id,
                    CardContentOverride.resource_type == type_value,
                    CardContentOverride.resource_id.in_(resource_ids),
                )
            )
        ).all()
    }
    resolved: dict[uuid.UUID, EffectiveOverride] = {}
    for resource_id in resource_ids:
        distribution = distributions.get(resource_id)
        base_visible = distribution.is_default_visible if distribution is not None else True
        override = overrides.get(resource_id)
        if override is not None and override.mode == CardContentOverrideMode.HIDDEN:
            resolved[resource_id] = EffectiveOverride(False, "hidden", {})
        elif override is not None and override.mode == CardContentOverrideMode.CUSTOM:
            resolved[resource_id] = EffectiveOverride(
                base_visible, "custom", dict(override.custom_display or {})
            )
        else:
            resolved[resource_id] = EffectiveOverride(base_visible, "inherit", {})
    return resolved


class EnterpriseContentStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def get_distribution(
        self, *, scope: EnterpriseContentScope, resource_type: ResourceType, resource_id: uuid.UUID
    ) -> DistributionRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            resource = await self._resource(session, scope, resource_type, resource_id)
            distribution = await self._distribution(session, scope, resource_type, resource_id)
            if distribution is None:
                return _distribution_record(
                    EnterpriseContentDistribution(
                        id=uuid.UUID(int=0),
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        resource_type=DistributedContentType(resource_type),
                        resource_id=resource.id,
                        is_default_visible=True,
                        version=0,
                        created_at=resource.created_at,
                        updated_at=resource.updated_at,
                    ),
                    implicit=True,
                )
            return _distribution_record(distribution)

    async def put_distribution(
        self,
        *,
        scope: EnterpriseContentScope,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        body: DistributionWriteRequest,
        trace_id: str | None,
    ) -> DistributionRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._resource(session, scope, resource_type, resource_id)
            distribution = await self._distribution(
                session, scope, resource_type, resource_id, for_update=True
            )
            if distribution is None:
                if expected_version != 0:
                    raise ApiError(
                        409,
                        "VERSION_CONFLICT",
                        "分发策略已发生变化",
                        details={"current_version": 0},
                    )
                distribution = EnterpriseContentDistribution(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    resource_type=DistributedContentType(resource_type),
                    resource_id=resource_id,
                    is_default_visible=body.is_default_visible,
                    version=1,
                )
                session.add(distribution)
                action = "enterprise_content_distribution.create"
            else:
                _require_version(distribution.version, expected_version)
                distribution.is_default_visible = body.is_default_visible
                distribution.version += 1
                action = "enterprise_content_distribution.update"
            await self._audit(
                session,
                scope,
                action,
                distribution.id,
                trace_id,
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "is_default_visible": distribution.is_default_visible,
                    "version": distribution.version,
                },
            )
            await session.flush()
            await session.refresh(distribution)
            return _distribution_record(distribution)

    async def list_overrides(
        self, *, scope: EnterpriseContentScope, card_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[OverrideRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._card(session, scope, card_id)
            filters = (
                CardContentOverride.tenant_id == scope.tenant_id,
                CardContentOverride.company_id == scope.company_id,
                CardContentOverride.card_id == card_id,
            )
            total = int(
                await session.scalar(
                    select(func.count()).select_from(CardContentOverride).where(*filters)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(CardContentOverride)
                    .where(*filters)
                    .order_by(CardContentOverride.updated_at.desc(), CardContentOverride.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_override_record(row) for row in rows], total

    async def put_override(
        self,
        *,
        scope: EnterpriseContentScope,
        card_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        body: OverrideWriteRequest,
        trace_id: str | None,
    ) -> OverrideRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._card(session, scope, card_id)
            source = await self._resource(session, scope, resource_type, resource_id)
            override = await self._override(
                session, scope, card_id, resource_type, resource_id, for_update=True
            )
            mode = CardContentOverrideMode(body.mode)
            display = body.custom_display.as_dict() if body.custom_display else {}
            if override is None:
                if expected_version != 0:
                    raise ApiError(
                        409,
                        "VERSION_CONFLICT",
                        "名片覆盖策略已发生变化",
                        details={"current_version": 0},
                    )
                override = CardContentOverride(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    card_id=card_id,
                    resource_type=DistributedContentType(resource_type),
                    resource_id=resource_id,
                    mode=mode,
                    custom_display=display,
                    source_version=source.version,
                    version=1,
                )
                session.add(override)
                action = "card_content_override.create"
            else:
                _require_version(override.version, expected_version)
                override.mode = mode
                override.custom_display = display
                override.source_version = source.version
                override.version += 1
                action = "card_content_override.update"
            await session.flush()
            await self._snapshot(session, override)
            await self._audit(
                session,
                scope,
                action,
                override.id,
                trace_id,
                {
                    "card_id": card_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "mode": body.mode,
                    "version": override.version,
                },
            )
            await session.refresh(override)
            return _override_record(override)

    async def delete_override(
        self,
        *,
        scope: EnterpriseContentScope,
        card_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            override = await self._override(
                session, scope, card_id, resource_type, resource_id, for_update=True
            )
            if override is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片内容覆盖策略不存在")
            _require_version(override.version, expected_version)
            await self._audit(
                session,
                scope,
                "card_content_override.delete",
                override.id,
                trace_id,
                {
                    "card_id": card_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "version": override.version,
                },
            )
            await session.delete(override)

    async def list_revisions(
        self,
        *,
        scope: EnterpriseContentScope,
        card_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> list[OverrideRevisionRecord]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            override = await self._override(session, scope, card_id, resource_type, resource_id)
            if override is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片内容覆盖策略不存在")
            rows = (
                await session.scalars(
                    select(CardContentOverrideRevision)
                    .where(CardContentOverrideRevision.override_id == override.id)
                    .order_by(CardContentOverrideRevision.version.desc())
                )
            ).all()
            return [_revision_record(row) for row in rows]

    async def rollback_override(
        self,
        *,
        scope: EnterpriseContentScope,
        card_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        revision_version: int,
        trace_id: str | None,
    ) -> OverrideRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            override = await self._override(
                session, scope, card_id, resource_type, resource_id, for_update=True
            )
            if override is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片内容覆盖策略不存在")
            _require_version(override.version, expected_version)
            revision = await session.scalar(
                select(CardContentOverrideRevision).where(
                    CardContentOverrideRevision.override_id == override.id,
                    CardContentOverrideRevision.version == revision_version,
                )
            )
            if revision is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "指定覆盖版本不存在")
            override.mode = revision.mode
            override.custom_display = dict(revision.custom_display)
            override.source_version = revision.source_version
            override.version += 1
            await self._snapshot(session, override)
            await self._audit(
                session,
                scope,
                "card_content_override.rollback",
                override.id,
                trace_id,
                {
                    "card_id": card_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "restored_revision": revision_version,
                    "version": override.version,
                },
            )
            await session.flush()
            await session.refresh(override)
            return _override_record(override)

    async def public_recommendations(
        self, *, card_slug: str, query: str | None, limit: int
    ) -> list[PublicRecommendation]:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            products = (
                await session.scalars(
                    select(Product)
                    .where(
                        Product.tenant_id == scope.tenant_id,
                        Product.company_id == scope.company_id,
                        Product.status == ContentStatus.PUBLISHED,
                        Product.visibility == Visibility.PUBLIC,
                        Product.deleted_at.is_(None),
                        Product.published_at.is_not(None),
                        Product.published_at <= func.now(),
                    )
                    .order_by(Product.published_at.desc())
                    .limit(limit * 3)
                )
            ).all()
            cases = (
                await session.scalars(
                    select(CaseStudy)
                    .where(
                        CaseStudy.tenant_id == scope.tenant_id,
                        CaseStudy.company_id == scope.company_id,
                        CaseStudy.status == ContentStatus.PUBLISHED,
                        CaseStudy.visibility == Visibility.PUBLIC,
                        CaseStudy.deleted_at.is_(None),
                        CaseStudy.published_at.is_not(None),
                        CaseStudy.published_at <= func.now(),
                    )
                    .order_by(CaseStudy.published_at.desc())
                    .limit(limit * 3)
                )
            ).all()
            knowledge_rows = (
                await session.execute(
                    select(KnowledgeDocument, KnowledgeVersion.raw_text)
                    .join(
                        KnowledgeVersion,
                        KnowledgeVersion.id == KnowledgeDocument.current_version_id,
                    )
                    .where(
                        KnowledgeDocument.tenant_id == scope.tenant_id,
                        KnowledgeDocument.company_id == scope.company_id,
                        KnowledgeDocument.status == ContentStatus.PUBLISHED,
                        KnowledgeVersion.tenant_id == scope.tenant_id,
                        KnowledgeVersion.company_id == scope.company_id,
                        KnowledgeVersion.review_status == ReviewStatus.APPROVED,
                        exists(
                            select(KnowledgeChunk.id).where(
                                KnowledgeChunk.tenant_id == scope.tenant_id,
                                KnowledgeChunk.company_id == scope.company_id,
                                KnowledgeChunk.document_id == KnowledgeDocument.id,
                                KnowledgeChunk.version_id == KnowledgeDocument.current_version_id,
                                KnowledgeChunk.is_active.is_(True),
                                KnowledgeChunk.visibility == Visibility.PUBLIC,
                            )
                        ),
                    )
                    .order_by(KnowledgeDocument.updated_at.desc())
                    .limit(limit * 3)
                )
            ).all()
            candidates: list[tuple[ResourceType, Any, str, str, str]] = (
                [
                    ("product", row, row.name, row.summary, f"/products/{row.slug}")
                    for row in products
                ]
                + [
                    ("case_study", row, row.title, row.result, f"/cases/{row.slug}")
                    for row in cases
                ]
                + [
                    (
                        "knowledge_document",
                        document,
                        document.title,
                        raw_text.strip()[:1000] or document.title,
                        "/",
                    )
                    for document, raw_text in knowledge_rows
                ]
            )
            query_terms = {item.casefold() for item in (query or "").split() if len(item) >= 2}
            if query_terms:
                candidates.sort(
                    key=lambda row: sum(
                        term in f"{row[2]} {row[3]}".casefold() for term in query_terms
                    ),
                    reverse=True,
                )
            output: list[PublicRecommendation] = []
            for resource_type, source, title, summary, url in candidates:
                resolved = (
                    await effective_overrides(
                        session, scope=scope, resource_type=resource_type, resource_ids=[source.id]
                    )
                )[source.id]
                if not resolved.visible:
                    continue
                display = resolved.custom_display
                visible_title = str(display.get("title") or title)
                visible_summary = str(display.get("summary") or summary)
                reason_code = (
                    "context_match"
                    if query_terms
                    and any(term in f"{title} {summary}".casefold() for term in query_terms)
                    else ("card_featured" if resolved.mode == "custom" else "recently_published")
                )
                reason = {
                    "context_match": "与您当前关注的问题相关",
                    "card_featured": "该名片重点展示此内容",
                    "recently_published": "企业近期公开发布",
                }[reason_code]
                output.append(
                    PublicRecommendation(
                        resource_type=resource_type,
                        resource_id=source.id,
                        title=visible_title,
                        summary=visible_summary[:1000],
                        url=url,
                        reason_code=reason_code,
                        reason=reason,
                        evidence=RecommendationEvidence(
                            source_type=resource_type,
                            source_id=source.id,
                            source_version=source.version,
                            title=visible_title,
                            excerpt=visible_summary[:500] or visible_title,
                        ),
                    )
                )
                if len(output) >= limit:
                    break
            return output

    async def _resource(
        self,
        session: AsyncSession,
        scope: EnterpriseContentScope,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> Any:
        model: type[Any] = {
            "product": Product,
            "case_study": CaseStudy,
            "knowledge_document": KnowledgeDocument,
        }[resource_type]
        statement = select(model).where(
            model.tenant_id == scope.tenant_id,
            model.company_id == scope.company_id,
            model.id == resource_id,
        )
        if hasattr(model, "deleted_at"):
            statement = statement.where(model.deleted_at.is_(None))
        row = await session.scalar(statement)
        if row is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "统一内容不存在或不在当前企业作用域")
        return row

    async def _distribution(
        self,
        session: AsyncSession,
        scope: EnterpriseContentScope,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> EnterpriseContentDistribution | None:
        statement = select(EnterpriseContentDistribution).where(
            EnterpriseContentDistribution.tenant_id == scope.tenant_id,
            EnterpriseContentDistribution.company_id == scope.company_id,
            EnterpriseContentDistribution.resource_type == DistributedContentType(resource_type),
            EnterpriseContentDistribution.resource_id == resource_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def _override(
        self,
        session: AsyncSession,
        scope: EnterpriseContentScope,
        card_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> CardContentOverride | None:
        statement = select(CardContentOverride).where(
            CardContentOverride.tenant_id == scope.tenant_id,
            CardContentOverride.company_id == scope.company_id,
            CardContentOverride.card_id == card_id,
            CardContentOverride.resource_type == DistributedContentType(resource_type),
            CardContentOverride.resource_id == resource_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def _card(
        self, session: AsyncSession, scope: EnterpriseContentScope, card_id: uuid.UUID
    ) -> Card:
        card = await session.scalar(
            select(Card).where(*_managed_card_filters(scope), Card.id == card_id)
        )
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在或不在当前作用域")
        return card

    @staticmethod
    async def _snapshot(session: AsyncSession, override: CardContentOverride) -> None:
        session.add(
            CardContentOverrideRevision(
                id=uuid.uuid4(),
                tenant_id=override.tenant_id,
                company_id=override.company_id,
                override_id=override.id,
                version=override.version,
                mode=override.mode,
                custom_display=dict(override.custom_display or {}),
                source_version=override.source_version,
            )
        )

    @staticmethod
    async def _set_scope(session: AsyncSession, scope: EnterpriseContentScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
        )

    @staticmethod
    async def _audit(
        session: AsyncSession,
        scope: EnterpriseContentScope,
        action: str,
        resource_id: uuid.UUID,
        trace_id: str | None,
        event_data: dict[str, Any],
    ) -> None:
        await append_audit(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
            action=action,
            resource_type="enterprise_content_distribution",
            resource_id=resource_id,
            trace_id=trace_id,
            event_data=event_data,
        )


def _distribution_record(
    row: EnterpriseContentDistribution, *, implicit: bool = False
) -> DistributionRecord:
    return DistributionRecord(
        id=row.id,
        resource_type=row.resource_type.value,
        resource_id=row.resource_id,
        is_default_visible=row.is_default_visible,
        version=row.version if not implicit else 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _override_record(row: CardContentOverride) -> OverrideRecord:
    return OverrideRecord(
        id=row.id,
        card_id=row.card_id,
        resource_type=row.resource_type.value,
        resource_id=row.resource_id,
        mode=row.mode.value,
        custom_display=dict(row.custom_display or {}),
        source_version=row.source_version,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _revision_record(row: CardContentOverrideRevision) -> OverrideRevisionRecord:
    return OverrideRevisionRecord(
        version=row.version,
        mode=row.mode.value,
        custom_display=dict(row.custom_display or {}),
        source_version=row.source_version,
        created_at=row.created_at,
    )

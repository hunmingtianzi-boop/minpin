from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.catalog_schemas import (
    CaseStudyRecord,
    CreateCardRequest,
    CreateCaseStudyRequest,
    CreateForbiddenTopicRequest,
    CreateProductRequest,
    ForbiddenTopicRecord,
    ManagedCardRecord,
    ProductRecord,
    PublicCaseStudyRecord,
    PublicProductRecord,
    UpdateCaseStudyRequest,
    UpdateForbiddenTopicRequest,
    UpdateManagedCardRequest,
    UpdateProductRequest,
    validate_safe_asset_url,
)
from app.api.errors import ApiError
from app.db.models import (
    Card,
    CaseStudy,
    ContentStatus,
    ForbiddenTopic,
    LifecycleStatus,
    Membership,
    Product,
    Visibility,
)
from app.db.session import resolve_public_card_scope, set_rls_context
from app.services.audit import append_audit
from app.services.enterprise_content_store import effective_overrides

_CARD_SLUG_ATTEMPTS = 8


@dataclass(frozen=True, slots=True)
class CatalogScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


@dataclass(frozen=True, slots=True)
class ForbiddenTopicRule:
    id: uuid.UUID
    topic: str
    match_terms: tuple[str, ...]
    action: str
    safe_response: str | None
    version: int


def generate_card_slug() -> str:
    """Return a URL-safe card slug with 144 bits of cryptographic entropy."""

    return f"c-{secrets.token_hex(18)}"


def require_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "资源已被其他操作更新，请刷新后重试",
            details={"current_version": current},
        )


def company_scope_filters(model: Any, scope: CatalogScope) -> tuple[Any, ...]:
    return (
        model.tenant_id == scope.tenant_id,
        model.company_id == scope.company_id,
    )


def managed_card_filters(scope: CatalogScope) -> tuple[Any, ...]:
    filters: list[Any] = [
        Card.tenant_id == scope.tenant_id,
        Card.company_id == scope.company_id,
        Card.deleted_at.is_(None),
    ]
    if scope.is_card_owner:
        filters.append(Card.owner_user_id == scope.actor_user_id)
    return tuple(filters)


def public_content_filters(
    model: Any,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
) -> tuple[Any, ...]:
    return (
        model.tenant_id == tenant_id,
        model.company_id == company_id,
        model.deleted_at.is_(None),
        model.status == ContentStatus.PUBLISHED,
        model.visibility == Visibility.PUBLIC,
        model.published_at.is_not(None),
        model.published_at <= func.now(),
    )


def is_public_content(
    *,
    status: ContentStatus,
    visibility: Visibility,
    published_at: datetime | None,
    deleted_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    return (
        deleted_at is None
        and status == ContentStatus.PUBLISHED
        and visibility == Visibility.PUBLIC
        and published_at is not None
        and published_at <= current
    )


class CatalogStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        public_card_base_url: str = "http://127.0.0.1:4173",
        slug_factory: Callable[[], str] = generate_card_slug,
    ) -> None:
        self._sessions = session_factory
        self._public_card_base_url = _normalize_public_base_url(public_card_base_url)
        self._slug_factory = slug_factory

    async def list_products(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
    ) -> tuple[list[ProductRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [*company_scope_filters(Product, scope), Product.deleted_at.is_(None)]
            if status is not None:
                filters.append(Product.status == status)
            total = int(
                await session.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
            )
            rows = (
                await session.scalars(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.sort_order, Product.updated_at.desc(), Product.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_product_record(row) for row in rows], total

    async def get_product(self, *, scope: CatalogScope, product_id: uuid.UUID) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _product_record(await self._product(session, scope, product_id))

    async def create_product(
        self,
        *,
        scope: CatalogScope,
        body: CreateProductRequest,
        trace_id: str | None = None,
    ) -> ProductRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                await self._ensure_product_slug_available(session, scope, body.slug)
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    status=ContentStatus.DRAFT,
                    version=1,
                    **_product_values(body),
                )
                session.add(product)
                await self._audit(
                    session,
                    scope=scope,
                    action="product.create",
                    resource_type="product",
                    resource_id=product.id,
                    trace_id=trace_id,
                    event_data={"slug": product.slug, "version": product.version},
                )
                await session.flush()
                await session.refresh(product)
                return _product_record(product)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_products_company_slug"):
                raise _slug_conflict("产品") from exc
            raise

    async def update_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        body: UpdateProductRequest,
        trace_id: str | None = None,
    ) -> ProductRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                product = await self._product(session, scope, product_id, for_update=True)
                require_version(product.version, expected_version)
                if body.slug != product.slug:
                    await self._ensure_product_slug_available(
                        session, scope, body.slug, exclude_id=product.id
                    )
                for key, value in _product_values(body).items():
                    setattr(product, key, value)
                product.version += 1
                await self._audit(
                    session,
                    scope=scope,
                    action="product.update",
                    resource_type="product",
                    resource_id=product.id,
                    trace_id=trace_id,
                    event_data={"slug": product.slug, "version": product.version},
                )
                await session.flush()
                await session.refresh(product)
                return _product_record(product)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_products_company_slug"):
                raise _slug_conflict("产品") from exc
            raise

    async def publish_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            _ensure_product_publishable(product)
            _publish_resource(product, label="产品")
            await self._audit(
                session,
                scope=scope,
                action="product.publish",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )
            await session.flush()
            await session.refresh(product)
            return _product_record(product)

    async def archive_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            _archive_resource(product, label="产品")
            await self._audit(
                session,
                scope=scope,
                action="product.archive",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )
            await session.flush()
            await session.refresh(product)
            return _product_record(product)

    async def delete_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            product.status = ContentStatus.ARCHIVED
            product.deleted_at = datetime.now(UTC)
            product.deleted_by = scope.actor_user_id
            product.version += 1
            await self._audit(
                session,
                scope=scope,
                action="product.delete",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )

    async def list_case_studies(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
    ) -> tuple[list[CaseStudyRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [*company_scope_filters(CaseStudy, scope), CaseStudy.deleted_at.is_(None)]
            if status is not None:
                filters.append(CaseStudy.status == status)
            total = int(
                await session.scalar(select(func.count()).select_from(CaseStudy).where(*filters))
                or 0
            )
            rows = (
                await session.scalars(
                    select(CaseStudy)
                    .where(*filters)
                    .order_by(CaseStudy.sort_order, CaseStudy.updated_at.desc(), CaseStudy.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_case_study_record(row) for row in rows], total

    async def get_case_study(
        self, *, scope: CatalogScope, case_study_id: uuid.UUID
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _case_study_record(await self._case_study(session, scope, case_study_id))

    async def create_case_study(
        self,
        *,
        scope: CatalogScope,
        body: CreateCaseStudyRequest,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                await self._ensure_case_slug_available(session, scope, body.slug)
                case_study = CaseStudy(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    status=ContentStatus.DRAFT,
                    version=1,
                    **_case_study_values(body),
                )
                session.add(case_study)
                await self._audit(
                    session,
                    scope=scope,
                    action="case_study.create",
                    resource_type="case_study",
                    resource_id=case_study.id,
                    trace_id=trace_id,
                    event_data={"slug": case_study.slug, "version": case_study.version},
                )
                await session.flush()
                await session.refresh(case_study)
                return _case_study_record(case_study)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_case_studies_company_slug"):
                raise _slug_conflict("案例") from exc
            raise

    async def update_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        body: UpdateCaseStudyRequest,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                case_study = await self._case_study(session, scope, case_study_id, for_update=True)
                require_version(case_study.version, expected_version)
                if body.slug != case_study.slug:
                    await self._ensure_case_slug_available(
                        session, scope, body.slug, exclude_id=case_study.id
                    )
                for key, value in _case_study_values(body).items():
                    setattr(case_study, key, value)
                case_study.version += 1
                await self._audit(
                    session,
                    scope=scope,
                    action="case_study.update",
                    resource_type="case_study",
                    resource_id=case_study.id,
                    trace_id=trace_id,
                    event_data={"slug": case_study.slug, "version": case_study.version},
                )
                await session.flush()
                await session.refresh(case_study)
                return _case_study_record(case_study)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_case_studies_company_slug"):
                raise _slug_conflict("案例") from exc
            raise

    async def publish_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            _ensure_case_study_publishable(case_study)
            _publish_resource(case_study, label="案例")
            await self._audit(
                session,
                scope=scope,
                action="case_study.publish",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )
            await session.flush()
            await session.refresh(case_study)
            return _case_study_record(case_study)

    async def archive_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            _archive_resource(case_study, label="案例")
            await self._audit(
                session,
                scope=scope,
                action="case_study.archive",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )
            await session.flush()
            await session.refresh(case_study)
            return _case_study_record(case_study)

    async def delete_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            case_study.status = ContentStatus.ARCHIVED
            case_study.deleted_at = datetime.now(UTC)
            case_study.deleted_by = scope.actor_user_id
            case_study.version += 1
            await self._audit(
                session,
                scope=scope,
                action="case_study.delete",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )

    async def list_forbidden_topics(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        active: bool | None = None,
    ) -> tuple[list[ForbiddenTopicRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = list(company_scope_filters(ForbiddenTopic, scope))
            if active is not None:
                filters.append(ForbiddenTopic.is_active.is_(active))
            total = int(
                await session.scalar(
                    select(func.count()).select_from(ForbiddenTopic).where(*filters)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(ForbiddenTopic)
                    .where(*filters)
                    .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_forbidden_topic_record(row) for row in rows], total

    async def get_forbidden_topic(
        self, *, scope: CatalogScope, topic_id: uuid.UUID
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _forbidden_topic_record(await self._forbidden_topic(session, scope, topic_id))

    async def create_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        body: CreateForbiddenTopicRequest,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = ForbiddenTopic(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                topic=body.topic,
                match_terms=body.match_terms,
                action=body.action,
                safe_response=body.safe_response,
                is_active=body.is_active,
                version=1,
            )
            session.add(topic)
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.create",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": topic.is_active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def update_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        body: UpdateForbiddenTopicRequest,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            topic.topic = body.topic
            topic.match_terms = body.match_terms
            topic.action = body.action
            topic.safe_response = body.safe_response
            topic.version += 1
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.update",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": topic.is_active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def set_forbidden_topic_active(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        active: bool,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            if topic.is_active is active:
                raise ApiError(409, "INVALID_STATE", "禁答主题已经处于目标状态")
            topic.is_active = active
            topic.version += 1
            await self._audit(
                session,
                scope=scope,
                action=("forbidden_topic.activate" if active else "forbidden_topic.deactivate"),
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def delete_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.delete",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"version": topic.version},
            )
            await session.delete(topic)

    async def active_forbidden_topics(
        self, *, scope: CatalogScope
    ) -> tuple[ForbiddenTopicRule, ...]:
        """Stable query seam for RAG policy composition; it does not mutate chat flow."""

        return await self.query_active_forbidden_topics(
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    async def query_active_forbidden_topics(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> tuple[ForbiddenTopicRule, ...]:
        """Read active rules from a trusted RAG runtime that has no staff actor."""

        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            rows = (
                await session.scalars(
                    select(ForbiddenTopic)
                    .where(
                        ForbiddenTopic.tenant_id == tenant_id,
                        ForbiddenTopic.company_id == company_id,
                        ForbiddenTopic.is_active.is_(True),
                    )
                    .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                )
            ).all()
            return tuple(
                ForbiddenTopicRule(
                    id=row.id,
                    topic=row.topic,
                    match_terms=tuple(row.match_terms or ()),
                    action=row.action,
                    safe_response=row.safe_response,
                    version=row.version,
                )
                for row in rows
            )

    async def list_cards(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
    ) -> tuple[list[ManagedCardRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = list(managed_card_filters(scope))
            if status is not None:
                filters.append(Card.status == status)
            total = int(
                await session.scalar(select(func.count()).select_from(Card).where(*filters)) or 0
            )
            rows = (
                await session.scalars(
                    select(Card)
                    .where(*filters)
                    .order_by(Card.updated_at.desc(), Card.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [self._managed_card_record(row) for row in rows], total

    async def get_card(self, *, scope: CatalogScope, card_id: uuid.UUID) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return self._managed_card_record(await self._card(session, scope, card_id))

    async def create_card(
        self,
        *,
        scope: CatalogScope,
        body: CreateCardRequest,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        owner_user_id = body.owner_user_id or scope.actor_user_id
        if scope.is_card_owner and owner_user_id != scope.actor_user_id:
            raise ApiError(403, "FORBIDDEN", "名片所有者只能为当前账号")
        for _attempt in range(_CARD_SLUG_ATTEMPTS):
            slug = self._slug_factory()
            try:
                return await self._create_card_attempt(
                    scope=scope,
                    body=body,
                    owner_user_id=owner_user_id,
                    slug=slug,
                    trace_id=trace_id,
                )
            except IntegrityError as exc:
                if _has_constraint(exc, "uq_cards_slug"):
                    continue
                raise
        raise ApiError(503, "CARD_SLUG_UNAVAILABLE", "暂时无法生成安全的名片链接，请重试")

    async def _create_card_attempt(
        self,
        *,
        scope: CatalogScope,
        body: CreateCardRequest,
        owner_user_id: uuid.UUID,
        slug: str,
        trace_id: str | None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._validate_owner(session, scope, owner_user_id)
            card = Card(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                owner_user_id=owner_user_id,
                slug=slug,
                display_name=body.display_name,
                status=ContentStatus.DRAFT,
                settings=_card_settings(body),
                version=1,
            )
            session.add(card)
            await self._audit(
                session,
                scope=scope,
                action="card.create",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={
                    "owner_user_id": owner_user_id,
                    "slug": slug,
                    "version": card.version,
                },
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card)

    async def update_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        body: UpdateManagedCardRequest,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        if scope.is_card_owner and body.owner_user_id != scope.actor_user_id:
            raise ApiError(403, "FORBIDDEN", "名片所有者不能转移给其他账号")
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            if body.owner_user_id != card.owner_user_id:
                await self._validate_owner(session, scope, body.owner_user_id)
            card.owner_user_id = body.owner_user_id
            card.display_name = body.display_name
            card.settings = _card_settings(body)
            card.version += 1
            await self._audit(
                session,
                scope=scope,
                action="card.update",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={
                    "owner_user_id": card.owner_user_id,
                    "slug": card.slug,
                    "version": card.version,
                },
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card)

    async def publish_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            _ensure_card_publishable(card)
            _publish_resource(card, label="名片")
            await self._audit(
                session,
                scope=scope,
                action="card.publish",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"slug": card.slug, "version": card.version},
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card)

    async def deactivate_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            _archive_resource(card, label="名片")
            await self._audit(
                session,
                scope=scope,
                action="card.deactivate",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"slug": card.slug, "version": card.version},
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card)

    async def list_public_products(
        self,
        *,
        card_slug: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PublicProductRecord], int]:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            filters = public_content_filters(
                Product,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            rows = (
                await session.scalars(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.sort_order, Product.published_at.desc(), Product.id)
                )
            ).all()
            overrides = await effective_overrides(
                session, scope=scope, resource_type="product", resource_ids=[row.id for row in rows]
            )
            records = [
                _public_product_record(row, overrides[row.id].custom_display)
                for row in rows
                if overrides[row.id].visible
            ]
            records.sort(key=lambda item: (item.sort_order, item.published_at, item.slug))
            return records[offset : offset + limit], len(records)

    async def get_public_product(self, *, card_slug: str, product_slug: str) -> PublicProductRecord:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            product = await session.scalar(
                select(Product).where(
                    *public_content_filters(
                        Product,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                    ),
                    _public_identifier_filter(Product, product_slug),
                )
            )
            if product is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或尚未公开")
            resolved = (
                await effective_overrides(
                    session, scope=scope, resource_type="product", resource_ids=[product.id]
                )
            )[product.id]
            if not resolved.visible:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或尚未公开")
            return _public_product_record(product, resolved.custom_display)

    async def list_public_case_studies(
        self,
        *,
        card_slug: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PublicCaseStudyRecord], int]:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            filters = public_content_filters(
                CaseStudy,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            rows = (
                await session.scalars(
                    select(CaseStudy)
                    .where(*filters)
                    .order_by(CaseStudy.sort_order, CaseStudy.published_at.desc(), CaseStudy.id)
                )
            ).all()
            overrides = await effective_overrides(
                session,
                scope=scope,
                resource_type="case_study",
                resource_ids=[row.id for row in rows],
            )
            records = [
                _public_case_study_record(row, overrides[row.id].custom_display)
                for row in rows
                if overrides[row.id].visible
            ]
            records.sort(key=lambda item: (item.sort_order, item.published_at, item.slug))
            return records[offset : offset + limit], len(records)

    async def get_public_case_study(
        self, *, card_slug: str, case_study_slug: str
    ) -> PublicCaseStudyRecord:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            case_study = await session.scalar(
                select(CaseStudy).where(
                    *public_content_filters(
                        CaseStudy,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                    ),
                    _public_identifier_filter(CaseStudy, case_study_slug),
                )
            )
            if case_study is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或尚未公开")
            resolved = (
                await effective_overrides(
                    session, scope=scope, resource_type="case_study", resource_ids=[case_study.id]
                )
            )[case_study.id]
            if not resolved.visible:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或尚未公开")
            return _public_case_study_record(case_study, resolved.custom_display)

    async def _set_scope(self, session: AsyncSession, scope: CatalogScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    async def _product(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        product_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Product:
        statement = select(Product).where(
            *company_scope_filters(Product, scope),
            Product.id == product_id,
            Product.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        product = await session.scalar(statement)
        if product is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或不在当前作用域")
        return product

    async def _case_study(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> CaseStudy:
        statement = select(CaseStudy).where(
            *company_scope_filters(CaseStudy, scope),
            CaseStudy.id == case_study_id,
            CaseStudy.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        case_study = await session.scalar(statement)
        if case_study is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或不在当前作用域")
        return case_study

    async def _forbidden_topic(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ForbiddenTopic:
        statement = select(ForbiddenTopic).where(
            *company_scope_filters(ForbiddenTopic, scope),
            ForbiddenTopic.id == topic_id,
        )
        if for_update:
            statement = statement.with_for_update()
        topic = await session.scalar(statement)
        if topic is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "禁答主题不存在或不在当前作用域")
        return topic

    async def _card(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        card_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Card:
        statement = select(Card).where(*managed_card_filters(scope), Card.id == card_id)
        if for_update:
            statement = statement.with_for_update()
        card = await session.scalar(statement)
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在或不在当前作用域")
        return card

    async def _ensure_product_slug_available(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        slug: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(Product.id).where(
            *company_scope_filters(Product, scope),
            Product.slug == slug,
        )
        if exclude_id is not None:
            statement = statement.where(Product.id != exclude_id)
        if await session.scalar(statement) is not None:
            raise _slug_conflict("产品")

    async def _ensure_case_slug_available(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        slug: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(CaseStudy.id).where(
            *company_scope_filters(CaseStudy, scope),
            CaseStudy.slug == slug,
        )
        if exclude_id is not None:
            statement = statement.where(CaseStudy.id != exclude_id)
        if await session.scalar(statement) is not None:
            raise _slug_conflict("案例")

    async def _validate_owner(
        self, session: AsyncSession, scope: CatalogScope, owner_user_id: uuid.UUID
    ) -> None:
        membership_id = await session.scalar(
            select(Membership.id).where(
                Membership.user_id == owner_user_id,
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
                Membership.status == LifecycleStatus.ACTIVE,
            )
        )
        if membership_id is None:
            raise ApiError(422, "INVALID_CARD_OWNER", "名片所有者不是当前企业的有效成员")

    async def _audit(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        trace_id: str | None,
        event_data: dict[str, Any],
    ) -> None:
        await append_audit(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            trace_id=trace_id,
            event_data=event_data,
        )

    def _managed_card_record(self, card: Card) -> ManagedCardRecord:
        settings = _dict_value(card.settings)
        share_url = f"{self._public_card_base_url}/c/{card.slug}"
        return ManagedCardRecord(
            id=card.id,
            owner_user_id=card.owner_user_id,
            slug=card.slug,
            display_name=card.display_name,
            title=_string_value(settings.get("title")) or card.display_name,
            avatar_url=_string_value(settings.get("avatar_url")),
            assistant_name=_string_value(settings.get("assistant_name")),
            welcome_message=_string_value(settings.get("welcome_message")),
            suggested_questions=_string_list(settings.get("suggested_questions"), limit=6),
            policy_versions=_string_dict(settings.get("policy_versions")),
            status=card.status.value,
            published_at=card.published_at,
            version=card.version,
            share_url=share_url,
            qr_url=share_url,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )


def _product_values(body: CreateProductRequest | UpdateProductRequest) -> dict[str, Any]:
    return {
        "slug": body.slug,
        "name": body.name,
        "category": body.category,
        "summary": body.summary,
        "detail": body.detail,
        "audience": body.audience,
        "price_boundary": body.price_boundary,
        "image_url": body.image_url,
        "visibility": Visibility(body.visibility),
        "sort_order": body.sort_order,
        "settings": dict(body.settings),
    }


def _case_study_values(
    body: CreateCaseStudyRequest | UpdateCaseStudyRequest,
) -> dict[str, Any]:
    return {
        "slug": body.slug,
        "title": body.title,
        "industry": body.industry,
        "background": body.background,
        "solution": body.solution,
        "result": body.result,
        "client_display_name": body.client_display_name,
        "image_url": body.image_url,
        "visibility": Visibility(body.visibility),
        "sort_order": body.sort_order,
        "settings": dict(body.settings),
    }


def _card_settings(body: CreateCardRequest | UpdateManagedCardRequest) -> dict[str, Any]:
    return {
        "title": body.title,
        "avatar_url": body.avatar_url,
        "assistant_name": body.assistant_name,
        "welcome_message": body.welcome_message,
        "suggested_questions": list(body.suggested_questions),
        "policy_versions": dict(body.policy_versions),
    }


def _product_record(product: Product) -> ProductRecord:
    return ProductRecord(
        id=product.id,
        slug=product.slug,
        name=product.name,
        category=product.category,
        summary=product.summary,
        detail=product.detail,
        audience=product.audience,
        price_boundary=product.price_boundary,
        image_url=product.image_url,
        visibility=product.visibility.value,
        sort_order=product.sort_order,
        settings=_dict_value(product.settings),
        status=product.status.value,
        published_at=product.published_at,
        version=product.version,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _case_study_record(case_study: CaseStudy) -> CaseStudyRecord:
    return CaseStudyRecord(
        id=case_study.id,
        slug=case_study.slug,
        title=case_study.title,
        industry=case_study.industry,
        background=case_study.background,
        solution=case_study.solution,
        result=case_study.result,
        client_display_name=case_study.client_display_name,
        image_url=case_study.image_url,
        visibility=case_study.visibility.value,
        sort_order=case_study.sort_order,
        settings=_dict_value(case_study.settings),
        status=case_study.status.value,
        published_at=case_study.published_at,
        version=case_study.version,
        created_at=case_study.created_at,
        updated_at=case_study.updated_at,
    )


def _forbidden_topic_record(topic: ForbiddenTopic) -> ForbiddenTopicRecord:
    return ForbiddenTopicRecord(
        id=topic.id,
        topic=topic.topic,
        match_terms=list(topic.match_terms or ()),
        action=topic.action,
        safe_response=topic.safe_response,
        is_active=topic.is_active,
        version=topic.version,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


def _public_product_record(
    product: Product, display: dict[str, Any] | None = None
) -> PublicProductRecord:
    if product.published_at is None:
        raise RuntimeError("public product is missing published_at")
    custom = display or {}
    return PublicProductRecord(
        slug=product.slug,
        name=str(custom.get("title") or product.name),
        category=product.category,
        summary=str(custom.get("summary") or product.summary),
        detail=product.detail,
        audience=product.audience,
        price_boundary=product.price_boundary,
        image_url=str(custom.get("image_url") or product.image_url)
        if (custom.get("image_url") or product.image_url)
        else None,
        sort_order=int(custom.get("sort_order", product.sort_order)),
        published_at=product.published_at,
    )


def _public_case_study_record(
    case_study: CaseStudy, display: dict[str, Any] | None = None
) -> PublicCaseStudyRecord:
    if case_study.published_at is None:
        raise RuntimeError("public case study is missing published_at")
    custom = display or {}
    return PublicCaseStudyRecord(
        slug=case_study.slug,
        title=str(custom.get("title") or case_study.title),
        industry=case_study.industry,
        background=case_study.background,
        solution=case_study.solution,
        result=case_study.result,
        client_display_name=case_study.client_display_name,
        image_url=str(custom.get("image_url") or case_study.image_url)
        if (custom.get("image_url") or case_study.image_url)
        else None,
        sort_order=int(custom.get("sort_order", case_study.sort_order)),
        published_at=case_study.published_at,
    )


def _ensure_product_publishable(product: Product) -> None:
    missing = [
        field
        for field, value in {
            "name": product.name,
            "summary": product.summary,
            "detail": product.detail,
        }.items()
        if not isinstance(value, str) or not value.strip()
    ]
    _ensure_publishable_asset(product.image_url, missing=missing, field_name="image_url")
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "产品信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_case_study_publishable(case_study: CaseStudy) -> None:
    missing = [
        field
        for field, value in {
            "title": case_study.title,
            "background": case_study.background,
            "solution": case_study.solution,
            "result": case_study.result,
        }.items()
        if not isinstance(value, str) or not value.strip()
    ]
    _ensure_publishable_asset(case_study.image_url, missing=missing, field_name="image_url")
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "案例信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_card_publishable(card: Card) -> None:
    settings = _dict_value(card.settings)
    missing: list[str] = []
    if not card.display_name.strip():
        missing.append("display_name")
    if not (_string_value(settings.get("title")) or "").strip():
        missing.append("title")
    _ensure_publishable_asset(
        _string_value(settings.get("avatar_url")),
        missing=missing,
        field_name="avatar_url",
    )
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "名片信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_publishable_asset(
    value: str | None,
    *,
    missing: list[str],
    field_name: str,
) -> None:
    try:
        validate_safe_asset_url(value)
    except ValueError:
        missing.append(field_name)


def _publish_resource(resource: Any, *, label: str) -> None:
    if resource.status == ContentStatus.PUBLISHED:
        raise ApiError(409, "INVALID_STATE", f"{label}已经发布")
    resource.status = ContentStatus.PUBLISHED
    resource.published_at = datetime.now(UTC)
    resource.version += 1


def _archive_resource(resource: Any, *, label: str) -> None:
    if resource.status == ContentStatus.ARCHIVED:
        raise ApiError(409, "INVALID_STATE", f"{label}已经归档")
    resource.status = ContentStatus.ARCHIVED
    resource.version += 1


def _slug_conflict(label: str) -> ApiError:
    return ApiError(409, "SLUG_CONFLICT", f"{label}链接标识已存在，请更换后重试")


def _public_identifier_filter(model: Any, value: str) -> Any:
    try:
        resource_id = uuid.UUID(value)
    except ValueError:
        return model.slug == value
    return or_(model.id == resource_id, model.slug == value)


def _has_constraint(exc: IntegrityError, name: str) -> bool:
    candidates: list[object | None] = [exc, exc.orig]
    candidates.extend(
        [
            getattr(exc.orig, "__cause__", None),
            getattr(exc.orig, "__context__", None),
        ]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        diagnostic = getattr(candidate, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", None) or getattr(
            candidate, "constraint_name", None
        )
        if constraint == name or name in str(candidate):
            return True
    return False


def _normalize_public_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("public_card_base_url must be an absolute HTTP(S) origin or base path")
    if parsed.scheme.casefold() == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("non-local public_card_base_url must use HTTPS")
    return candidate


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:limit]


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


__all__ = [
    "CatalogScope",
    "CatalogStore",
    "ForbiddenTopicRule",
    "company_scope_filters",
    "generate_card_slug",
    "is_public_content",
    "managed_card_filters",
    "public_content_filters",
    "require_version",
]

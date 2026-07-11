from __future__ import annotations

import hashlib
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.admin_schemas import CreateKnowledgeDocumentRequest, PutKnowledgeDocumentRequest
from app.api.catalog_schemas import CaseStudyRecord, ProductRecord
from app.core.config import Settings
from app.db.models import KnowledgeDocument, KnowledgeVersion, ReviewStatus
from app.db.session import set_rls_context
from app.services.admin_store import AdminScope, AdminStore


class CatalogKnowledgeSynchronizer:
    """Index catalog drafts before their public status is atomically exposed."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        admin_store: AdminStore,
    ) -> None:
        self._sessions = session_factory
        self._admin = admin_store

    @classmethod
    def from_runtime(
        cls,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> "CatalogKnowledgeSynchronizer":
        return cls(
            session_factory=session_factory,
            admin_store=AdminStore.from_runtime(
                session_factory=session_factory,
                settings=settings,
                http_client=http_client,
            ),
        )

    async def sync_product(
        self,
        *,
        scope: AdminScope,
        product: ProductRecord,
        trace_id: str | None,
    ) -> uuid.UUID:
        raw_text = "\n\n".join(
            part
            for part in (
                f"产品名称：{product.name}",
                f"分类：{product.category}" if product.category else None,
                f"摘要：{product.summary}",
                f"详细介绍：{product.detail}",
                f"适用对象：{product.audience}" if product.audience else None,
                f"价格边界：{product.price_boundary}" if product.price_boundary else None,
            )
            if part
        )
        return await self._sync(
            scope=scope,
            source_type="product",
            source_id=str(product.id),
            title=product.name,
            raw_text=raw_text,
            metadata={
                "source_label": "企业已发布产品",
                "product_slug": product.slug,
                "catalog_version": product.version,
            },
            trace_id=trace_id,
        )

    async def sync_case_study(
        self,
        *,
        scope: AdminScope,
        case_study: CaseStudyRecord,
        trace_id: str | None,
    ) -> uuid.UUID:
        raw_text = "\n\n".join(
            part
            for part in (
                f"案例名称：{case_study.title}",
                f"行业：{case_study.industry}" if case_study.industry else None,
                f"背景：{case_study.background}",
                f"方案：{case_study.solution}",
                f"结果：{case_study.result}",
                (
                    f"客户展示名称：{case_study.client_display_name}"
                    if case_study.client_display_name
                    else None
                ),
            )
            if part
        )
        return await self._sync(
            scope=scope,
            source_type="case_study",
            source_id=str(case_study.id),
            title=case_study.title,
            raw_text=raw_text,
            metadata={
                "source_label": "企业已发布案例",
                "case_slug": case_study.slug,
                "catalog_version": case_study.version,
            },
            trace_id=trace_id,
        )

    async def _sync(
        self,
        *,
        scope: AdminScope,
        source_type: str,
        source_id: str,
        title: str,
        raw_text: str,
        metadata: dict[str, object],
        trace_id: str | None,
    ) -> uuid.UUID:
        document_id, current_hash = await self._find_document(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
        )
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if document_id is not None and current_hash == content_hash:
            return document_id
        if document_id is None:
            document = await self._admin.create_document(
                scope=scope,
                body=CreateKnowledgeDocumentRequest(
                    title=title,
                    source_type=source_type,
                    source_id=source_id,
                ),
                trace_id=trace_id,
            )
            document_id = document.id
        draft = await self._admin.put_document_draft(
            scope=scope,
            document_id=document_id,
            body=PutKnowledgeDocumentRequest(
                raw_text=raw_text,
                title=title,
                visibility="public",
                metadata=metadata,
            ),
            trace_id=trace_id,
        )
        await self._admin.publish_document(
            scope=scope,
            document_id=document_id,
            version_id=draft.draft_version.id,
            trace_id=trace_id,
        )
        return document_id

    async def _find_document(
        self,
        *,
        scope: AdminScope,
        source_type: str,
        source_id: str,
    ) -> tuple[uuid.UUID | None, str | None]:
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            document = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == scope.tenant_id,
                    KnowledgeDocument.company_id == scope.company_id,
                    KnowledgeDocument.source_type == source_type,
                    KnowledgeDocument.source_id == source_id,
                )
            )
            if document is None or document.current_version_id is None:
                return (document.id if document else None), None
            version = await session.scalar(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.id == document.current_version_id,
                    KnowledgeVersion.review_status == ReviewStatus.APPROVED,
                )
            )
            return document.id, version.content_hash if version else None


__all__ = ["CatalogKnowledgeSynchronizer"]

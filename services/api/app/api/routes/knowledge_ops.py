from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.admin_schemas import (
    CreateKnowledgeDocumentRequest,
    KnowledgeDraftEnvelope,
    KnowledgePublishEnvelope,
    PutKnowledgeDocumentRequest,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.knowledge_ops_schemas import (
    EvaluationJobEnvelope,
    FaqEnvelope,
    FaqListEnvelope,
    FaqWriteRequest,
    KnowledgeChunkListEnvelope,
    KnowledgeIndexJobEnvelope,
    KnowledgeIndexJobListEnvelope,
    KnowledgeVersionListEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.admin_store import AdminScope, AdminStore
from app.services.knowledge_ops_store import KnowledgeOpsScope, KnowledgeOpsStore

router = APIRouter(tags=["Knowledge Operations"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
_ADMIN_ROLES = {"company_admin", "platform_admin"}


def _scope(principal: StaffPrincipal) -> KnowledgeOpsScope:
    return KnowledgeOpsScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _admin_scope(principal: StaffPrincipal) -> AdminScope:
    return AdminScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _store(request: Request) -> KnowledgeOpsStore:
    return KnowledgeOpsStore(request.app.state.session_factory)


def _admin_store(request: Request) -> AdminStore:
    return AdminStore.from_runtime(
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
    )


def _require_permission(principal: StaffPrincipal, *permissions: str) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in _ADMIN_ROLES:
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection(permissions) or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有执行此操作的权限")


@router.get("/admin/faqs", response_model=FaqListEnvelope, operation_id="listAdminFaqs")
async def list_faqs(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FaqListEnvelope:
    _require_permission(principal, "knowledge.read", "knowledge.review")
    records, total = await _store(request).list_faqs(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return FaqListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/faqs",
    response_model=FaqEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminFaq",
)
async def create_faq(
    body: FaqWriteRequest,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    admin = _admin_store(request)
    document = await admin.create_document(
        scope=_admin_scope(principal),
        body=CreateKnowledgeDocumentRequest(title=body.question, source_type="faq"),
        trace_id=request_id_ctx.get(),
    )
    await admin.put_document_draft(
        scope=_admin_scope(principal),
        document_id=document.id,
        body=PutKnowledgeDocumentRequest(
            raw_text=body.answer,
            title=body.question,
            visibility=body.visibility,
            metadata={"source_label": "企业 FAQ"},
        ),
        trace_id=request_id_ctx.get(),
    )
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=document.id)
    )


@router.get(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="getAdminFaq",
)
async def get_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.read", "knowledge.review")
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    )


@router.patch(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="updateAdminFaq",
)
async def update_faq(
    faq_id: uuid.UUID,
    body: FaqWriteRequest,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    await _admin_store(request).put_document_draft(
        scope=_admin_scope(principal),
        document_id=faq_id,
        body=PutKnowledgeDocumentRequest(
            raw_text=body.answer,
            title=body.question,
            visibility=body.visibility,
            metadata={"source_label": "企业 FAQ"},
        ),
        trace_id=request_id_ctx.get(),
    )
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    )


@router.delete(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="archiveAdminFaq",
)
async def archive_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _store(request).archive_faq(
        scope=_scope(principal), document_id=faq_id, trace_id=request_id_ctx.get()
    )
    return FaqEnvelope(data=record)


@router.post(
    "/admin/faqs/{faq_id}:publish",
    response_model=KnowledgePublishEnvelope,
    operation_id="publishAdminFaq",
)
async def publish_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgePublishEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    result = await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=faq_id,
        version_id=None,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgePublishEnvelope(data=result)


@router.get(
    "/admin/knowledge/documents/{document_id}/versions",
    response_model=KnowledgeVersionListEnvelope,
    operation_id="listKnowledgeDocumentVersions",
)
async def list_document_versions(
    document_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeVersionListEnvelope:
    _require_permission(principal, "knowledge.read")
    records = await _store(request).list_versions(scope=_scope(principal), document_id=document_id)
    return KnowledgeVersionListEnvelope(data=records, total=len(records))


@router.post(
    "/admin/knowledge/documents/{document_id}/versions",
    response_model=KnowledgeDraftEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createKnowledgeDocumentVersion",
)
async def create_document_version(
    document_id: uuid.UUID,
    body: PutKnowledgeDocumentRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeDraftEnvelope:
    _require_permission(principal, "knowledge.write")
    result = await _admin_store(request).put_document_draft(
        scope=_admin_scope(principal),
        document_id=document_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeDraftEnvelope(data=result)


@router.post(
    "/admin/knowledge/versions/{version_id}:publish",
    response_model=KnowledgePublishEnvelope,
    operation_id="publishKnowledgeVersion",
)
async def publish_version(
    version_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgePublishEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    document_id = await _store(request).version_document(
        scope=_scope(principal), version_id=version_id
    )
    result = await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=document_id,
        version_id=version_id,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgePublishEnvelope(data=result)


@router.get(
    "/admin/knowledge/index-jobs",
    response_model=KnowledgeIndexJobListEnvelope,
    operation_id="listKnowledgeIndexJobs",
)
async def list_index_jobs(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    job_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(pending|running|succeeded|failed)$"),
    ] = None,
) -> KnowledgeIndexJobListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _store(request).list_index_jobs(
        scope=_scope(principal), limit=limit, offset=offset, status=job_status
    )
    return KnowledgeIndexJobListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/knowledge/index-jobs/{job_id}:retry",
    response_model=KnowledgeIndexJobEnvelope,
    operation_id="retryKnowledgeIndexJob",
)
async def retry_index_job(
    job_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeIndexJobEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    store = _store(request)
    target = await store.retry_target(scope=_scope(principal), job_id=job_id)
    await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=target.document_id,
        version_id=target.version_id,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeIndexJobEnvelope(
        data=await store.get_index_job(scope=_scope(principal), job_id=job_id)
    )


@router.get(
    "/admin/knowledge/chunks",
    response_model=KnowledgeChunkListEnvelope,
    operation_id="listKnowledgeChunks",
)
async def list_chunks(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_id: uuid.UUID | None = None,
) -> KnowledgeChunkListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _store(request).list_chunks(
        scope=_scope(principal), limit=limit, offset=offset, document_id=document_id
    )
    return KnowledgeChunkListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/knowledge:evaluate",
    response_model=EvaluationJobEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="evaluateKnowledge",
)
async def evaluate_knowledge(
    request: Request,
    principal: StaffDependency,
) -> EvaluationJobEnvelope:
    _require_permission(principal, "knowledge.review", "knowledge.publish")
    job = await _store(request).enqueue_evaluation(
        scope=_scope(principal), trace_id=request_id_ctx.get()
    )
    return EvaluationJobEnvelope(data=job)


__all__ = ["router"]

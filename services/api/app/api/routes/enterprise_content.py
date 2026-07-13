from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.dependencies import get_staff_principal
from app.api.enterprise_schemas import (
    DistributionEnvelope,
    DistributionWriteRequest,
    OverrideEnvelope,
    OverrideListEnvelope,
    OverrideRevisionListEnvelope,
    OverrideWriteRequest,
    RollbackOverrideRequest,
)
from app.api.errors import ApiError
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.enterprise_content_store import EnterpriseContentScope, EnterpriseContentStore

router = APIRouter(prefix="/admin", tags=["Enterprise Content Distribution"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
IfMatchDependency = Annotated[str, Header(alias="If-Match")]
_RESOURCE_TYPES = {"product", "case_study", "knowledge_document"}


def _scope(principal: StaffPrincipal) -> EnterpriseContentScope:
    if principal.company_id is None:
        raise ApiError(403, "COMPANY_SCOPE_REQUIRED", "请选择企业作用域后再执行此操作")
    return EnterpriseContentScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _require(principal: StaffPrincipal, *, write: bool) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in {"company_admin", "platform_admin"}:
        return
    granted = {str(value) for value in principal.permissions}
    required = {
        "enterprise_content.manage",
        "catalog.manage",
        "catalog.write" if write else "catalog.read",
    }
    if granted.intersection(required | {"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有管理企业统一内容的权限")


def _resource_type(value: str) -> str:
    if value not in _RESOURCE_TYPES:
        raise ApiError(
            422,
            "INVALID_RESOURCE_TYPE",
            "resource_type 必须是 product、case_study 或 knowledge_document",
        )
    return value


def _parse_if_match(value: str) -> int:
    candidate = value.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:].strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        candidate = candidate[1:-1]
    if not candidate.isascii() or not candidate.isdigit():
        raise ApiError(400, "INVALID_IF_MATCH", "If-Match 必须为资源版本号")
    return int(candidate)


def _store(request: Request) -> EnterpriseContentStore:
    override = getattr(request.app.state, "enterprise_content_store", None)
    return (
        override
        if override is not None
        else EnterpriseContentStore(request.app.state.session_factory)
    )


@router.get(
    "/content-distributions/{resource_type}/{resource_id}",
    response_model=DistributionEnvelope,
    operation_id="getEnterpriseContentDistribution",
)
async def get_distribution(
    resource_type: str, resource_id: uuid.UUID, request: Request, principal: StaffDependency
) -> DistributionEnvelope:
    _require(principal, write=False)
    return DistributionEnvelope(
        data=await _store(request).get_distribution(
            scope=_scope(principal),
            resource_type=_resource_type(resource_type),
            resource_id=resource_id,
        )
    )


@router.put(
    "/content-distributions/{resource_type}/{resource_id}",
    response_model=DistributionEnvelope,
    operation_id="putEnterpriseContentDistribution",
)
async def put_distribution(
    resource_type: str,
    resource_id: uuid.UUID,
    body: DistributionWriteRequest,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> DistributionEnvelope:
    _require(principal, write=True)
    return DistributionEnvelope(
        data=await _store(request).put_distribution(
            scope=_scope(principal),
            resource_type=_resource_type(resource_type),
            resource_id=resource_id,
            expected_version=_parse_if_match(if_match),
            body=body,
            trace_id=request_id_ctx.get(),
        )
    )


@router.get(
    "/cards/{card_id}/content-overrides",
    response_model=OverrideListEnvelope,
    operation_id="listCardContentOverrides",
)
async def list_overrides(
    card_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OverrideListEnvelope:
    _require(principal, write=False)
    rows, total = await _store(request).list_overrides(
        scope=_scope(principal), card_id=card_id, limit=limit, offset=offset
    )
    return OverrideListEnvelope(data=rows, total=total, limit=limit, offset=offset)


@router.put(
    "/cards/{card_id}/content-overrides/{resource_type}/{resource_id}",
    response_model=OverrideEnvelope,
    operation_id="putCardContentOverride",
)
async def put_override(
    card_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    body: OverrideWriteRequest,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> OverrideEnvelope:
    _require(principal, write=True)
    return OverrideEnvelope(
        data=await _store(request).put_override(
            scope=_scope(principal),
            card_id=card_id,
            resource_type=_resource_type(resource_type),
            resource_id=resource_id,
            expected_version=_parse_if_match(if_match),
            body=body,
            trace_id=request_id_ctx.get(),
        )
    )


@router.delete(
    "/cards/{card_id}/content-overrides/{resource_type}/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCardContentOverride",
)
async def delete_override(
    card_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> Response:
    _require(principal, write=True)
    await _store(request).delete_override(
        scope=_scope(principal),
        card_id=card_id,
        resource_type=_resource_type(resource_type),
        resource_id=resource_id,
        expected_version=_parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/cards/{card_id}/content-overrides/{resource_type}/{resource_id}/revisions",
    response_model=OverrideRevisionListEnvelope,
    operation_id="listCardContentOverrideRevisions",
)
async def list_revisions(
    card_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> OverrideRevisionListEnvelope:
    _require(principal, write=False)
    return OverrideRevisionListEnvelope(
        data=await _store(request).list_revisions(
            scope=_scope(principal),
            card_id=card_id,
            resource_type=_resource_type(resource_type),
            resource_id=resource_id,
        )
    )


@router.post(
    "/cards/{card_id}/content-overrides/{resource_type}/{resource_id}/rollback",
    response_model=OverrideEnvelope,
    operation_id="rollbackCardContentOverride",
)
async def rollback_override(
    card_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    body: RollbackOverrideRequest,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> OverrideEnvelope:
    _require(principal, write=True)
    return OverrideEnvelope(
        data=await _store(request).rollback_override(
            scope=_scope(principal),
            card_id=card_id,
            resource_type=_resource_type(resource_type),
            resource_id=resource_id,
            expected_version=_parse_if_match(if_match),
            revision_version=body.revision_version,
            trace_id=request_id_ctx.get(),
        )
    )

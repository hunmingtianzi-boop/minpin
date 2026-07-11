from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import get_staff_principal
from app.api.platform_schemas import (
    CreateEnterpriseRequest,
    EnterpriseEnvelope,
    EnterpriseListEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.platform_store import PlatformActor, PlatformStore

router = APIRouter(prefix="/platform/enterprises", tags=["Platform Administration"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _store(request: Request) -> PlatformStore:
    return PlatformStore(request.app.state.session_factory, request.app.state.settings)


def _actor(principal: StaffPrincipal) -> PlatformActor:
    return PlatformActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


@router.post(
    "",
    response_model=EnterpriseEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPlatformEnterprise",
)
async def create_enterprise(
    body: CreateEnterpriseRequest,
    request: Request,
    principal: StaffDependency,
) -> EnterpriseEnvelope:
    record = await _store(request).create_enterprise(
        actor=_actor(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return EnterpriseEnvelope(data=record)


@router.get(
    "",
    response_model=EnterpriseListEnvelope,
    operation_id="listPlatformEnterprises",
)
async def list_enterprises(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EnterpriseListEnvelope:
    records, total = await _store(request).list_enterprises(
        actor=_actor(principal),
        limit=limit,
        offset=offset,
    )
    return EnterpriseListEnvelope(data=records, total=total, limit=limit, offset=offset)


__all__ = ["router"]

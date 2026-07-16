from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.admin_schemas import (
    EnterpriseReadinessEnvelope,
    EnterpriseReadinessRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.core.tokens import StaffPrincipal
from app.db.models import (
    Card,
    ContentStatus,
    KnowledgeImportBatch,
    KnowledgeImportBatchStatus,
)
from app.db.session import set_rls_context
from app.services.platform_llm_profiles import is_chat_available

router = APIRouter(prefix="/admin", tags=["Admin Readiness"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


async def _readiness(
    request: Request,
    principal: StaffPrincipal,
) -> EnterpriseReadinessRecord:
    role = str(getattr(principal.role, "value", principal.role))
    if role != "company_admin":
        raise ApiError(403, "FORBIDDEN", "仅企业管理员可查看企业就绪状态")
    async with request.app.state.session_factory() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=principal.tenant_id,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            actor_session_id=principal.session_id,
        )
        card_count = int(
            await session.scalar(
                select(func.count(Card.id)).where(
                    Card.tenant_id == principal.tenant_id,
                    Card.company_id == principal.company_id,
                    Card.deleted_at.is_(None),
                    Card.status != ContentStatus.PUBLISHED,
                )
            )
            or 0
        )
        processing_count = int(
            await session.scalar(
                select(func.count(KnowledgeImportBatch.id)).where(
                    KnowledgeImportBatch.tenant_id == principal.tenant_id,
                    KnowledgeImportBatch.company_id == principal.company_id,
                    KnowledgeImportBatch.status.in_(
                        [
                            KnowledgeImportBatchStatus.PENDING,
                            KnowledgeImportBatchStatus.PROCESSING,
                        ]
                    ),
                )
            )
            or 0
        )
        failed_count = int(
            await session.scalar(
                select(func.count(KnowledgeImportBatch.id)).where(
                    KnowledgeImportBatch.tenant_id == principal.tenant_id,
                    KnowledgeImportBatch.company_id == principal.company_id,
                    KnowledgeImportBatch.status.in_(
                        [
                            KnowledgeImportBatchStatus.COMPLETED_WITH_ERRORS,
                            KnowledgeImportBatchStatus.FAILED,
                            KnowledgeImportBatchStatus.DEAD_LETTER,
                        ]
                    ),
                )
            )
            or 0
        )
    return EnterpriseReadinessRecord(
        generated_at=datetime.now(UTC),
        llm_ready=await is_chat_available(
            request.app.state.session_factory,
            request.app.state.settings,
        ),
        unpublished_card_count=card_count,
        processing_import_batch_count=processing_count,
        failed_import_batch_count=failed_count,
    )


@router.get(
    "/readiness",
    response_model=EnterpriseReadinessEnvelope,
    operation_id="getEnterpriseReadiness",
)
async def get_enterprise_readiness(
    request: Request,
    principal: StaffDependency,
) -> EnterpriseReadinessEnvelope:
    return EnterpriseReadinessEnvelope(data=await _readiness(request, principal))


__all__ = ["router"]

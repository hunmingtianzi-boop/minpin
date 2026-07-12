from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.scheduled_publish_schemas import ScheduledPublishJobRecord
from app.db.models import (
    CaseStudy,
    ContentStatus,
    KnowledgeDocument,
    KnowledgeVersion,
    Product,
    ReviewStatus,
    ScheduledPublishJob,
    ScheduledPublishResourceType,
    ScheduledPublishStatus,
)
from app.db.session import set_rls_context
from app.services.admin_store import AdminScope
from app.services.audit import append_audit
from app.services.catalog_store import require_version

_MIN_SCHEDULE_DELAY_SECONDS = 30


class ScheduledPublishStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def schedule(
        self,
        *,
        scope: AdminScope,
        resource_type: ScheduledPublishResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        scheduled_at: datetime,
        knowledge_version_id: uuid.UUID | None = None,
        trace_id: str | None = None,
    ) -> ScheduledPublishJobRecord:
        scheduled_at = scheduled_at.astimezone(UTC)
        if scheduled_at <= datetime.now(UTC) + _delay():
            raise ApiError(422, "SCHEDULE_TOO_SOON", "定时发布时间至少需要晚于当前时间 30 秒")
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                target_version, selected_version = await self._validate_resource(
                    session,
                    scope=scope,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    expected_version=expected_version,
                    knowledge_version_id=knowledge_version_id,
                )
                job = ScheduledPublishJob(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    target_version=target_version,
                    knowledge_version_id=selected_version,
                    scheduled_by=scope.actor_user_id,
                    scheduled_at=scheduled_at,
                    next_attempt_at=scheduled_at,
                    status=ScheduledPublishStatus.PENDING,
                    version=1,
                )
                session.add(job)
                await append_audit(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    actor_user_id=scope.actor_user_id,
                    action="scheduled_publish.create",
                    resource_type="scheduled_publish_job",
                    resource_id=job.id,
                    trace_id=trace_id,
                    event_data={
                        "target_type": resource_type.value,
                        "target_id": resource_id,
                        "target_version": target_version,
                        "scheduled_at": scheduled_at,
                    },
                )
                await session.flush()
                await session.refresh(job)
                return _record(job)
        except IntegrityError as exc:
            if "uq_scheduled_publish_jobs_active_resource" in str(exc.orig):
                raise ApiError(409, "SCHEDULE_EXISTS", "该资源已有生效中的定时发布任务") from exc
            raise

    async def list(
        self, *, scope: AdminScope, limit: int, offset: int
    ) -> tuple[list[ScheduledPublishJobRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = (
                ScheduledPublishJob.tenant_id == scope.tenant_id,
                ScheduledPublishJob.company_id == scope.company_id,
            )
            total = int(
                await session.scalar(
                    select(func.count()).select_from(ScheduledPublishJob).where(*filters)
                )
                or 0
            )
            jobs = (
                await session.scalars(
                    select(ScheduledPublishJob)
                    .where(*filters)
                    .order_by(ScheduledPublishJob.created_at.desc(), ScheduledPublishJob.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_record(job) for job in jobs], total

    async def get(self, *, scope: AdminScope, job_id: uuid.UUID) -> ScheduledPublishJobRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _record(await self._job(session, scope=scope, job_id=job_id))

    async def cancel(
        self,
        *,
        scope: AdminScope,
        job_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ScheduledPublishJobRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            job = await self._job(session, scope=scope, job_id=job_id, for_update=True)
            require_version(job.version, expected_version)
            if job.status not in {ScheduledPublishStatus.PENDING, ScheduledPublishStatus.FAILED}:
                raise ApiError(409, "SCHEDULE_NOT_CANCELLABLE", "当前定时发布任务无法取消")
            job.status = ScheduledPublishStatus.CANCELLED
            job.cancelled_at = datetime.now(UTC)
            job.version += 1
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="scheduled_publish.cancel",
                resource_type="scheduled_publish_job",
                resource_id=job.id,
                trace_id=trace_id,
                event_data={"target_type": job.resource_type.value, "target_id": job.resource_id},
            )
            await session.flush()
            await session.refresh(job)
            return _record(job)

    async def _validate_resource(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        resource_type: ScheduledPublishResourceType,
        resource_id: uuid.UUID,
        expected_version: int,
        knowledge_version_id: uuid.UUID | None,
    ) -> tuple[int, uuid.UUID | None]:
        model: Any = {
            ScheduledPublishResourceType.PRODUCT: Product,
            ScheduledPublishResourceType.CASE_STUDY: CaseStudy,
            ScheduledPublishResourceType.KNOWLEDGE_DOCUMENT: KnowledgeDocument,
        }[resource_type]
        resource = await session.scalar(
            select(model)
            .where(
                model.id == resource_id,
                model.tenant_id == scope.tenant_id,
                model.company_id == scope.company_id,
            )
            .with_for_update()
        )
        if resource is None or getattr(resource, "deleted_at", None) is not None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "待发布资源不存在")
        require_version(resource.version, expected_version)
        if resource.status == ContentStatus.PUBLISHED:
            raise ApiError(409, "ALREADY_PUBLISHED", "资源已经发布")
        if resource.status == ContentStatus.ARCHIVED:
            raise ApiError(409, "RESOURCE_ARCHIVED", "已归档资源不能定时发布")
        if resource_type != ScheduledPublishResourceType.KNOWLEDGE_DOCUMENT:
            if knowledge_version_id is not None:
                raise ApiError(422, "VERSION_ID_NOT_ALLOWED", "目录内容不能指定知识版本")
            return resource.version, None
        version_query = select(KnowledgeVersion).where(
            KnowledgeVersion.tenant_id == scope.tenant_id,
            KnowledgeVersion.company_id == scope.company_id,
            KnowledgeVersion.document_id == resource.id,
            KnowledgeVersion.review_status == ReviewStatus.DRAFT,
        )
        if knowledge_version_id is not None:
            version_query = version_query.where(KnowledgeVersion.id == knowledge_version_id)
        else:
            version_query = version_query.order_by(KnowledgeVersion.version_number.desc()).limit(1)
        version = await session.scalar(version_query.with_for_update())
        if version is None:
            raise ApiError(409, "DRAFT_NOT_FOUND", "没有可发布的知识草稿版本")
        return resource.version, version.id

    async def _job(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        job_id: uuid.UUID,
        for_update: bool = False,
    ) -> ScheduledPublishJob:
        query = select(ScheduledPublishJob).where(
            ScheduledPublishJob.id == job_id,
            ScheduledPublishJob.tenant_id == scope.tenant_id,
            ScheduledPublishJob.company_id == scope.company_id,
        )
        job = await session.scalar(query.with_for_update() if for_update else query)
        if job is None:
            raise ApiError(404, "SCHEDULE_NOT_FOUND", "定时发布任务不存在")
        return job

    async def _set_scope(self, session: AsyncSession, scope: AdminScope) -> None:
        await set_rls_context(session, tenant_id=scope.tenant_id, company_id=scope.company_id)


def _delay():
    from datetime import timedelta

    return timedelta(seconds=_MIN_SCHEDULE_DELAY_SECONDS)


def _record(job: ScheduledPublishJob) -> ScheduledPublishJobRecord:
    return ScheduledPublishJobRecord(
        id=job.id,
        resource_type=job.resource_type.value,
        resource_id=job.resource_id,
        target_version=job.target_version,
        knowledge_version_id=job.knowledge_version_id,
        scheduled_by=job.scheduled_by,
        scheduled_at=job.scheduled_at,
        status=job.status.value,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        next_attempt_at=job.next_attempt_at,
        completed_at=job.completed_at,
        cancelled_at=job.cancelled_at,
        error_code=job.error_code,
        version=job.version,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


__all__ = ["ScheduledPublishStore"]

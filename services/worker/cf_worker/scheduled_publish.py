from __future__ import annotations

import httpx
from app.core.config import Settings as ApiSettings
from app.services.admin_store import AdminScope, AdminStore

from cf_worker.config import WorkerSettings
from cf_worker.repository import ClaimedScheduledPublish, PostgresOutboxRepository


class ScheduledPublishExecutor:
    def __init__(self, repository: PostgresOutboxRepository, settings: WorkerSettings) -> None:
        self._repository = repository
        self._settings = settings

    async def execute(self, claim: ClaimedScheduledPublish) -> None:
        if claim.resource_type in {"product", "case_study"}:
            await self._repository.publish_scheduled_catalog(claim)
            return
        if claim.resource_type != "knowledge_document" or claim.knowledge_version_id is None:
            raise RuntimeError("invalid_scheduled_publish_claim")
        await self._repository.validate_scheduled_knowledge(claim)
        api_settings = ApiSettings(
            database_url=self._settings.database_url,
            embedding_provider=self._settings.embedding_provider,
            embedding_base_url=self._settings.embedding_base_url,
            embedding_api_key=self._settings.embedding_api_key,
            embedding_model=self._settings.embedding_model,
            embedding_dimension=self._settings.embedding_dimension,
            embedding_timeout_seconds=self._settings.embedding_timeout_seconds,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.embedding_timeout_seconds, connect=5.0),
            follow_redirects=False,
        ) as client:
            store = AdminStore.from_runtime(
                session_factory=self._repository.session_factory,
                settings=api_settings,
                http_client=client,
            )
            await store.publish_document(
                scope=AdminScope(
                    tenant_id=claim.tenant_id,
                    company_id=claim.company_id,
                    actor_user_id=claim.scheduled_by,
                ),
                document_id=claim.resource_id,
                version_id=claim.knowledge_version_id,
                trace_id=f"scheduled-publish:{claim.id}",
            )


__all__ = ["ScheduledPublishExecutor"]

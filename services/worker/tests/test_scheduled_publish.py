from __future__ import annotations

import uuid
from typing import Any

import pytest

from cf_worker.repository import ClaimedScheduledPublish
from cf_worker.scheduled_publish import ScheduledPublishExecutor


def _claim(resource_type: str = "product") -> ClaimedScheduledPublish:
    return ClaimedScheduledPublish(
        {
            "job_id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "company_id": uuid.uuid4(),
            "lock_token": uuid.uuid4(),
            "resource_type": resource_type,
            "resource_id": uuid.uuid4(),
            "target_version": 3,
            "knowledge_version_id": uuid.uuid4() if resource_type == "knowledge_document" else None,
            "scheduled_by": uuid.uuid4(),
            "attempts": 1,
        }
    )


class _Repository:
    def __init__(self) -> None:
        self.catalog: list[Any] = []

    async def publish_scheduled_catalog(self, claim: Any) -> None:
        self.catalog.append(claim)


@pytest.mark.asyncio
async def test_executor_delegates_catalog_publication_to_scoped_repository() -> None:
    repository = _Repository()
    executor = ScheduledPublishExecutor(repository, object())  # type: ignore[arg-type]
    claim = _claim()
    await executor.execute(claim)
    assert repository.catalog == [claim]


@pytest.mark.asyncio
async def test_executor_rejects_unknown_resource_type() -> None:
    executor = ScheduledPublishExecutor(_Repository(), object())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="invalid_scheduled_publish_claim"):
        await executor.execute(_claim("unknown"))

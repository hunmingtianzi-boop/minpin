from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import admin
from app.api.scheduled_publish_schemas import ScheduledPublishJobRecord
from app.core.tokens import StaffPrincipal


class _ScheduledStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        now = datetime.now(UTC)
        self.job = ScheduledPublishJobRecord(
            id=uuid.uuid4(),
            resource_type="product",
            resource_id=uuid.uuid4(),
            target_version=4,
            scheduled_by=uuid.uuid4(),
            scheduled_at=now + timedelta(hours=1),
            status="pending",
            attempts=0,
            max_attempts=6,
            next_attempt_at=now + timedelta(hours=1),
            version=1,
            created_at=now,
            updated_at=now,
        )

    async def list(self, **kwargs: Any):
        self.calls.append(("list", kwargs))
        return [self.job], 1

    async def get(self, **kwargs: Any):
        self.calls.append(("get", kwargs))
        return self.job

    async def cancel(self, **kwargs: Any):
        self.calls.append(("cancel", kwargs))
        self.job = self.job.model_copy(update={"status": "cancelled", "version": 2})
        return self.job


def _principal(*permissions: str) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role="card_owner",
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


def test_list_get_and_cancel_scheduled_publish_use_permissions_and_versions() -> None:
    store = _ScheduledStore()
    principal = _principal("catalog.read", "catalog.publish")
    app = FastAPI()
    app.state.scheduled_publish_store = store
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(admin.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal
    with TestClient(app) as client:
        listed = client.get("/api/v1/admin/scheduled-publishes")
        fetched = client.get(f"/api/v1/admin/scheduled-publishes/{store.job.id}")
        cancelled = client.post(
            f"/api/v1/admin/scheduled-publishes/{store.job.id}:cancel",
            headers={"If-Match": '"1"'},
        )
    assert listed.status_code == 200
    assert fetched.status_code == 200 and fetched.headers["etag"] == '"1"'
    assert cancelled.status_code == 200 and cancelled.json()["data"]["status"] == "cancelled"
    assert store.calls[-1][1]["expected_version"] == 1


def test_scheduled_publish_list_rejects_unprivileged_member() -> None:
    app = FastAPI()
    app.state.scheduled_publish_store = _ScheduledStore()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(admin.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: _principal()
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/scheduled-publishes")
    assert response.status_code == 403

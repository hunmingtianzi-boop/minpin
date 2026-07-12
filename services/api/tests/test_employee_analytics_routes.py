from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import workflow as workflow_routes
from app.api.workflow_schemas import (
    EmployeeAnalyticsItem,
    EmployeeAnalyticsReconciliation,
)
from app.core.tokens import StaffPrincipal


class _WorkflowStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.generated_at = datetime.now(UTC)

    async def list_employee_analytics(self, **kwargs: Any):
        self.calls.append(kwargs)
        scope = kwargs["scope"]
        item = EmployeeAnalyticsItem(
            user_id=scope.actor_user_id,
            membership_id=uuid.uuid4(),
            display_name="测试员工",
            role=scope.role,
            membership_status="active",
            card_count=2,
            visits=10,
            unique_visitors=8,
            conversations=4,
            leads=3,
            conversation_rate=0.4,
            lead_rate=0.75,
            last_activity_at=self.generated_at,
        )
        reconciliation = EmployeeAnalyticsReconciliation(
            card_count=2,
            visits=10,
            unique_visitors=8,
            employee_unique_visitors_sum=8,
            conversations=4,
            total_leads=3,
            conversation_rate=0.4,
            lead_rate=0.75,
            last_activity_at=self.generated_at,
        )
        return [item], reconciliation, 1, self.generated_at


@pytest.fixture
def analytics_client(monkeypatch: pytest.MonkeyPatch):
    store = _WorkflowStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(workflow_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(workflow_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal_box


def test_employee_analytics_forwards_scope_pagination_and_sort(analytics_client) -> None:
    client, store, principal_box = analytics_client
    response = client.get(
        "/api/v1/admin/analytics/employees",
        params={
            "period_days": 90,
            "limit": 20,
            "offset": 5,
            "sort_by": "lead_rate",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    call = store.calls[-1]
    assert call["scope"].tenant_id == principal_box["value"].tenant_id
    assert call["scope"].company_id == principal_box["value"].company_id
    assert call["period_days"] == 90
    assert call["limit"] == 20
    assert call["offset"] == 5
    assert call["sort_by"] == "lead_rate"
    assert call["sort_order"] == "asc"
    payload = response.json()
    assert payload["data"][0]["leads"] == 3
    assert payload["reconciliation"]["total_leads"] == 3
    assert payload["period_days"] == 90


def test_employee_analytics_permissions_and_validation(analytics_client) -> None:
    client, store, principal_box = analytics_client
    principal_box["value"] = _principal(role="card_owner")
    assert client.get("/api/v1/admin/analytics/employees").status_code == 200
    assert store.calls[-1]["scope"].is_card_owner

    principal_box["value"] = _principal(role="staff", permissions=("analytics.read",))
    assert client.get("/api/v1/admin/analytics/employees").status_code == 200

    principal_box["value"] = _principal(role="staff", permissions=("visits.read",))
    assert client.get("/api/v1/admin/analytics/employees").status_code == 403

    principal_box["value"] = _principal(role="company_admin")
    assert client.get("/api/v1/admin/analytics/employees?period_days=91").status_code == 422
    assert client.get("/api/v1/admin/analytics/employees?sort_by=unknown").status_code == 422


def test_employee_analytics_openapi_contract(analytics_client) -> None:
    client, _store, _principal_box = analytics_client
    operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/admin/analytics/employees"
    ]["get"]
    assert operation["operationId"] == "listEmployeeAnalytics"
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("EmployeeAnalyticsListEnvelope")


def _principal(*, role: str, permissions: tuple[str, ...] = ()) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )

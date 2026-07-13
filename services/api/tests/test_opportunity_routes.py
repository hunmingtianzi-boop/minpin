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
from app.api.workflow_schemas import OpportunityCandidateView
from app.core.tokens import StaffPrincipal


class _WorkflowStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.item = OpportunityCandidateView(
            conversation_id=uuid.uuid4(),
            card_id=uuid.uuid4(),
            card_display_name="测试名片",
            visitor_id=uuid.uuid4(),
            question="可以给我一份报价方案吗？",
            reason="商业决策信号（报价、预算或采购）",
            score=0.9,
            has_consented_lead=False,
            last_activity_at=datetime.now(UTC),
        )

    async def list_opportunities(self, **kwargs: Any) -> tuple[list[OpportunityCandidateView], int]:
        self.calls.append(kwargs)
        return [self.item], 1


@pytest.fixture
def opportunity_client(monkeypatch: pytest.MonkeyPatch):
    store = _WorkflowStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(workflow_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(workflow_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal_box


def test_opportunity_route_forwards_scope_and_is_explicitly_anonymous(opportunity_client) -> None:
    client, store, principal_box = opportunity_client
    response = client.get("/api/v1/admin/opportunities?limit=20&offset=5")

    assert response.status_code == 200
    call = store.calls[-1]
    assert call["scope"].tenant_id == principal_box["value"].tenant_id
    assert call["scope"].company_id == principal_box["value"].company_id
    assert call["limit"] == 20
    assert call["offset"] == 5
    payload = response.json()
    assert payload["data"][0]["has_consented_lead"] is False
    assert payload["data"][0]["question"] == "可以给我一份报价方案吗？"


def test_opportunity_route_requires_conversation_access(opportunity_client) -> None:
    client, _store, principal_box = opportunity_client
    principal_box["value"] = _principal(role="staff", permissions=("conversations.read",))
    assert client.get("/api/v1/admin/opportunities").status_code == 200

    principal_box["value"] = _principal(role="staff", permissions=("leads.read",))
    assert client.get("/api/v1/admin/opportunities").status_code == 403


def test_opportunity_route_has_stable_openapi_contract(opportunity_client) -> None:
    client, _store, _principal_box = opportunity_client
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/admin/opportunities"]["get"]
    assert operation["operationId"] == "listAdminOpportunities"
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("OpportunityCandidateListEnvelope")


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

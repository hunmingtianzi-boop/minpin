from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import visitor_profiles as profile_routes
from app.api.workflow_schemas import (
    VisitorProfileDetail,
    VisitorProfileListItem,
    VisitorProfileSignalPreview,
)
from app.core.tokens import StaffPrincipal


class _ProfileStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        now = datetime.now(UTC)
        self.visitor_id = uuid.uuid4()
        self.item = VisitorProfileListItem(
            visitor_id=self.visitor_id,
            first_seen_at=now,
            last_seen_at=now,
            signal_count=1,
            top_interests=[
                VisitorProfileSignalPreview(
                    label="工业节能",
                    strength=0.8,
                    confidence=0.8,
                    last_seen_at=now,
                )
            ],
        )

    async def list(self, **kwargs: Any) -> tuple[list[VisitorProfileListItem], int]:
        self.calls.append(("list", kwargs))
        return [self.item], 1

    async def get(self, **kwargs: Any) -> VisitorProfileDetail:
        self.calls.append(("get", kwargs))
        return VisitorProfileDetail(
            visitor_id=self.visitor_id,
            first_seen_at=self.item.first_seen_at,
            last_seen_at=self.item.last_seen_at,
            signals=[],
        )


@pytest.fixture
def profile_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, _ProfileStore, dict[str, StaffPrincipal]]:
    store = _ProfileStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(profile_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(profile_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal_box


def test_profile_routes_forward_server_derived_scope(
    profile_client: tuple[TestClient, _ProfileStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = profile_client
    response = client.get("/api/v1/admin/visitor-profiles?limit=20&offset=0")
    assert response.status_code == 200
    scope = store.calls[-1][1]["scope"]
    assert scope.tenant_id == principal_box["value"].tenant_id
    assert scope.company_id == principal_box["value"].company_id
    assert response.json()["meta"]["total"] == 1

    detail = client.get(
        f"/api/v1/admin/visitor-profiles/{store.visitor_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["visitor_id"] == str(store.visitor_id)


def test_profile_routes_allow_conversation_read_but_deny_unrelated_staff(
    profile_client: tuple[TestClient, _ProfileStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = profile_client
    principal_box["value"] = _principal(
        role="staff", permissions=("conversations.read",)
    )
    assert client.get("/api/v1/admin/visitor-profiles").status_code == 200
    principal_box["value"] = _principal(role="staff", permissions=("leads.read",))
    assert client.get("/api/v1/admin/visitor-profiles").status_code == 403
    assert [name for name, _kwargs in store.calls] == ["list"]


def _principal(
    *, role: str, permissions: tuple[str, ...] = ()
) -> StaffPrincipal:
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

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_schemas import EnterpriseReadinessRecord
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import enterprise_readiness as routes
from app.core.tokens import StaffPrincipal


def _principal(role: str = "company_admin") -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=(),
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, dict[str, StaffPrincipal]]:
    principal = {"value": _principal()}

    async def fake_readiness(_request: object, actor: StaffPrincipal):
        if str(actor.role) != "company_admin":
            raise ApiError(403, "FORBIDDEN", "仅企业管理员可查看企业就绪状态")
        return EnterpriseReadinessRecord(
            generated_at=datetime.now(UTC),
            llm_ready=True,
            unpublished_card_count=2,
            processing_import_batch_count=1,
            failed_import_batch_count=0,
        )

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal["value"]
    monkeypatch.setattr(routes, "_readiness", fake_readiness)
    with TestClient(app) as test_client:
        yield test_client, principal


def test_readiness_response_is_allowlisted_and_secret_free(
    client: tuple[TestClient, dict[str, StaffPrincipal]],
) -> None:
    test_client, _ = client
    response = test_client.get("/api/v1/admin/readiness")
    assert response.status_code == 200
    assert set(response.json()["data"]) == {
        "generated_at",
        "llm_ready",
        "unpublished_card_count",
        "processing_import_batch_count",
        "failed_import_batch_count",
    }
    assert "api_key" not in response.text


def test_non_company_admin_is_forbidden(
    client: tuple[TestClient, dict[str, StaffPrincipal]],
) -> None:
    test_client, principal = client
    principal["value"] = _principal("platform_admin")
    response = test_client.get("/api/v1/admin/readiness")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

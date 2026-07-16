from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import platform_llm as routes
from app.core.tokens import StaffPrincipal
from app.services.platform_llm_profiles import (
    PlatformLLMProbeResult,
    PlatformLLMProfileView,
)


def _principal(role: str = "platform_admin") -> StaffPrincipal:
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


def _view() -> PlatformLLMProfileView:
    now = datetime.now(UTC)
    return PlatformLLMProfileView(
        id=uuid.uuid4(),
        name="主配置",
        purpose="chat_main",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        model="model-main",
        thinking="disabled",
        reasoning_effort=None,
        timeout_seconds=30,
        max_retries=2,
        max_concurrency=20,
        max_output_tokens=1000,
        temperature=0.1,
        daily_budget_cny=100,
        input_price_cny_per_million=1.5,
        output_price_cny_per_million=6,
        enabled=True,
        is_active=True,
        version=3,
        key_configured=True,
        key_hint="••••oken",
        last_test_status="untested",
        last_test_latency_ms=None,
        last_tested_at=None,
        created_at=now,
        updated_at=now,
    )


class RouteService:
    def __init__(self) -> None:
        self.record = _view()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_profiles(self, **kwargs: Any) -> list[PlatformLLMProfileView]:
        self.calls.append(("list", kwargs))
        return [self.record]

    async def get_profile(self, **kwargs: Any) -> PlatformLLMProfileView:
        self.calls.append(("get", kwargs))
        return self.record

    async def create_profile(self, **kwargs: Any) -> PlatformLLMProfileView:
        self.calls.append(("create", kwargs))
        return self.record

    async def update_profile(self, **kwargs: Any) -> PlatformLLMProfileView:
        self.calls.append(("update", kwargs))
        return self.record

    async def activate_profile(self, **kwargs: Any) -> PlatformLLMProfileView:
        self.calls.append(("activate", kwargs))
        return self.record

    async def test_profile_connection(self, **kwargs: Any) -> PlatformLLMProbeResult:
        self.calls.append(("test", kwargs))
        return PlatformLLMProbeResult(
            ok=True,
            profile_id=self.record.id,
            tested_version=self.record.version,
            provider=self.record.provider,
            model=self.record.model,
            latency_ms=12,
        )


@pytest.fixture
def route_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RouteService, dict[str, StaffPrincipal]]:
    service = RouteService()
    principal_box = {"value": _principal()}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(routes, "_service", lambda _request: service)
    with TestClient(app) as client:
        yield client, service, principal_box


def test_route_surface_and_response_are_strictly_allowlisted(
    route_client: tuple[TestClient, RouteService, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client
    paths = client.app.openapi()["paths"]
    root = "/api/v1/platform/settings/llm/profiles"
    assert set(paths[root]) == {"get", "post"}
    assert set(paths[f"{root}/{{profile_id}}"] ) == {"put"}
    assert set(paths[f"{root}/{{profile_id}}/test"]) == {"post"}
    assert set(paths[f"{root}/{{profile_id}}/activate"]) == {"post"}

    payload = client.get(root).json()["data"][0]
    assert set(payload) == {
        "id",
        "name",
        "purpose",
        "provider",
        "base_url",
        "model",
        "thinking",
        "reasoning_effort",
        "timeout_seconds",
        "max_retries",
        "max_concurrency",
        "max_output_tokens",
        "temperature",
        "daily_budget_cny",
        "input_price_cny_per_million",
        "output_price_cny_per_million",
        "key_configured",
        "key_hint",
        "enabled",
        "is_active",
        "version",
        "last_test_status",
        "last_test_latency_ms",
        "last_tested_at",
        "created_at",
        "updated_at",
    }
    assert "api_key" not in payload
    assert "api_key_ciphertext" not in payload


def test_update_merges_omitted_fields_before_calling_service(
    route_client: tuple[TestClient, RouteService, dict[str, StaffPrincipal]],
) -> None:
    client, service, _ = route_client
    response = client.put(
        f"/api/v1/platform/settings/llm/profiles/{service.record.id}",
        json={"expected_version": 3, "name": "新名称", "max_concurrency": 40},
    )
    assert response.status_code == 200
    body = next(payload["body"] for name, payload in service.calls if name == "update")
    assert body.name == "新名称"
    assert body.provider == service.record.provider
    assert body.reasoning_effort is None
    assert body.max_concurrency == 40
    assert body.max_output_tokens == service.record.max_output_tokens
    assert body.api_key is None


def test_temporary_test_key_is_forwarded_once_but_never_returned(
    route_client: tuple[TestClient, RouteService, dict[str, StaffPrincipal]],
) -> None:
    client, service, _ = route_client
    temporary = "temporary-test-placeholder-token"
    response = client.post(
        f"/api/v1/platform/settings/llm/profiles/{service.record.id}/test",
        json={"api_key": temporary},
    )
    assert response.status_code == 200
    test_call = next(payload for name, payload in service.calls if name == "test")
    assert test_call["api_key_override"].get_secret_value() == temporary
    assert temporary not in response.text
    assert set(response.json()["data"]) == {
        "status",
        "provider",
        "model",
        "latency_ms",
        "error_code",
    }


@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", "")])
def test_enterprise_actor_is_rejected_before_service_access(
    method: str,
    suffix: str,
    route_client: tuple[TestClient, RouteService, dict[str, StaffPrincipal]],
) -> None:
    client, service, principal_box = route_client
    principal_box["value"] = _principal("company_admin")
    create_body = {
        "name": "unauthorized",
        "provider": "openai_compatible",
        "base_url": "https://provider.example.test/v1",
        "api_key": "unauthorized-placeholder-token",
        "model": "model-main",
    }
    response = client.request(
        method,
        f"/api/v1/platform/settings/llm/profiles{suffix}",
        json=create_body if method == "post" else None,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert service.calls == []

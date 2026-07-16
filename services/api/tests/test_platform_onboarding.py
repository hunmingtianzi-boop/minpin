from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.knowledge_import_schemas import KnowledgeImportBatchRecord
from app.api.platform_schemas import PlatformOnboardingSessionRecord
from app.api.routes import platform_onboarding as routes
from app.core.tokens import StaffPrincipal
from app.services.knowledge_import_store import KnowledgeImportScope
from app.services.platform_onboarding import (
    _BUSINESS_PROFILE_FIELDS,
    _SUGGESTION_SYSTEM_PROMPT,
    PlatformOnboardingImportScope,
    _parse_suggestions,
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


class RouteService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.record = PlatformOnboardingSessionRecord(
            id=uuid.uuid4(),
            status="draft",
            tenant_slug="acme-demo",
            tenant_name="Acme",
            version=1,
            expires_at=now + timedelta(hours=24),
            created_at=now,
            updated_at=now,
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("start", kwargs))
        return self.record

    async def list_sessions(
        self, **kwargs: Any
    ) -> tuple[list[PlatformOnboardingSessionRecord], int]:
        self.calls.append(("list", kwargs))
        return [self.record], 1

    async def get_session(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("get", kwargs))
        return self.record

    async def import_scope(self, **kwargs: Any) -> PlatformOnboardingImportScope:
        self.calls.append(("scope", kwargs))
        return PlatformOnboardingImportScope(
            session_id=self.record.id,
            version=self.record.version,
            scope=KnowledgeImportScope(
                tenant_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
            ),
        )

    async def attach_import_batch(
        self, **kwargs: Any
    ) -> PlatformOnboardingSessionRecord:
        self.calls.append(("attach", kwargs))
        return self.record.model_copy(
            update={"status": "processing", "version": 2}
        )

    async def generate_suggestions(
        self, **kwargs: Any
    ) -> PlatformOnboardingSessionRecord:
        self.calls.append(("suggestions", kwargs))
        return self.record.model_copy(update={"status": "manual_required", "version": 2})

    async def confirm(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("confirm", kwargs))
        return self.record.model_copy(update={"status": "confirmed", "version": 2})

    async def cancel(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("cancel", kwargs))
        return self.record.model_copy(update={"status": "cancelled", "version": 2})


class ImportStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.batch_id = uuid.uuid4()

    async def create_batch(self, **kwargs: Any) -> KnowledgeImportBatchRecord:
        self.calls.append(kwargs)
        return KnowledgeImportBatchRecord(
            id=self.batch_id,
            status="pending",
            total_items=1,
            pending_items=1,
            succeeded_items=0,
            failed_items=0,
            created_at=datetime.now(UTC),
        )


@pytest.fixture
def route_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]]:
    service = RouteService()
    import_store = ImportStore()
    principal_box = {"value": _principal()}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(routes, "_service", lambda _request: service)
    monkeypatch.setattr(routes, "_import_store", lambda _request: import_store)
    with TestClient(app) as client:
        yield client, service, import_store, principal_box


def test_route_surface_is_session_bound(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _, _ = route_client
    paths = client.app.openapi()["paths"]
    root = "/api/v1/platform/onboarding"
    assert set(paths[root]) == {"get", "post"}
    assert set(paths[f"{root}/{{onboarding_id}}"] ) == {"get"}
    for suffix in ("imports", "suggestions", "confirm", "cancel"):
        assert set(paths[f"{root}/{{onboarding_id}}/{suffix}"]) == {"post"}
    upload = paths[f"{root}/{{onboarding_id}}/imports"]["post"]
    serialized = str(upload)
    assert "tenant_id" not in serialized
    assert "company_id" not in serialized


def test_upload_reuses_current_import_store_and_forces_draft(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, import_store, _ = route_client
    response = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/imports",
        files={"files": ("company.txt", "企业资料", "text/plain")},
    )
    assert response.status_code == 202
    assert import_store.calls[0]["auto_publish"] is False
    assert len(import_store.calls[0]["items"]) == 1
    assert import_store.calls[0]["scope"].tenant_id is not None
    attach = next(payload for name, payload in service.calls if name == "attach")
    assert attach["expected_version"] == service.record.version
    assert attach["batch_id"] == import_store.batch_id


def test_enterprise_actor_is_rejected_before_any_service_access(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, import_store, principal_box = route_client
    principal_box["value"] = _principal("company_admin")
    response = client.get("/api/v1/platform/onboarding")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert service.calls == []
    assert import_store.calls == []


def test_suggestion_parser_drops_unknown_unbound_and_duplicate_fields() -> None:
    source_id = uuid.uuid4()
    rows = {
        source_id: {
            "file_name": "company.txt",
            "document_id": uuid.uuid4(),
            "raw_text": "Acme 是制造企业。",
        }
    }
    suggestions = _parse_suggestions(
        {
            "suggestions": [
                {
                    "field": "company_name",
                    "value": "Acme",
                    "confidence": 1.4,
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "company_name",
                    "value": "重复项",
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "api_key",
                    "value": "should-never-pass",
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "summary",
                    "value": "无来源",
                    "source_ids": [str(uuid.uuid4())],
                },
            ]
        },
        source_rows=rows,
    )
    assert [item.field for item in suggestions] == ["company_name"]
    assert suggestions[0].confidence == 1
    assert suggestions[0].sources[0].import_item_id == source_id
    assert "api_key" not in str(suggestions)


def test_business_profile_parser_keeps_only_sourced_allowed_insights() -> None:
    source_id = uuid.uuid4()
    rows = {
        source_id: {
            "file_name": "业务介绍.pdf",
            "document_id": uuid.uuid4(),
            "raw_text": "为制造企业提供设备预测性维护服务。",
        }
    }
    profile = _parse_suggestions(
        {
            "business_profile": [
                {
                    "field": "business_positioning",
                    "value": "面向制造企业的设备预测性维护服务商",
                    "confidence": 0.92,
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "annual_revenue",
                    "value": "1 亿元",
                    "source_ids": [str(source_id)],
                },
            ]
        },
        source_rows=rows,
        key="business_profile",
        allowed_fields={"business_positioning": 800},
    )
    assert [item.field for item in profile] == ["business_positioning"]
    assert profile[0].sources[0].file_name == "业务介绍.pdf"
    assert "annual_revenue" not in str(profile)


def test_business_analysis_contract_covers_directions_conflicts_and_evidence_gaps() -> None:
    assert {
        "core_capabilities",
        "business_model",
        "business_directions",
        "evidence_conflicts",
        "missing_information",
    }.issubset(_BUSINESS_PROFILE_FIELDS)
    assert "当前已有业务" in _SUGGESTION_SYSTEM_PROMPT
    assert "规划方向" in _SUGGESTION_SYSTEM_PROMPT
    assert "多份资料相互冲突" in _SUGGESTION_SYSTEM_PROMPT
    assert "禁止输出空话" in _SUGGESTION_SYSTEM_PROMPT


def test_migration_stores_no_plain_password_and_has_narrow_draft_functions() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20260715_0018_platform_onboarding_sessions.py"
    ).read_text(encoding="utf-8")
    assert "admin_password" not in migration
    assert "api_key" not in migration
    assert "platform_onboarding_drafts" in migration
    assert "platform_onboarding_imports_settled" in migration
    assert "SECURITY DEFINER" in migration
    assert "SET search_path = ''" in migration
    assert "REVOKE ALL ON FUNCTION" in migration
    assert "item.batch_id = ANY(onboarding.import_batch_ids)" in migration

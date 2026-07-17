from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routes import public_conversations
from app.api.schemas import (
    AiAssistantPublicConfig,
    PolicyVersions,
    PublicCard,
    PublicCompany,
)
from app.core.config import Settings
from app.services import ai_runtime
from app.services.platform_llm_profiles import EffectiveChatConfig


async def test_request_runtime_uses_fresh_effective_profile(monkeypatch) -> None:
    settings = Settings(app_env="test", llm_api_key="environment-key")
    sessions = async_sessionmaker(class_=AsyncSession)
    profile_id = uuid.uuid4()
    resolved = EffectiveChatConfig(
        profile_id=profile_id,
        profile_name="active",
        provider="database-provider",
        base_url="https://provider.example/v1",
        api_key=SecretStr("database-key"),
        model="database-model",
        thinking="disabled",
        reasoning_effort="high",
        timeout_seconds=17,
        max_retries=0,
        max_concurrency=3,
        max_output_tokens=900,
        temperature=0.2,
        daily_budget_cny=80,
        input_price_cny_per_million=1.5,
        output_price_cny_per_million=3.0,
        allow_general_answers=True,
        faq_fast_path_enabled=True,
        enabled=True,
        source="database",
        version=7,
        updated_at=datetime.now(UTC),
    )
    resolver = AsyncMock(return_value=resolved)
    monkeypatch.setattr(ai_runtime, "resolve_effective_chat_config", resolver)

    async with httpx.AsyncClient() as client:
        runtime = await ai_runtime.resolve_rag_runtime(
            settings=settings,
            http_client=client,
            session_factory=sessions,
        )

    resolver.assert_awaited_once_with(sessions, settings)
    assert runtime.config.profile_id == profile_id
    assert runtime.orchestrator._chat_provider.provider_name == "database-provider"
    assert runtime.orchestrator._chat_provider.model_name == "database-model"
    assert runtime.settings.llm_api_key == SecretStr("database-key")
    assert runtime.settings.llm_allow_general_answers is True
    assert runtime.settings.rag_faq_fast_path_enabled is True
    assert "database-key" not in repr(runtime)


async def test_public_card_availability_uses_same_dynamic_resolver(monkeypatch) -> None:
    card = PublicCard(
        id=uuid.uuid4(),
        slug="sample-card",
        card_kind="enterprise",
        display_name="示例名片",
        title="负责人",
        company=PublicCompany(id=uuid.uuid4(), name="示例企业", summary=""),
        ai_assistant=AiAssistantPublicConfig(
            available=True,
            display_name="企业助手",
            disclosure="AI 生成",
            welcome_message="你好",
        ),
        policy_versions=PolicyVersions(
            privacy="v1",
            chat_notice="v1",
            lead_consent="v1",
            profile_personalization="v1",
        ),
    )
    store = SimpleNamespace(get_public_card=AsyncMock(return_value=card))
    availability = AsyncMock(return_value=False)
    monkeypatch.setattr(public_conversations, "_store", lambda _request: store)
    monkeypatch.setattr(public_conversations, "is_chat_available", availability)
    state = SimpleNamespace(session_factory=object(), settings=Settings(app_env="test"))
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    response = await public_conversations.get_public_card("sample-card", request)

    assert response.data.ai_assistant.available is False
    availability.assert_awaited_once_with(state.session_factory, state.settings)

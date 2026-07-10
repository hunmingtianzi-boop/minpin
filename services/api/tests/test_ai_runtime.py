from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.ai_runtime import build_rag_orchestrator


async def test_build_runtime_uses_explicit_deepseek_v4_without_credentials() -> None:
    settings = Settings(
        app_env="test",
        llm_api_key="not-injected-into-runtime",
        llm_model="deepseek-v4-flash",
        llm_thinking="disabled",
    )
    sessions = async_sessionmaker(class_=AsyncSession)

    async with httpx.AsyncClient() as client:
        orchestrator = build_rag_orchestrator(
            settings=settings,
            http_client=client,
            session_factory=sessions,
        )

    assert orchestrator._chat_provider.model_name == "deepseek-v4-flash"
    assert "not-injected-into-runtime" not in repr(orchestrator)

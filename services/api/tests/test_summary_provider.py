from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.api.errors import ApiError
from app.core.config import Settings
from app.services.summary_provider import DeepSeekSummaryProvider, SummaryMessage


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        llm_api_key=SecretStr("unit-test-provider-key"),
        llm_max_retries=1,
        **overrides,
    )


@pytest.mark.asyncio
async def test_summary_provider_redacts_input_output_and_records_metadata() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "provider-request-1"},
            json={
                "id": "completion-1",
                "model": "deepseek-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "客户电话 13800138000，想了解方案",
                                    "interests": ["AI 接待"],
                                    "strength": "high",
                                    "primary_intent": "product_evaluation",
                                    "next_step": "发邮件到 visitor@example.com",
                                    "risk_notes": None,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 40},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekSummaryProvider(_settings(), client).generate(
            [
                SummaryMessage(
                    id="message-1",
                    role="user",
                    content="手机号 13800138000，邮箱 visitor@example.com",
                )
            ],
            trace_id="trace-summary-1",
        )

    request_payload = json.loads(calls[0].content)
    serialized = json.dumps(request_payload, ensure_ascii=False)
    assert "13800138000" not in serialized
    assert "visitor@example.com" not in serialized
    assert request_payload["thinking"] == {"type": "disabled"}
    assert calls[0].headers["x-request-id"] == "trace-summary-1"
    assert "13800138000" not in result.draft.summary
    assert "visitor@example.com" not in (result.draft.next_step or "")
    assert result.draft.primary_intent == "product_evaluation"
    assert result.request_id == "provider-request-1"
    assert result.model == "deepseek-test"
    assert result.input_tokens == 120
    assert result.output_tokens == 40
    assert result.total_latency_ms >= 0
    assert len(result.input_hash) == 64
    assert len(result.output_hash) == 64


@pytest.mark.asyncio
async def test_summary_provider_retries_retryable_status_without_leaking_body() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "private provider body"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "访客关注产品能力",
                                    "interests": ["产品能力"],
                                    "strength": "medium",
                                    "primary_intent": "information_research",
                                    "next_step": "安排人工沟通",
                                    "risk_notes": None,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekSummaryProvider(_settings(), client).generate(
            [SummaryMessage(id="message-1", role="user", content="介绍产品")]
        )

    assert attempts == 2
    assert result.retry_count == 1


@pytest.mark.asyncio
async def test_summary_provider_rejects_invalid_schema() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"strength":"high"}'}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ApiError) as captured:
            await DeepSeekSummaryProvider(_settings(), client).generate(
                [SummaryMessage(id="message-1", role="user", content="问题")]
            )

    assert captured.value.code == "SUMMARY_RESPONSE_INVALID"

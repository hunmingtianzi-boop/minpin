from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.api.errors import ApiError
from app.api.workflow_schemas import SummaryDraft
from app.core.config import Settings
from app.core.redaction import redact_sensitive_text

SUMMARY_PROMPT_VERSION = "visit-summary-v1"
SUMMARY_SYSTEM_PROMPT = """
你是企业数智名片的拜访纪要助手。只根据提供的已脱敏对话生成结构化纪要，绝不补充对话中没有的事实。
输出必须是单个 JSON 对象，且只能包含：summary、interests、strength、next_step、risk_notes。
strength 只能是 low、medium、high、unknown。interests 最多 12 项。
不得输出电话、邮箱、微信号、身份证、密钥或其他个人敏感值；如对话中出现，只概括为“访客已主动留资”。
风险、报价、合同、承诺等信息必须保守表述，并在 risk_notes 中明确需要人工确认。
""".strip()


@dataclass(frozen=True, slots=True)
class SummaryMessage:
    id: str
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class SummaryGeneration:
    draft: SummaryDraft
    provider: str
    model: str
    request_id: str | None
    input_hash: str
    output_hash: str
    input_tokens: int
    output_tokens: int
    total_latency_ms: int
    retry_count: int


class DeepSeekSummaryProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def generate(
        self,
        messages: Sequence[SummaryMessage],
        *,
        trace_id: str | None = None,
    ) -> SummaryGeneration:
        api_key = self._settings.llm_api_key
        if api_key is None:
            raise ApiError(503, "LLM_API_KEY_MISSING", "AI 纪要服务尚未配置")
        dialogue = _bounded_redacted_dialogue(messages)
        input_payload = json.dumps(
            {"conversation": dialogue},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        input_hash = hashlib.sha256(
            f"{SUMMARY_SYSTEM_PROMPT}\n{input_payload}".encode("utf-8")
        ).hexdigest()
        request_payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": input_payload},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": min(self._settings.llm_max_output_tokens, 1_000),
            "stream": False,
            "thinking": {"type": self._settings.llm_thinking},
        }
        if self._settings.llm_thinking != "enabled":
            request_payload["temperature"] = self._settings.llm_temperature
        elif self._settings.llm_reasoning_effort:
            request_payload["reasoning_effort"] = self._settings.llm_reasoning_effort

        started = time.perf_counter()
        response: httpx.Response | None = None
        retry_count = 0
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                        **({"X-Request-Id": trace_id} if trace_id else {}),
                    },
                    json=request_payload,
                    timeout=self._settings.llm_timeout_seconds,
                )
            except (httpx.HTTPError, TimeoutError) as exc:
                if attempt >= self._settings.llm_max_retries:
                    raise ApiError(
                        503,
                        "SUMMARY_PROVIDER_UNAVAILABLE",
                        "AI 纪要服务暂不可用",
                    ) from exc
                retry_count += 1
                await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
                continue
            if response.status_code < 400:
                break
            if response.status_code not in {408, 409, 429} and response.status_code < 500:
                raise ApiError(503, "SUMMARY_PROVIDER_REJECTED", "AI 纪要服务拒绝了请求")
            if attempt >= self._settings.llm_max_retries:
                raise ApiError(503, "SUMMARY_PROVIDER_UNAVAILABLE", "AI 纪要服务暂不可用")
            retry_count += 1
            await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
        if response is None:
            raise ApiError(503, "SUMMARY_PROVIDER_UNAVAILABLE", "AI 纪要服务暂不可用")
        total_latency_ms = max(0, round((time.perf_counter() - started) * 1_000))
        try:
            payload: Any = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            content = _strip_json_fence(content)
            raw_draft = SummaryDraft.model_validate(json.loads(content))
            draft = _redact_summary(raw_draft)
            usage = payload.get("usage") if isinstance(payload, dict) else None
            usage = usage if isinstance(usage, dict) else {}
            output_json = draft.model_dump_json()
            return SummaryGeneration(
                draft=draft,
                provider=self._settings.llm_provider,
                model=str(payload.get("model") or self._settings.llm_model),
                request_id=(
                    response.headers.get("x-request-id")
                    or (str(payload.get("id")) if payload.get("id") else None)
                ),
                input_hash=input_hash,
                output_hash=hashlib.sha256(output_json.encode("utf-8")).hexdigest(),
                input_tokens=_non_negative_int(usage.get("prompt_tokens")),
                output_tokens=_non_negative_int(usage.get("completion_tokens")),
                total_latency_ms=total_latency_ms,
                retry_count=retry_count,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(503, "SUMMARY_RESPONSE_INVALID", "AI 纪要返回格式无效") from exc


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _bounded_redacted_dialogue(
    messages: Sequence[SummaryMessage],
    *,
    max_chars: int = 30_000,
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    remaining = max_chars
    for item in reversed(messages[-80:]):
        if item.role not in {"user", "assistant", "human"}:
            continue
        redacted = redact_sensitive_text(item.content).content.strip()
        if not redacted:
            continue
        content = redacted[: min(1_600, remaining)]
        if not content:
            break
        accepted.append({"id": item.id, "role": item.role, "content": content})
        remaining -= len(content)
        if remaining <= 0:
            break
    accepted.reverse()
    return accepted


def _redact_summary(value: SummaryDraft) -> SummaryDraft:
    return SummaryDraft(
        summary=redact_sensitive_text(value.summary).content,
        interests=[redact_sensitive_text(item).content for item in value.interests],
        strength=value.strength,
        next_step=(redact_sensitive_text(value.next_step).content if value.next_step else None),
        risk_notes=(redact_sensitive_text(value.risk_notes).content if value.risk_notes else None),
    )


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


__all__ = [
    "DeepSeekSummaryProvider",
    "SUMMARY_PROMPT_VERSION",
    "SUMMARY_SYSTEM_PROMPT",
    "SummaryMessage",
    "SummaryGeneration",
]

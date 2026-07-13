from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.ai import ProviderCredentials, RAGRequest
from app.api.dependencies import get_idempotency_key, get_visitor_principal
from app.api.errors import ApiError
from app.api.schemas import (
    ConsentEnvelope,
    ConsentRequest,
    ConversationEnvelope,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateVisitRequest,
    MessageCompleted,
    MessageDelta,
    MessageError,
    MessageStarted,
    PublicCardEnvelope,
    VisitEnvelope,
)
from app.api.sse import encode_sse
from app.core.metrics import MetricsRegistry
from app.core.rate_limit import RateLimitBackendUnavailable, RedisRateLimiter
from app.core.request_context import request_id_ctx
from app.core.request_security import request_ip_hash, security_subject_hash
from app.core.tokens import VisitorPrincipal
from app.services.public_store import (
    PreparedMessage,
    PublicStore,
    StoredAnswer,
    citations_to_schema,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Public Conversation"])
VisitorDependency = Annotated[VisitorPrincipal, Depends(get_visitor_principal)]
IdempotencyDependency = Annotated[str, Depends(get_idempotency_key)]


def _store(request: Request) -> PublicStore:
    return PublicStore(request.app.state.session_factory, request.app.state.settings)


@router.get(
    "/public/cards/{slug}",
    response_model=PublicCardEnvelope,
    operation_id="getPublicCard",
)
async def get_public_card(slug: str, request: Request) -> PublicCardEnvelope:
    card = await _store(request).get_public_card(slug=slug)
    return PublicCardEnvelope(data=card)


@router.post(
    "/public/cards/{slug}/visits",
    response_model=VisitEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createVisit",
)
async def create_visit(
    slug: str,
    body: CreateVisitRequest,
    request: Request,
    idempotency_key: IdempotencyDependency,
) -> VisitEnvelope:
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-visit-ip-card",
        subject=security_subject_hash(
            settings,
            "public-visit-ip-card",
            ip_hash,
            slug.strip().casefold(),
        ),
        limit=settings.public_visit_ip_card_rate_limit_per_minute,
    )
    visit = await _store(request).create_visit(
        slug=slug,
        request=body,
        idempotency_key=idempotency_key,
    )
    return VisitEnvelope(data=visit)


@router.post(
    "/public/cards/{slug}/consents",
    response_model=ConsentEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="recordConsent",
)
async def record_consent(
    slug: str,
    body: ConsentRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> ConsentEnvelope:
    consent = await _store(request).record_consent(
        slug=slug,
        principal=principal,
        request=body,
        idempotency_key=idempotency_key,
    )
    return ConsentEnvelope(data=consent)


@router.post(
    "/public/cards/{slug}/conversations",
    response_model=ConversationEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createConversation",
)
async def create_conversation(
    slug: str,
    body: CreateConversationRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> ConversationEnvelope:
    conversation = await _store(request).create_conversation(
        slug=slug,
        principal=principal,
        request=body,
        idempotency_key=idempotency_key,
    )
    return ConversationEnvelope(data=conversation)


@router.post(
    "/public/conversations/{conversation_id}/messages:stream",
    operation_id="streamConversationMessage",
)
async def stream_message(
    conversation_id: uuid.UUID,
    body: CreateMessageRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> Response:
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-chat-ip-card",
        subject=security_subject_hash(
            settings,
            "public-chat-ip-card",
            ip_hash,
            principal.card_id,
        ),
        limit=settings.public_chat_ip_card_rate_limit_per_minute,
    )
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-chat-session",
        subject=principal.rate_limit_subject,
        limit=settings.public_chat_rate_limit_per_minute,
    )

    store = _store(request)
    prepared = await store.prepare_message(
        conversation_id=conversation_id,
        principal=principal,
        content=body.content,
        idempotency_key=idempotency_key,
    )
    stored = await store.load_stored_answer(prepared=prepared, principal=principal)
    task: asyncio.Task[StoredAnswer] | None = None
    if stored is None:
        task = asyncio.create_task(
            _generate_and_persist(
                request=request,
                store=store,
                principal=principal,
                prepared=prepared,
            ),
            name=f"ai-answer:{prepared.assistant_message_id}",
        )
        request.app.state.ai_tasks.add(task)
        task.add_done_callback(lambda completed: _finish_background_task(request, completed))

    stream = _answer_events(
        message_id=prepared.assistant_message_id,
        request_id=request_id_ctx.get(),
        stored=stored,
        task=task,
        metrics=getattr(request.app.state, "metrics", None),
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id_ctx.get(),
        },
    )


async def _enforce_public_rate_limit(
    *,
    request: Request,
    bucket: str,
    subject: str,
    limit: int,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        if request.app.state.settings.app_env == "test":
            return
        raise ApiError(503, "RATE_LIMIT_UNAVAILABLE", "访问保护服务正在恢复，请稍后重试")
    try:
        decision = await RedisRateLimiter(redis).check(
            bucket=bucket,
            subject=subject,
            limit=limit,
            window_seconds=60,
        )
    except RateLimitBackendUnavailable as exc:
        raise ApiError(
            503,
            "RATE_LIMIT_UNAVAILABLE",
            "访问保护服务正在恢复，请稍后重试",
        ) from exc
    if not decision.allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "请求过于频繁，请稍后重试",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


async def _generate_and_persist(
    *,
    request: Request,
    store: PublicStore,
    principal: VisitorPrincipal,
    prepared: PreparedMessage,
) -> StoredAnswer:
    # This function is deliberately independent from the response stream so it
    # can finish and persist after a client disconnect.
    settings = request.app.state.settings
    metrics: MetricsRegistry | None = getattr(request.app.state, "metrics", None)
    api_key = settings.llm_api_key
    if api_key is None:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category="configuration",
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code="LLM_API_KEY_MISSING",
        )
        raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务尚未配置")

    semaphore: asyncio.Semaphore = request.app.state.ai_semaphore
    acquired = False
    try:
        await store.assert_model_budget(principal=principal)
        async with asyncio.timeout(settings.llm_queue_timeout_seconds):
            await semaphore.acquire()
            acquired = True

        embedding_credentials = None
        if settings.embedding_provider and settings.embedding_api_key:
            embedding_credentials = ProviderCredentials(
                settings.embedding_api_key.get_secret_value()
            )
        history = await store.load_conversation_history(
            prepared=prepared,
            principal=principal,
        )
        forbidden_topics = await store.load_forbidden_topic_rules(principal=principal)
        result = await request.app.state.rag_orchestrator.answer(
            RAGRequest(
                tenant_id=str(principal.tenant_id),
                company_id=str(principal.company_id),
                card_id=str(principal.card_id),
                question=prepared.question,
                history=history,
                forbidden_topics=forbidden_topics,
            ),
            chat_credentials=ProviderCredentials(api_key.get_secret_value()),
            embedding_credentials=embedding_credentials,
        )
        stored_answer = await store.persist_ai_answer(
            prepared=prepared,
            principal=principal,
            result=result,
        )
        if metrics is not None:
            trace = result.trace
            estimated_cost = (
                trace.input_tokens * settings.llm_input_price_cny_per_million
                + trace.output_tokens * settings.llm_output_price_cny_per_million
            ) / 1_000_000
            metrics.observe_ai_result(
                provider=trace.chat_provider,
                model=trace.chat_model,
                outcome="refusal" if result.refused else "success",
                retrieval_mode=trace.retrieval_mode,
                duration_seconds=trace.elapsed_ms / 1_000,
                model_seconds=trace.model_ms / 1_000,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
                estimated_cost_cny=estimated_cost,
                retrieval_count=trace.retrieval_count,
                citation_count=trace.citation_count,
                refusal_code=result.refusal.code.value if result.refusal else None,
            )
        return stored_answer
    except TimeoutError as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category="queue_timeout",
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code="MODEL_QUEUE_FULL",
        )
        raise ApiError(429, "MODEL_BUSY", "AI 服务繁忙，请稍后重试") from exc
    except ApiError as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category=exc.code,
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code=exc.code,
        )
        raise
    except Exception as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category="unexpected",
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code=type(exc).__name__,
        )
        raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务暂不可用，请稍后重试") from exc
    finally:
        if acquired:
            semaphore.release()


async def _answer_events(
    *,
    message_id: uuid.UUID,
    request_id: str,
    stored: StoredAnswer | None,
    task: asyncio.Task[StoredAnswer] | None,
    metrics: MetricsRegistry | None = None,
) -> AsyncIterator[bytes]:
    stream_started = time.perf_counter()
    answer_source = "cache" if stored is not None else "generated"
    yield encode_sse(
        "message.started",
        MessageStarted(message_id=message_id, request_id=request_id).model_dump(mode="json"),
    )
    answer = stored
    if answer is None and task is not None:
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    yield b": keep-alive\n\n"
            answer = await asyncio.shield(task)
        except ApiError as exc:
            yield encode_sse(
                "message.error",
                MessageError(
                    code=exc.code,
                    retryable=exc.status_code in {429, 503},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
            return
        except Exception:
            yield encode_sse(
                "message.error",
                MessageError(
                    code="MODEL_UNAVAILABLE",
                    retryable=True,
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
            return
    if answer is None:
        yield encode_sse(
            "message.error",
            MessageError(
                code="MESSAGE_NOT_READY",
                retryable=True,
                request_id=request_id,
            ).model_dump(mode="json"),
        )
        return

    first_content = True
    for chunk in _text_chunks(answer.text):
        if first_content and metrics is not None:
            metrics.observe_first_token(
                source=answer_source,
                duration_seconds=time.perf_counter() - stream_started,
            )
            first_content = False
        yield encode_sse(
            "message.delta",
            MessageDelta(text=chunk).model_dump(mode="json"),
        )
    for citation in citations_to_schema(answer.citations):
        yield encode_sse("message.citation", citation.model_dump(mode="json"))
    yield encode_sse(
        "message.completed",
        MessageCompleted(
            message_id=answer.message_id,
            finish_reason=answer.finish_reason,
            lead_prompt=answer.lead_prompt,
        ).model_dump(mode="json"),
    )


def _text_chunks(value: str, size: int = 48) -> tuple[str, ...]:
    if not value:
        return ("",)
    return tuple(value[index : index + size] for index in range(0, len(value), size))


def _finish_background_task(request: Request, task: asyncio.Task[StoredAnswer]) -> None:
    request.app.state.ai_tasks.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.warning(
            "background_ai_answer_failed",
            error_type=type(error).__name__,
            task_name=task.get_name(),
        )

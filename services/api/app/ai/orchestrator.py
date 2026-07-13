"""Application-facing orchestration for safe, cited enterprise RAG answers."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from .errors import AIErrorCategory, AIProviderError, AIServiceError
from .policy import EvidenceGate, InputSecurityPolicy
from .prompts import DEFAULT_PROMPT_VERSION, PromptRegistry
from .protocols import ChatProvider, EmbeddingProvider, RetrievalRepository
from .schemas import (
    AIAnswer,
    ChatCompletion,
    ChatMessage,
    Citation,
    ForbiddenTopicPolicy,
    ProviderCredentials,
    RAGRequest,
    Refusal,
    RefusalCode,
    RetrievalQuery,
    RetrievedEvidence,
    TraceMetadata,
)


@dataclass(frozen=True, slots=True)
class RAGOrchestratorConfig:
    prompt_version: str = DEFAULT_PROMPT_VERSION
    top_k: int = 6
    candidate_limit: int = 30
    trigram_threshold: float = 0.12
    rrf_k: int = 60
    vector_weight: float = 1.0
    lexical_weight: float = 1.0
    temperature: float = 0.1
    max_tokens: int = 1200
    citation_excerpt_chars: int = 320
    fallback_to_lexical_on_embedding_error: bool = True

    def __post_init__(self) -> None:
        if self.top_k <= 0 or self.candidate_limit < self.top_k:
            raise ValueError("invalid retrieval limits")
        if not 0 <= self.trigram_threshold <= 1:
            raise ValueError("trigram_threshold must be between 0 and 1")
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if self.vector_weight < 0 or self.lexical_weight < 0:
            raise ValueError("retrieval weights must not be negative")
        if self.vector_weight == 0 and self.lexical_weight == 0:
            raise ValueError("at least one retrieval weight must be positive")
        if not 0 <= self.temperature <= 2 or self.max_tokens <= 0:
            raise ValueError("invalid chat generation settings")
        if self.citation_excerpt_chars <= 0:
            raise ValueError("citation_excerpt_chars must be positive")


@dataclass(slots=True)
class _TraceState:
    trace_id: str
    query_fingerprint: str
    started_at: float
    prompt_version: str
    chat_provider: str
    chat_model: str
    embedding_provider: str | None
    embedding_model: str | None
    retrieval_mode: Literal["hybrid", "lexical", "skipped"] = "skipped"
    retrieval_count: int = 0
    policy_flags: tuple[str, ...] = ()
    retrieval_ms: int = 0
    model_ms: int = 0
    provider_request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def finish(self, citations: Sequence[Citation]) -> TraceMetadata:
        return TraceMetadata(
            trace_id=self.trace_id,
            query_fingerprint=self.query_fingerprint,
            prompt_version=self.prompt_version,
            chat_provider=self.chat_provider,
            chat_model=self.chat_model,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            retrieval_mode=self.retrieval_mode,
            retrieval_count=self.retrieval_count,
            citation_count=len(citations),
            policy_flags=self.policy_flags,
            elapsed_ms=_elapsed_ms(self.started_at),
            retrieval_ms=self.retrieval_ms,
            model_ms=self.model_ms,
            provider_request_id=self.provider_request_id,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            error_category=self.error_category,
            extra=dict(self.extra),
        )


class RAGOrchestrator:
    """Coordinate safety, optional embeddings, retrieval, generation and gating.

    Provider credentials are method arguments and are not stored on this object.
    This makes the orchestrator safe to reuse across tenant requests.
    """

    def __init__(
        self,
        chat_provider: ChatProvider,
        retrieval_repository: RetrievalRepository,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        security_policy: InputSecurityPolicy | None = None,
        evidence_gate: EvidenceGate | None = None,
        prompt_registry: PromptRegistry | None = None,
        config: RAGOrchestratorConfig | None = None,
    ) -> None:
        self._chat_provider = chat_provider
        self._retrieval_repository = retrieval_repository
        self._embedding_provider = embedding_provider
        self._security_policy = security_policy or InputSecurityPolicy()
        self._evidence_gate = evidence_gate or EvidenceGate()
        self._prompt_registry = prompt_registry or PromptRegistry()
        self.config = config or RAGOrchestratorConfig()
        self._prompt_registry.get(self.config.prompt_version)

    async def answer(
        self,
        request: RAGRequest,
        *,
        chat_credentials: ProviderCredentials,
        embedding_credentials: ProviderCredentials | None = None,
    ) -> AIAnswer:
        started_at = time.perf_counter()
        trace_id = str(uuid.uuid4())
        policy = self._security_policy.evaluate(request.question)
        normalized = policy.normalized_text
        trace = _TraceState(
            trace_id=trace_id,
            query_fingerprint=_query_fingerprint(
                request.tenant_id,
                request.company_id,
                normalized,
            ),
            started_at=started_at,
            prompt_version=self.config.prompt_version,
            chat_provider=self._chat_provider.provider_name,
            chat_model=self._chat_provider.model_name,
            embedding_provider=(
                self._embedding_provider.provider_name if self._embedding_provider else None
            ),
            embedding_model=(
                self._embedding_provider.model_name if self._embedding_provider else None
            ),
            policy_flags=tuple(flag.value for flag in policy.flags),
        )
        if policy.blocked:
            trace.error_category = AIErrorCategory.SAFETY.value
            return _refused(policy.refusal, trace)

        forbidden = _match_forbidden_topic(normalized, request.forbidden_topics)
        if forbidden is not None:
            trace.policy_flags += ("forbidden_topic",)
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra.update(
                {
                    "forbidden_rule_id": forbidden.rule_id,
                    "forbidden_rule_version": forbidden.version,
                    "forbidden_action": forbidden.action,
                    "needs_human_review": forbidden.action == "handoff",
                }
            )
            return _refused(_forbidden_refusal(forbidden), trace)

        embedding: tuple[float, ...] | None = None
        if self._embedding_provider is not None and embedding_credentials is not None:
            embedding_started = time.perf_counter()
            try:
                batch = await self._embedding_provider.embed(
                    [normalized],
                    credentials=embedding_credentials,
                    trace_id=trace_id,
                )
                if len(batch.embeddings) != 1:
                    raise ValueError("embedding provider returned the wrong batch size")
                embedding = batch.embeddings[0]
                trace.extra["embedding_request_id"] = batch.request_id
            except AIProviderError as exc:
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
                if not self.config.fallback_to_lexical_on_embedding_error:
                    trace.error_category = exc.category.value
                    return _refused(_provider_refusal(exc), trace)
                trace.extra["embedding_fallback_category"] = exc.category.value
                trace.extra["embedding_fallback_code"] = exc.code
            except (IndexError, ValueError):
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
                if not self.config.fallback_to_lexical_on_embedding_error:
                    trace.error_category = AIErrorCategory.INVALID_RESPONSE.value
                    return _refused(
                        Refusal(
                            code=RefusalCode.PROVIDER_ERROR,
                            reason="向量服务返回了无效结果。",
                            safe_alternative="请稍后重试。",
                        ),
                        trace,
                    )
                trace.extra["embedding_fallback_category"] = AIErrorCategory.INVALID_RESPONSE.value
                trace.extra["embedding_fallback_code"] = "invalid_embedding_batch"
            else:
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
        elif self._embedding_provider is not None:
            trace.extra["embedding_skipped"] = "credentials_not_supplied"

        trace.retrieval_mode = "hybrid" if embedding is not None else "lexical"
        top_k = request.top_k if request.top_k is not None else self.config.top_k
        retrieval_text = _compose_retrieval_text(normalized, request.history)
        retrieval_started = time.perf_counter()
        try:
            evidence = tuple(
                await self._retrieval_repository.search(
                    RetrievalQuery(
                        tenant_id=request.tenant_id,
                        company_id=request.company_id,
                        text=retrieval_text,
                        embedding=embedding,
                        top_k=top_k,
                        candidate_limit=max(top_k, self.config.candidate_limit),
                        trigram_threshold=self.config.trigram_threshold,
                        rrf_k=self.config.rrf_k,
                        vector_weight=self.config.vector_weight,
                        lexical_weight=self.config.lexical_weight,
                        card_id=request.card_id,
                    )
                )
            )
        except AIServiceError as exc:
            trace.retrieval_ms = _elapsed_ms(retrieval_started)
            trace.error_category = exc.category.value
            return _refused(
                Refusal(
                    code=RefusalCode.RETRIEVAL_ERROR,
                    reason="知识检索暂时不可用。",
                    retryable=exc.retryable,
                    safe_alternative="请稍后重试或联系企业工作人员。",
                ),
                trace,
            )
        trace.retrieval_ms = _elapsed_ms(retrieval_started)
        trace.retrieval_count = len(evidence)
        trace.extra["retrieved_evidence_ids"] = tuple(item.evidence_id for item in evidence)
        trace.extra["retrieved_version_ids"] = tuple(
            dict.fromkeys(item.version_id for item in evidence)
        )

        pre_gate = self._evidence_gate.before_generation(policy, evidence)
        if not pre_gate.allowed:
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra["needs_human_review"] = pre_gate.needs_human_review
            return _refused(pre_gate.refusal, trace)

        prompt = self._prompt_registry.get(self.config.prompt_version)
        messages = prompt.render(
            question=normalized,
            evidence=pre_gate.evidence,
            policy=policy,
            history=request.history,
        )
        model_started = time.perf_counter()
        try:
            completion = await self._chat_provider.complete(
                messages,
                credentials=chat_credentials,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                trace_id=trace_id,
            )
        except AIProviderError as exc:
            trace.model_ms = _elapsed_ms(model_started)
            trace.error_category = exc.category.value
            trace.provider_request_id = exc.request_id
            return _refused(_provider_refusal(exc), trace)
        trace.model_ms = _elapsed_ms(model_started)
        _add_completion_trace(trace, completion)

        post_gate = self._evidence_gate.after_generation(
            policy,
            completion.output,
            pre_gate.evidence,
        )
        if not post_gate.allowed:
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra["needs_human_review"] = post_gate.needs_human_review
            return _refused(post_gate.refusal, trace)

        citations = tuple(
            _citation_from_evidence(item, self.config.citation_excerpt_chars)
            for item in post_gate.evidence
        )
        trace.extra["needs_human_review"] = post_gate.needs_human_review
        trace.extra["cited_content_hashes"] = tuple(
            citation.content_hash for citation in citations if citation.content_hash
        )
        return AIAnswer(
            answer=completion.output.answer,
            citations=citations,
            refusal=None,
            trace=trace.finish(citations),
        )


def _add_completion_trace(trace: _TraceState, completion: ChatCompletion) -> None:
    trace.provider_request_id = completion.request_id
    trace.input_tokens = completion.usage.input_tokens
    trace.output_tokens = completion.usage.output_tokens
    trace.extra["response_model"] = completion.model


def _provider_refusal(error: AIProviderError) -> Refusal:
    reason = "AI 服务暂时不可用。" if error.retryable else "AI 服务请求未能完成。"
    return Refusal(
        code=RefusalCode.PROVIDER_ERROR,
        reason=reason,
        retryable=error.retryable,
        safe_alternative="请稍后重试或联系企业工作人员。",
    )


def _refused(refusal: Refusal | None, trace: _TraceState) -> AIAnswer:
    safe_refusal = refusal or Refusal(
        code=RefusalCode.INPUT_INVALID,
        reason="请求无法处理。",
    )
    return AIAnswer(
        answer="",
        citations=(),
        refusal=safe_refusal,
        trace=trace.finish(()),
    )


def _match_forbidden_topic(
    text: str,
    rules: Sequence[ForbiddenTopicPolicy],
) -> ForbiddenTopicPolicy | None:
    normalized = " ".join(text.casefold().split())
    best: tuple[int, int, ForbiddenTopicPolicy] | None = None
    for rule in rules:
        matched_lengths = [
            len(candidate)
            for term in (rule.topic, *rule.match_terms)
            if (candidate := " ".join(term.casefold().split()))
            and _rule_term_matches(normalized, candidate)
        ]
        if not matched_lengths:
            continue
        candidate_rule = (max(matched_lengths), rule.version, rule)
        if best is None or candidate_rule[:2] > best[:2]:
            best = candidate_rule
    return best[2] if best else None


def _rule_term_matches(text: str, term: str) -> bool:
    simple_ascii = term.isascii() and all(
        character.isalnum() or character in {"-", "_", " "} for character in term
    )
    if simple_ascii:
        return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None
    return term in text


def _forbidden_refusal(rule: ForbiddenTopicPolicy) -> Refusal:
    if rule.action == "safe_template":
        return Refusal(
            code=RefusalCode.FORBIDDEN_TOPIC,
            reason=rule.safe_response or "该话题暂不在企业授权答复范围内。",
        )
    if rule.action == "handoff":
        return Refusal(
            code=RefusalCode.FORBIDDEN_TOPIC,
            reason="该问题需要由企业工作人员进一步确认。",
            safe_alternative=rule.safe_response or "您可以留下联系方式，我们会安排人工跟进。",
        )
    return Refusal(
        code=RefusalCode.FORBIDDEN_TOPIC,
        reason="该话题不在企业授权答复范围内。",
        safe_alternative=rule.safe_response or "可以继续咨询已发布的企业、产品或服务信息。",
    )


def _citation_from_evidence(evidence: RetrievedEvidence, max_chars: int) -> Citation:
    excerpt = " ".join(evidence.text.split())
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rstrip() + "…"
    return Citation(
        evidence_id=evidence.evidence_id,
        document_id=evidence.document_id,
        version_id=evidence.version_id,
        ordinal=evidence.ordinal,
        title=evidence.title,
        excerpt=excerpt,
        source_url=evidence.source_url,
        content_hash=evidence.content_hash,
        score=evidence.score,
    )


def _query_fingerprint(tenant_id: str, company_id: str, normalized: str) -> str:
    material = f"{tenant_id}\x00{company_id}\x00{normalized}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _compose_retrieval_text(normalized: str, history: Sequence[ChatMessage]) -> str:
    previous_user_turns = [
        str(item.content).strip()[:300]
        for item in history
        if item.role == "user" and item.content.strip()
    ][-2:]
    if not previous_user_turns:
        return normalized
    return "\n".join([*previous_user_turns, normalized])

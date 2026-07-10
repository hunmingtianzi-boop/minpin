from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import TextClause

from app.ai import (
    ChatProviderConfig,
    EmbeddingProviderConfig,
    EvidenceGate,
    EvidenceGateConfig,
    HttpxJsonTransport,
    HybridRetrievalConfig,
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
    PostgresHybridRetrievalRepository,
    RAGOrchestrator,
    RAGOrchestratorConfig,
)
from app.ai.protocols import AsyncSqlExecutor
from app.core.config import Settings


class ScopedSessionExecutor(AsyncSqlExecutor):
    """Execute one retrieval query in a short, RLS-scoped transaction.

    The model call happens after this method returns, so no database connection or
    transaction remains open while waiting on a model provider.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def fetch_mappings(
        self,
        statement: TextClause,
        parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        tenant_id = str(parameters.get("tenant_id", "")).strip()
        company_id = str(parameters.get("company_id", "")).strip()
        if not tenant_id or not company_id:
            raise ValueError("tenant_id and company_id are required for scoped retrieval")

        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    SELECT
                        set_config('app.tenant_id', :tenant_id, true),
                        set_config('app.company_id', :company_id, true),
                        set_config('app.card_slug', '', true)
                    """
                ),
                {"tenant_id": tenant_id, "company_id": company_id},
            )
            result = await session.execute(statement, dict(parameters))
            return [dict(row) for row in result.mappings().all()]


def build_rag_orchestrator(
    *,
    settings: Settings,
    http_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> RAGOrchestrator:
    transport = HttpxJsonTransport(http_client)
    chat_provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            provider_name=settings.llm_provider,
            timeout_seconds=settings.llm_timeout_seconds,
            thinking_mode=settings.llm_thinking,
            reasoning_effort=(
                settings.llm_reasoning_effort if settings.llm_thinking == "enabled" else None
            ),
            max_retries=settings.llm_max_retries,
        ),
        transport=transport,
    )

    embedding_provider = None
    if settings.embedding_provider:
        assert settings.embedding_base_url is not None
        assert settings.embedding_model is not None
        embedding_provider = OpenAICompatibleEmbeddingProvider(
            EmbeddingProviderConfig(
                base_url=settings.embedding_base_url,
                model=settings.embedding_model,
                provider_name=settings.embedding_provider,
                timeout_seconds=settings.embedding_timeout_seconds,
                dimensions=settings.embedding_dimension,
            ),
            transport=transport,
        )

    lexical_weight = max(0.0, 1.0 - settings.retrieval_vector_weight)
    retrieval_repository = PostgresHybridRetrievalRepository(
        ScopedSessionExecutor(session_factory),
        config=HybridRetrievalConfig(
            expected_embedding_dimensions=settings.embedding_dimension,
            max_top_k=max(settings.retrieval_top_k, 30),
            max_candidate_limit=max(settings.retrieval_top_k * 8, 100),
        ),
    )
    return RAGOrchestrator(
        chat_provider,
        retrieval_repository,
        embedding_provider=embedding_provider,
        evidence_gate=EvidenceGate(
            EvidenceGateConfig(
                min_vector_score=settings.retrieval_min_vector_score,
                min_lexical_score=settings.retrieval_min_lexical_score,
                max_evidence=settings.retrieval_context_k,
            )
        ),
        config=RAGOrchestratorConfig(
            top_k=settings.retrieval_context_k,
            candidate_limit=max(settings.retrieval_top_k * 4, settings.retrieval_context_k),
            trigram_threshold=settings.retrieval_min_lexical_score,
            vector_weight=settings.retrieval_vector_weight,
            lexical_weight=lexical_weight,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
        ),
    )

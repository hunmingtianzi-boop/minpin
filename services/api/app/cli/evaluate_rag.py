from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai import (
    DEFAULT_PROMPT_VERSION,
    ForbiddenTopicPolicy,
    ProviderCredentials,
    RAGRequest,
)
from app.cli.seed_content import deterministic_id
from app.core.config import Settings, get_settings
from app.core.redaction import redact_sensitive_text
from app.db.models import ForbiddenTopic, KnowledgeChunk
from app.db.session import set_rls_context
from app.evaluation import (
    EvaluationObservation,
    compute_metrics,
    evaluate_release_gate,
    load_evaluation_suite,
)
from app.services.ai_runtime import build_rag_orchestrator


async def _source_ids_for_chunks(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    chunk_ids: list[str],
) -> list[str]:
    valid_ids: list[uuid.UUID] = []
    for chunk_id in chunk_ids:
        try:
            valid_ids.append(uuid.UUID(chunk_id))
        except ValueError:
            continue
    if not valid_ids:
        return []
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                """
                SELECT
                    set_config('app.tenant_id', :tenant_id, true),
                    set_config('app.company_id', :company_id, true),
                    set_config('app.card_slug', '', true)
                """
            ),
            {"tenant_id": str(tenant_id), "company_id": str(company_id)},
        )
        rows = (
            await session.execute(
                select(KnowledgeChunk.id, KnowledgeChunk.source_id).where(
                    KnowledgeChunk.id.in_(valid_ids)
                )
            )
        ).all()
    by_id = {str(chunk_id): source_id for chunk_id, source_id in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


async def _forbidden_topic_policies(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
) -> tuple[ForbiddenTopicPolicy, ...]:
    async with sessions() as session, session.begin():
        await set_rls_context(session, tenant_id=tenant_id, company_id=company_id)
        rows = (
            await session.scalars(
                select(ForbiddenTopic)
                .where(
                    ForbiddenTopic.tenant_id == tenant_id,
                    ForbiddenTopic.company_id == company_id,
                    ForbiddenTopic.is_active.is_(True),
                )
                .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                .limit(200)
            )
        ).all()
    return tuple(
        ForbiddenTopicPolicy(
            rule_id=str(row.id),
            topic=row.topic,
            match_terms=tuple(row.match_terms),
            action=row.action,
            safe_response=(
                redact_sensitive_text(row.safe_response).content if row.safe_response else None
            ),
            version=row.version,
        )
        for row in rows
    )


async def run_evaluation(
    *,
    dataset: Path,
    settings: Settings,
    tenant_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    suite = load_evaluation_suite(dataset)
    dataset_bytes = await asyncio.to_thread(dataset.read_bytes)
    tenant_id = tenant_id or deterministic_id(suite.tenant_slug, "tenant")
    company_id = company_id or deterministic_id(suite.tenant_slug, "company")
    if settings.llm_api_key is None:
        raise ValueError("LLM_API_KEY is required to run the live RAG evaluation")

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    observations: list[EvaluationObservation] = []
    try:
        forbidden_topics = await _forbidden_topic_policies(
            sessions,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=5.0)
        ) as client:
            orchestrator = build_rag_orchestrator(
                settings=settings,
                http_client=client,
                session_factory=sessions,
            )
            chat_credentials = ProviderCredentials(settings.llm_api_key.get_secret_value())
            embedding_credentials = (
                ProviderCredentials(settings.embedding_api_key.get_secret_value())
                if settings.embedding_provider and settings.embedding_api_key
                else None
            )
            for case in suite.cases:
                started = time.perf_counter()
                result = await orchestrator.answer(
                    RAGRequest(
                        tenant_id=str(tenant_id),
                        company_id=str(company_id),
                        question=case.question,
                        forbidden_topics=forbidden_topics,
                    ),
                    chat_credentials=chat_credentials,
                    embedding_credentials=embedding_credentials,
                )
                retrieved_chunk_ids = [
                    str(value)
                    for value in result.trace.extra.get("retrieved_evidence_ids", ())
                ]
                cited_chunk_ids = [citation.evidence_id for citation in result.citations]
                retrieved_source_ids = await _source_ids_for_chunks(
                    sessions,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    chunk_ids=retrieved_chunk_ids,
                )
                cited_source_ids = await _source_ids_for_chunks(
                    sessions,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    chunk_ids=cited_chunk_ids,
                )
                observations.append(
                    EvaluationObservation(
                        case_id=case.id,
                        retrieved_source_ids=retrieved_source_ids,
                        cited_source_ids=cited_source_ids,
                        refused=result.refused,
                        latency_ms=round((time.perf_counter() - started) * 1_000),
                        severe_security_failure=case.security_critical and not result.refused,
                    )
                )
    finally:
        await engine.dispose()

    metrics = compute_metrics(suite, observations)
    gate = evaluate_release_gate(metrics)
    return {
        "dataset": str(dataset),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "suite_version": suite.version,
        "tenant_slug": suite.tenant_slug,
        "runtime": {
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "prompt_version": DEFAULT_PROMPT_VERSION,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
        },
        "gate": gate.model_dump(mode="json"),
        "observations": [item.model_dump(mode="json") for item in observations],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the versioned RAG release evaluation")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tenant-id", type=uuid.UUID)
    parser.add_argument("--company-id", type=uuid.UUID)
    args = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            dataset=args.dataset,
            settings=get_settings(),
            tenant_id=args.tenant_id,
            company_id=args.company_id,
        )
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not report["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

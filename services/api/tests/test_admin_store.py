from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from app.ai import EmbeddingBatch, ProviderCredentials
from app.api.admin_schemas import (
    KnowledgeDocumentRecord,
    KnowledgePublishResult,
    KnowledgeVersionSummary,
)
from app.api.errors import ApiError
from app.core.config import Settings
from app.services.admin_store import (
    AdminScope,
    AdminStore,
    PreparedChunk,
    PreparedPublish,
    as_passage,
    chunk_knowledge_text,
    validate_embedding_vectors,
)


class StubEmbeddingProvider:
    provider_name = "test-embedding"
    model_name = "intfloat/multilingual-e5-large"

    def __init__(self, events: list[str], vectors: tuple[tuple[float, ...], ...]) -> None:
        self.events = events
        self.vectors = vectors
        self.calls: list[tuple[list[str], ProviderCredentials, str | None]] = []

    async def embed(
        self,
        texts: list[str],
        *,
        credentials: ProviderCredentials,
        trace_id: str | None = None,
    ) -> EmbeddingBatch:
        self.events.append("embed")
        self.calls.append((list(texts), credentials, trace_id))
        return EmbeddingBatch(
            embeddings=self.vectors,
            provider=self.provider_name,
            model=self.model_name,
        )


class PublishHarness(AdminStore):
    def __init__(
        self,
        settings: Settings,
        provider: StubEmbeddingProvider,
        prepared: PreparedPublish,
        events: list[str],
    ) -> None:
        super().__init__(cast(Any, object()), settings, embedding_provider=provider)
        self.prepared = prepared
        self.events = events
        self.committed_vectors: list[tuple[float, ...]] | None = None
        self.failed: tuple[str, str] | None = None

    async def _prepare_publish(
        self,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
    ) -> PreparedPublish:
        self.events.append("prepare")
        assert document_id == self.prepared.document_id
        assert version_id in {None, self.prepared.version_id}
        return self.prepared

    async def _commit_publish(
        self,
        *,
        scope: AdminScope,
        prepared: PreparedPublish,
        vectors: list[tuple[float, ...]],
        embedding_model: str,
        trace_id: str | None,
    ) -> KnowledgePublishResult:
        self.events.append("commit")
        self.committed_vectors = list(vectors)
        return _publish_result(prepared)

    async def _safe_mark_job_failed(
        self,
        *,
        scope: AdminScope,
        prepared: PreparedPublish,
        error_code: str,
        error_detail: str,
        trace_id: str | None,
    ) -> None:
        self.events.append("failed")
        self.failed = (error_code, error_detail)


def _settings() -> Settings:
    credential = "-".join(("embedding", "test", "credential"))
    return Settings(
        app_env="test",
        embedding_provider="local-fastembed",
        embedding_base_url="http://127.0.0.1:8010/v1",
        embedding_api_key=credential,
        embedding_model="intfloat/multilingual-e5-large",
        embedding_dimension=1024,
    )


def _scope() -> AdminScope:
    return AdminScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
    )


def _prepared() -> PreparedPublish:
    version_id = uuid.uuid4()
    return PreparedPublish(
        document_id=uuid.uuid4(),
        document_version=3,
        version_id=version_id,
        version_number=2,
        job_id=uuid.uuid4(),
        chunks=(
            PreparedChunk(id=uuid.uuid4(), text="企业资料第一段", content_hash="a" * 64),
            PreparedChunk(id=uuid.uuid4(), text="passage: 企业资料第二段", content_hash="b" * 64),
        ),
    )


def _publish_result(prepared: PreparedPublish) -> KnowledgePublishResult:
    now = datetime.now(UTC)
    version = KnowledgeVersionSummary(
        id=prepared.version_id,
        version_number=prepared.version_number,
        review_status="approved",
        chunk_count=len(prepared.chunks),
        indexed_chunk_count=len(prepared.chunks),
        published_at=now,
        created_at=now,
    )
    document = KnowledgeDocumentRecord(
        id=prepared.document_id,
        source_type="manual",
        source_id=f"admin:{prepared.document_id}",
        title="企业资料",
        status="published",
        version=prepared.document_version + 1,
        current_version_id=prepared.version_id,
        current_version_number=prepared.version_number,
        latest_version=version,
        created_at=now,
        updated_at=now,
    )
    return KnowledgePublishResult(
        document=document,
        published_version=version,
        index_job_id=prepared.job_id,
        index_status="succeeded",
    )


def test_chunking_prefix_and_vector_validation_are_deterministic() -> None:
    chunks = chunk_knowledge_text("第一段\n\n第二段", max_chars=100)
    assert chunks == ("第一段\n\n第二段",)
    assert as_passage("  企业   资料 ") == "passage: 企业 资料"
    assert as_passage("passage: 已有前缀") == "passage: 已有前缀"

    vectors = validate_embedding_vectors(
        [[0.0] * 1024, [1.0] * 1024],
        expected_count=2,
    )
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_vector_validation_rejects_non_finite_values(invalid: float) -> None:
    vector = [0.0] * 1024
    vector[4] = invalid
    with pytest.raises(ValueError, match="invalid vector"):
        validate_embedding_vectors([vector], expected_count=1)


async def test_publish_generates_passage_embeddings_between_two_transactions() -> None:
    events: list[str] = []
    prepared = _prepared()
    vectors = tuple(tuple([float(index)] + [0.0] * 1023) for index in range(2))
    provider = StubEmbeddingProvider(events, vectors)
    store = PublishHarness(_settings(), provider, prepared, events)

    result = await store.publish_document(
        scope=_scope(),
        document_id=prepared.document_id,
        trace_id="request-1",
    )

    assert events == ["prepare", "embed", "commit"]
    assert provider.calls[0][0] == [
        "passage: 企业资料第一段",
        "passage: 企业资料第二段",
    ]
    assert provider.calls[0][2] == "request-1"
    assert store.committed_vectors == list(vectors)
    assert result.document.current_version_id == prepared.version_id
    assert result.index_status == "succeeded"


async def test_publish_failure_records_job_failure_without_switching_version() -> None:
    events: list[str] = []
    prepared = _prepared()
    provider = StubEmbeddingProvider(events, ((0.0,), (1.0,)))
    store = PublishHarness(_settings(), provider, prepared, events)

    with pytest.raises(ApiError) as captured:
        await store.publish_document(scope=_scope(), document_id=prepared.document_id)

    assert captured.value.code == "EMBEDDING_FAILED"
    assert events == ["prepare", "embed", "failed"]
    assert store.committed_vectors is None
    assert store.failed is not None
    assert store.failed[0] == "ValueError"


async def test_set_scope_delegates_exact_tenant_and_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, uuid.UUID, uuid.UUID]] = []

    async def fake_set_rls_context(
        session: object,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        calls.append((session, tenant_id, company_id))

    monkeypatch.setattr(
        "app.services.admin_store.set_rls_context",
        fake_set_rls_context,
    )
    scope = _scope()
    session = object()
    store = AdminStore(cast(Any, object()), _settings())

    await store._set_scope(cast(Any, session), scope)

    assert calls == [(session, scope.tenant_id, scope.company_id)]

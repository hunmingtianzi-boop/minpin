from __future__ import annotations

from typing import Any, Mapping, Sequence

import pytest

from app.ai import (
    HybridRetrievalConfig,
    KnowledgeSqlSchema,
    PostgresHybridRetrievalRepository,
    RetrievalQuery,
)


class RecordingExecutor:
    def __init__(self, rows: Sequence[Mapping[str, Any]] = ()) -> None:
        self.rows = rows
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    async def fetch_mappings(
        self,
        statement: Any,
        parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        self.calls.append((statement, dict(parameters)))
        return self.rows


def _row() -> dict[str, Any]:
    return {
        "evidence_id": "chunk-1",
        "document_id": "doc-1",
        "version_id": "version-2",
        "ordinal": 3,
        "title": "服务介绍",
        "evidence_text": "标准版包含企业名片和智能问答。",
        "embedding_model": "embed-v1",
        "metadata": {"source_url": "https://example.test/source"},
        "content_hash": "sha256:abc",
        "vector_score": 0.88,
        "lexical_score": 0.42,
        "fused_score": 0.031,
    }


def _repository(executor: RecordingExecutor) -> PostgresHybridRetrievalRepository:
    return PostgresHybridRetrievalRepository(
        executor,
        config=HybridRetrievalConfig(
            expected_embedding_dimensions=3,
            embedding_model="embed-v1",
        ),
    )


@pytest.mark.asyncio
async def test_hybrid_sql_enforces_scope_publication_and_current_version() -> None:
    executor = RecordingExecutor([_row()])
    repository = _repository(executor)

    evidence = await repository.search(
        RetrievalQuery(
            tenant_id="00000000-0000-0000-0000-000000000001",
            company_id="00000000-0000-0000-0000-000000000002",
            text="标准版服务",
            embedding=(0.1, 0.2, 0.3),
        )
    )

    statement, parameters = executor.calls[0]
    sql = " ".join(str(statement).split())
    assert "d.tenant_id = CAST(:tenant_id AS uuid)" in sql
    assert "d.company_id = CAST(:company_id AS uuid)" in sql
    assert "v.tenant_id = CAST(:tenant_id AS uuid)" in sql
    assert "c.tenant_id = CAST(:tenant_id AS uuid)" in sql
    assert "d.current_version_id = c.version_id" in sql
    assert "v.review_status = :published_review_status" in sql
    assert "c.visibility = :public_visibility" in sql
    assert "d.status = :active_document_status" in sql
    assert "<=> CAST(:query_embedding AS vector)" in sql
    assert "similarity(e.evidence_text, :query_text)" in sql
    assert "FULL OUTER JOIN lexical_ranked" in sql
    assert "CAST(:embedding_model AS text) IS NULL" in sql
    assert "e.embedding_model = CAST(:embedding_model AS text)" in sql
    assert "FROM products AS product" in sql
    assert "product.status = 'published'" in sql
    assert "FROM case_studies AS case_study" in sql
    assert "case_study.status = 'published'" in sql
    assert ":rrf_k + v.vector_rank" in sql
    assert parameters["query_embedding"] == "[0.1,0.2,0.3]"
    assert parameters["published_review_status"] == "approved"
    assert parameters["public_visibility"] == "public"
    assert parameters["active_document_status"] == "published"
    assert parameters["embedding_model"] == "embed-v1"
    assert evidence[0].evidence_id == "chunk-1"
    assert evidence[0].source_url == "https://example.test/source"
    assert evidence[0].score == pytest.approx(0.031)


@pytest.mark.asyncio
async def test_lexical_path_has_no_vector_expression_but_keeps_all_scope_filters() -> None:
    executor = RecordingExecutor()
    repository = _repository(executor)

    await repository.search(
        RetrievalQuery(
            tenant_id="00000000-0000-0000-0000-000000000001",
            company_id="00000000-0000-0000-0000-000000000002",
            text="企业服务",
            embedding=None,
        )
    )

    statement, parameters = executor.calls[0]
    sql = " ".join(str(statement).split())
    assert "query_embedding" not in sql
    assert "similarity(e.evidence_text, :query_text)" in sql
    assert "d.current_version_id = c.version_id" in sql
    assert "v.review_status = :published_review_status" in sql
    assert "c.visibility = :public_visibility" in sql
    assert "query_embedding" not in parameters
    assert parameters["embedding_model"] == "embed-v1"


def test_sql_schema_rejects_identifier_injection() -> None:
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        KnowledgeSqlSchema(chunks_table="knowledge_chunks; DROP TABLE users")


@pytest.mark.asyncio
async def test_optional_chunk_active_column_adds_server_side_filter() -> None:
    executor = RecordingExecutor()
    repository = PostgresHybridRetrievalRepository(
        executor,
        config=HybridRetrievalConfig(
            schema=KnowledgeSqlSchema(chunk_is_active="is_active"),
            expected_embedding_dimensions=3,
        ),
    )

    await repository.search(
        RetrievalQuery(
            tenant_id="00000000-0000-0000-0000-000000000001",
            company_id="00000000-0000-0000-0000-000000000002",
            text="企业服务",
        )
    )

    assert "c.is_active IS TRUE" in str(executor.calls[0][0])


@pytest.mark.asyncio
async def test_embedding_dimension_and_limits_are_validated_before_sql() -> None:
    executor = RecordingExecutor()
    repository = _repository(executor)

    with pytest.raises(ValueError, match="dimension mismatch"):
        await repository.search(
            RetrievalQuery(
                tenant_id="tenant",
                company_id="company",
                text="question",
                embedding=(0.1, 0.2),
            )
        )

    assert executor.calls == []

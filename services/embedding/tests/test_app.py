from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import _prepare_text, _serialize_embeddings


ACCESS_TOKEN = "unit-test-access-token"


class StubTextEmbedding:
    def __init__(self) -> None:
        self.vectors: list[list[float]] | None = None
        self.calls: list[tuple[list[str], int]] = []

    def embed(
        self, documents: str | Iterable[str], batch_size: int = 256
    ) -> Iterator[Sequence[float]]:
        inputs = [documents] if isinstance(documents, str) else list(documents)
        self.calls.append((inputs, batch_size))
        vectors = self.vectors
        if vectors is None:
            vectors = [
                [float(index)] + [0.0] * (app_module.MODEL_DIMENSION - 1)
                for index in range(len(inputs))
            ]
        return iter(vectors)


@pytest.fixture
def service_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path]]:
    model = StubTextEmbedding()
    constructor_calls: list[dict[str, Any]] = []
    cache_dir = tmp_path / "models"

    def build_model(**kwargs: Any) -> StubTextEmbedding:
        constructor_calls.append(kwargs)
        return model

    monkeypatch.setenv("EMBEDDING_API_KEY", ACCESS_TOKEN)
    monkeypatch.setattr(app_module, "TextEmbedding", build_model)
    monkeypatch.setattr(app_module, "MODEL_CACHE", cache_dir)

    with TestClient(app_module.app) as client:
        yield client, model, constructor_calls, cache_dir

    assert app_module.app.state.model is None


def authorization(value: str = ACCESS_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def valid_request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": app_module.MODEL_NAME,
        "input": "数据库如何保证租户隔离？",
        "encoding_format": "float",
    }
    payload.update(overrides)
    return payload


def test_prepare_text_defaults_to_query_and_preserves_explicit_retrieval_role() -> None:
    assert _prepare_text("  零基础   可以参加吗？ ") == "query: 零基础 可以参加吗？"
    assert _prepare_text("passage: 企业资料") == "passage: 企业资料"
    assert _prepare_text("QUERY: existing") == "QUERY: existing"


def test_serialize_embeddings_validates_batch_shape_and_dimension() -> None:
    assert _serialize_embeddings([[0.1, 0.2]], expected_count=1, expected_dimension=2) == [
        [0.1, 0.2]
    ]
    with pytest.raises(RuntimeError, match="batch size"):
        _serialize_embeddings([], expected_count=1, expected_dimension=2)
    with pytest.raises(RuntimeError, match="invalid vector"):
        _serialize_embeddings([[0.1]], expected_count=1, expected_dimension=2)


@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
def test_serialize_embeddings_rejects_non_finite_values(non_finite: float) -> None:
    with pytest.raises(RuntimeError, match="invalid vector"):
        _serialize_embeddings(
            [[non_finite, 0.2]], expected_count=1, expected_dimension=2
        )


def test_health_endpoints_report_live_and_loading_without_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module.app.state, "model", None, raising=False)
    client = TestClient(app_module.app)
    try:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")
    finally:
        client.close()

    assert live_response.status_code == 200
    assert live_response.json() == {"data": {"status": "ok"}}
    assert ready_response.status_code == 503
    assert ready_response.json() == {"detail": "model is loading"}


def test_lifespan_loads_stub_model_and_ready_reports_metadata(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
) -> None:
    client, model, constructor_calls, cache_dir = service_client

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "status": "ready",
            "model": app_module.MODEL_NAME,
            "dimensions": app_module.MODEL_DIMENSION,
        }
    }
    assert app_module.app.state.model is model
    assert cache_dir.is_dir()
    assert len(constructor_calls) == 1
    assert constructor_calls[0]["model_name"] == app_module.MODEL_NAME
    assert constructor_calls[0]["cache_dir"] == str(cache_dir)
    assert constructor_calls[0]["providers"] == ["CPUExecutionProvider"]
    assert 1 <= constructor_calls[0]["threads"] <= 12


@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({}, "missing bearer token"),
        ({"Authorization": "Basic credentials"}, "missing bearer token"),
        (authorization("wrong-token"), "invalid bearer token"),
    ],
)
def test_embeddings_reject_missing_or_invalid_bearer_token(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
    headers: dict[str, str],
    detail: str,
) -> None:
    client, model, _, _ = service_client

    response = client.post("/v1/embeddings", json=valid_request(), headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": detail}
    assert model.calls == []


def test_embeddings_require_configured_service_credential(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, model, _, _ = service_client
    monkeypatch.delenv("EMBEDDING_API_KEY")

    response = client.post(
        "/v1/embeddings", json=valid_request(), headers=authorization()
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "embedding service credential is not configured"
    }
    assert model.calls == []


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (valid_request(model="unsupported/model"), "unsupported model"),
        (valid_request(dimensions=256), "unsupported dimensions"),
    ],
)
def test_embeddings_reject_unsupported_model_or_dimension(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
    payload: dict[str, Any],
    detail: str,
) -> None:
    client, model, _, _ = service_client

    response = client.post(
        "/v1/embeddings", json=payload, headers=authorization()
    )

    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    assert model.calls == []


def test_embeddings_returns_openai_compatible_response(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
) -> None:
    client, model, _, _ = service_client
    raw_inputs = ["  公司   简介  ", "passage: 产品资料"]
    first_vector = [0.25] + [0.0] * (app_module.MODEL_DIMENSION - 1)
    second_vector = [-0.5] + [0.0] * (app_module.MODEL_DIMENSION - 1)
    model.vectors = [first_vector, second_vector]

    response = client.post(
        "/v1/embeddings",
        json=valid_request(input=raw_inputs, dimensions=app_module.MODEL_DIMENSION),
        headers=authorization(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["model"] == app_module.MODEL_NAME
    assert body["data"] == [
        {"object": "embedding", "embedding": first_vector, "index": 0},
        {"object": "embedding", "embedding": second_vector, "index": 1},
    ]
    expected_tokens = sum(max(1, len(text) // 2) for text in raw_inputs)
    assert body["usage"] == {
        "prompt_tokens": expected_tokens,
        "total_tokens": expected_tokens,
    }
    assert all(
        math.isfinite(value)
        for item in body["data"]
        for value in item["embedding"]
    )
    assert model.calls == [
        (["query: 公司 简介", "passage: 产品资料"], 2)
    ]


@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
def test_embeddings_rejects_non_finite_model_output(
    service_client: tuple[TestClient, StubTextEmbedding, list[dict[str, Any]], Path],
    non_finite: float,
) -> None:
    client, model, _, _ = service_client
    model.vectors = [
        [non_finite] + [0.0] * (app_module.MODEL_DIMENSION - 1)
    ]

    with pytest.raises(RuntimeError, match="invalid vector"):
        client.post(
            "/v1/embeddings", json=valid_request(), headers=authorization()
        )

from __future__ import annotations

import asyncio
import hmac
import math
import os
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastembed import TextEmbedding
from pydantic import BaseModel, Field, field_validator


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
MODEL_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
MODEL_NATIVE_DIMENSION = int(
    os.getenv("EMBEDDING_NATIVE_DIMENSION", str(MODEL_DIMENSION))
)
MODEL_CACHE = Path(
    os.getenv(
        "FASTEMBED_CACHE_PATH",
        str(Path(os.getenv("LOCALAPPDATA", Path.home())) / "cf-ai-card-runtime" / "models"),
    )
)
MAX_BATCH_SIZE = 64
MAX_INPUT_CHARS = 20_000
MAX_EMBEDDING_THREADS = 12


def _embedding_thread_count() -> int:
    """Choose a bounded CPU thread count, allowing deployment overrides."""

    configured = os.getenv("EMBEDDING_THREADS")
    if configured:
        try:
            requested = int(configured)
        except ValueError as exc:
            raise RuntimeError("EMBEDDING_THREADS must be an integer") from exc
        return max(1, min(requested, MAX_EMBEDDING_THREADS))
    return max(1, min(os.cpu_count() or 4, MAX_EMBEDDING_THREADS))


def _uses_e5_retrieval_prefix() -> bool:
    return MODEL_NAME.casefold().startswith("intfloat/multilingual-e5")


class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]
    dimensions: int | None = None
    encoding_format: Literal["float"] = "float"

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str | list[str]) -> str | list[str]:
        values = [value] if isinstance(value, str) else value
        if not values or len(values) > MAX_BATCH_SIZE:
            raise ValueError(f"input must contain between 1 and {MAX_BATCH_SIZE} texts")
        if any(not item.strip() or len(item) > MAX_INPUT_CHARS for item in values):
            raise ValueError("embedding input is empty or too long")
        return value


class EmbeddingData(BaseModel):
    object: Literal["embedding"] = "embedding"
    embedding: list[float]
    index: int


class Usage(BaseModel):
    prompt_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingData]
    model: str
    usage: Usage


def _prepare_text(value: str) -> str:
    normalized = " ".join(value.split())
    lowered = normalized.casefold()
    if not _uses_e5_retrieval_prefix():
        if lowered.startswith("query: "):
            return normalized[len("query: ") :].strip()
        if lowered.startswith("passage: "):
            return normalized[len("passage: ") :].strip()
        return normalized
    if lowered.startswith("query: ") or lowered.startswith("passage: "):
        return normalized
    # Online API calls are queries.  The indexing command sends an explicit
    # ``passage:`` prefix so E5 receives the correct asymmetric retrieval role.
    return f"query: {normalized}"


def _serialize_embeddings(
    vectors: Sequence[Sequence[float]],
    *,
    expected_count: int,
    expected_dimension: int,
    native_dimension: int | None = None,
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise RuntimeError("embedding model returned the wrong batch size")
    source_dimension = native_dimension or expected_dimension
    if source_dimension <= 0 or source_dimension > expected_dimension:
        raise RuntimeError("embedding dimensions are invalid")
    serialized: list[list[float]] = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if len(values) != source_dimension or any(not math.isfinite(value) for value in values):
            raise RuntimeError("embedding model returned an invalid vector")
        if source_dimension < expected_dimension:
            values.extend([0.0] * (expected_dimension - source_dimension))
        serialized.append(values)
    return serialized


def _require_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("EMBEDDING_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="embedding service credential is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid bearer token")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    threads = _embedding_thread_count()
    model = await asyncio.to_thread(
        TextEmbedding,
        model_name=MODEL_NAME,
        cache_dir=str(MODEL_CACHE),
        threads=threads,
        providers=["CPUExecutionProvider"],
    )
    app.state.model = model
    app.state.loaded_at = time.time()
    yield
    app.state.model = None


app = FastAPI(
    title="CF AI Card Local Embedding Service",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health/live")
async def live() -> dict[str, object]:
    return {"data": {"status": "ok"}}


@app.get("/health/ready")
async def ready() -> dict[str, object]:
    if getattr(app.state, "model", None) is None:
        raise HTTPException(status_code=503, detail="model is loading")
    return {
        "data": {
            "status": "ready",
            "model": MODEL_NAME,
            "dimensions": MODEL_DIMENSION,
        }
    }


@app.post(
    "/v1/embeddings",
    response_model=EmbeddingResponse,
    dependencies=[Depends(_require_api_key)],
)
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    if request.model != MODEL_NAME:
        raise HTTPException(status_code=400, detail="unsupported model")
    if request.dimensions is not None and request.dimensions != MODEL_DIMENSION:
        raise HTTPException(status_code=400, detail="unsupported dimensions")

    raw_inputs = [request.input] if isinstance(request.input, str) else request.input
    inputs = [_prepare_text(item) for item in raw_inputs]
    model: TextEmbedding = app.state.model

    def embed() -> list[Sequence[float]]:
        return list(model.embed(inputs, batch_size=min(len(inputs), 16)))

    vectors = await asyncio.to_thread(embed)
    serialized = _serialize_embeddings(
        vectors,
        expected_count=len(inputs),
        expected_dimension=MODEL_DIMENSION,
        native_dimension=MODEL_NATIVE_DIMENSION,
    )
    token_estimate = sum(max(1, len(text) // 2) for text in raw_inputs)
    return EmbeddingResponse(
        data=[
            EmbeddingData(index=index, embedding=vector)
            for index, vector in enumerate(serialized)
        ],
        model=MODEL_NAME,
        usage=Usage(prompt_tokens=token_estimate, total_tokens=token_estimate),
    )

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeOpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FaqWriteRequest(KnowledgeOpsModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=20_000)
    visibility: Literal["public", "authenticated", "internal"] = "public"

    @field_validator("question", "answer")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class FaqRecord(KnowledgeOpsModel):
    id: uuid.UUID
    source_id: str
    question: str
    answer: str | None = None
    visibility: str | None = None
    status: str
    version: int = Field(ge=1)
    current_version_id: uuid.UUID | None = None
    editable_version_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class FaqEnvelope(KnowledgeOpsModel):
    data: FaqRecord


class FaqListEnvelope(KnowledgeOpsModel):
    data: list[FaqRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class KnowledgeVersionRecord(KnowledgeOpsModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int = Field(ge=1)
    review_status: str
    visibility: str
    chunk_count: int = Field(ge=0)
    indexed_chunk_count: int = Field(ge=0)
    content_hash: str
    published_at: datetime | None = None
    created_at: datetime


class KnowledgeVersionListEnvelope(KnowledgeOpsModel):
    data: list[KnowledgeVersionRecord]
    total: int = Field(ge=0)


class KnowledgeIndexJobRecord(KnowledgeOpsModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    version_id: uuid.UUID
    embedding_model: str
    status: str
    attempt: int = Field(ge=0)
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeIndexJobEnvelope(KnowledgeOpsModel):
    data: KnowledgeIndexJobRecord


class KnowledgeIndexJobListEnvelope(KnowledgeOpsModel):
    data: list[KnowledgeIndexJobRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class KnowledgeChunkRecord(KnowledgeOpsModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    ordinal: int = Field(ge=0)
    title: str
    text_preview: str
    visibility: str
    is_active: bool
    embedding_model: str | None = None
    source_type: str
    source_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunkListEnvelope(KnowledgeOpsModel):
    data: list[KnowledgeChunkRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class EvaluationJob(KnowledgeOpsModel):
    id: uuid.UUID
    status: Literal["pending"] = "pending"
    created_at: datetime


class EvaluationJobEnvelope(KnowledgeOpsModel):
    data: EvaluationJob


__all__ = [name for name in globals() if not name.startswith("_")]

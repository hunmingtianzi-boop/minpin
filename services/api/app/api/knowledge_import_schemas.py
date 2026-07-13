from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KnowledgeImportItemRecord(ImportModel):
    id: uuid.UUID
    file_name: str
    source_type: str
    status: str
    auto_publish: bool = False
    parse_status: str = "pending"
    publish_status: str | None = None
    row_number: int | None = None
    document_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    published_at: datetime | None = None


class KnowledgeImportBatchRecord(ImportModel):
    id: uuid.UUID
    status: str
    auto_publish: bool = False
    total_items: int = Field(ge=1)
    pending_items: int = Field(ge=0)
    succeeded_items: int = Field(ge=0)
    failed_items: int = Field(ge=0)
    created_at: datetime
    completed_at: datetime | None = None
    items: list[KnowledgeImportItemRecord] = Field(default_factory=list)


class KnowledgeImportBatchEnvelope(ImportModel):
    data: KnowledgeImportBatchRecord


class KnowledgeImportBatchListEnvelope(ImportModel):
    data: list[KnowledgeImportBatchRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


__all__ = [
    "KnowledgeImportBatchEnvelope",
    "KnowledgeImportBatchListEnvelope",
    "KnowledgeImportBatchRecord",
    "KnowledgeImportItemRecord",
]

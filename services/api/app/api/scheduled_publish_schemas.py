from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScheduledPublishModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SchedulePublishRequest(ScheduledPublishModel):
    scheduled_at: datetime
    version_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def require_timezone(self) -> "SchedulePublishRequest":
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone")
        return self


class ScheduledPublishJobRecord(ScheduledPublishModel):
    id: uuid.UUID
    resource_type: Literal["product", "case_study", "knowledge_document"]
    resource_id: uuid.UUID
    target_version: int = Field(ge=1)
    knowledge_version_id: uuid.UUID | None = None
    scheduled_by: uuid.UUID
    scheduled_at: datetime
    status: Literal["pending", "processing", "completed", "cancelled", "failed", "dead_letter"]
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    next_attempt_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    error_code: str | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ScheduledPublishJobEnvelope(ScheduledPublishModel):
    data: ScheduledPublishJobRecord


class ScheduledPublishJobListEnvelope(ScheduledPublishModel):
    data: list[ScheduledPublishJobRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


__all__ = [
    "SchedulePublishRequest",
    "ScheduledPublishJobEnvelope",
    "ScheduledPublishJobListEnvelope",
    "ScheduledPublishJobRecord",
]

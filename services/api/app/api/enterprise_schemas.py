from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.catalog_schemas import validate_safe_asset_url

ResourceType = Literal["product", "case_study", "knowledge_document"]
OverrideMode = Literal["inherit", "hidden", "custom"]


class EnterpriseStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DistributionWriteRequest(EnterpriseStrictModel):
    is_default_visible: bool


class DistributionRecord(EnterpriseStrictModel):
    id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    is_default_visible: bool
    # zero is the synthetic "inherit company default" version; PUT with
    # If-Match: 0 materializes an explicit company policy.
    version: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class DistributionEnvelope(EnterpriseStrictModel):
    data: DistributionRecord


class CustomDisplay(EnterpriseStrictModel):
    """Presentation-only fields; source content and access policy stay immutable."""

    title: str | None = Field(default=None, min_length=1, max_length=240)
    summary: str | None = Field(default=None, min_length=1, max_length=5_000)
    image_url: str | None = Field(default=None, max_length=2_048)
    sort_order: int | None = Field(default=None, ge=0, le=1_000_000)

    _safe_image = field_validator("image_url")(validate_safe_asset_url)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class OverrideWriteRequest(EnterpriseStrictModel):
    mode: OverrideMode
    custom_display: CustomDisplay | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> "OverrideWriteRequest":
        if self.mode == "custom" and not self.custom_display:
            raise ValueError("custom mode requires custom_display")
        if self.mode != "custom" and self.custom_display is not None:
            raise ValueError("custom_display is only allowed in custom mode")
        return self


class OverrideRecord(EnterpriseStrictModel):
    id: uuid.UUID
    card_id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    mode: OverrideMode
    custom_display: dict[str, Any] = Field(default_factory=dict)
    source_version: int = Field(ge=1)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class OverrideEnvelope(EnterpriseStrictModel):
    data: OverrideRecord


class OverrideListEnvelope(EnterpriseStrictModel):
    data: list[OverrideRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class OverrideRevisionRecord(EnterpriseStrictModel):
    version: int = Field(ge=1)
    mode: OverrideMode
    custom_display: dict[str, Any] = Field(default_factory=dict)
    source_version: int = Field(ge=1)
    created_at: datetime


class OverrideRevisionListEnvelope(EnterpriseStrictModel):
    data: list[OverrideRevisionRecord]


class RollbackOverrideRequest(EnterpriseStrictModel):
    revision_version: int = Field(ge=1)


class RecommendationEvidence(EnterpriseStrictModel):
    source_type: ResourceType
    source_id: uuid.UUID
    source_version: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(min_length=1, max_length=500)


class PublicRecommendation(EnterpriseStrictModel):
    resource_type: ResourceType
    resource_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=1_000)
    url: str = Field(min_length=1, max_length=2_048)
    reason_code: Literal["recently_published", "card_featured", "context_match"]
    reason: str = Field(min_length=1, max_length=200)
    evidence: RecommendationEvidence


class PublicRecommendationEnvelope(EnterpriseStrictModel):
    data: list[PublicRecommendation]

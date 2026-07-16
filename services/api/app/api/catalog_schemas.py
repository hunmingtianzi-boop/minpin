from __future__ import annotations

import ipaddress
import json
import uuid
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContentStatusValue = Literal["draft", "review_pending", "published", "archived"]
CardKindValue = Literal["enterprise", "employee"]
VisibilityValue = Literal["public", "authenticated", "internal"]
ForbiddenAction = Literal["refuse", "handoff", "safe_template"]


class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_safe_asset_url(value: str | None) -> str | None:
    """Allow first-party paths or public HTTPS assets, never local/private destinations."""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if any(ord(character) < 32 for character in candidate) or "\\" in candidate:
        raise ValueError("asset URL contains unsafe characters")
    if candidate.startswith("/"):
        if candidate.startswith("//"):
            raise ValueError("protocol-relative asset URLs are not allowed")
        return candidate

    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("remote asset URLs must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("asset URLs must not contain credentials")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local asset hosts are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("private or reserved asset addresses are not allowed")
    return candidate


def validate_json_settings(value: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("settings must contain JSON-compatible values") from exc
    if len(encoded.encode("utf-8")) > 32_768:
        raise ValueError("settings must not exceed 32 KiB")
    return value


class ProductWriteFields(CatalogStrictModel):
    slug: str = Field(
        min_length=3,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$",
    )
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    summary: str = Field(min_length=1, max_length=5_000)
    detail: str = Field(min_length=1, max_length=100_000)
    audience: str | None = Field(default=None, max_length=5_000)
    price_boundary: str | None = Field(default=None, max_length=2_000)
    image_url: str | None = Field(default=None, max_length=2_048)
    visibility: VisibilityValue = "public"
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    _validate_image_url = field_validator("image_url")(validate_safe_asset_url)
    _validate_settings = field_validator("settings")(validate_json_settings)


class CreateProductRequest(ProductWriteFields):
    pass


class UpdateProductRequest(ProductWriteFields):
    pass


class ProductRecord(ProductWriteFields):
    id: uuid.UUID
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ProductEnvelope(CatalogStrictModel):
    data: ProductRecord


class ProductListEnvelope(CatalogStrictModel):
    data: list[ProductRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PublicProductRecord(CatalogStrictModel):
    slug: str
    name: str
    category: str | None = None
    summary: str
    detail: str
    audience: str | None = None
    price_boundary: str | None = None
    image_url: str | None = None
    sort_order: int = Field(ge=0)
    published_at: datetime


class PublicProductEnvelope(CatalogStrictModel):
    data: PublicProductRecord


class PublicProductListEnvelope(CatalogStrictModel):
    data: list[PublicProductRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CaseStudyWriteFields(CatalogStrictModel):
    slug: str = Field(
        min_length=3,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$",
    )
    title: str = Field(min_length=1, max_length=240)
    industry: str | None = Field(default=None, max_length=120)
    background: str = Field(min_length=1, max_length=50_000)
    solution: str = Field(min_length=1, max_length=50_000)
    result: str = Field(min_length=1, max_length=50_000)
    client_display_name: str | None = Field(default=None, max_length=200)
    image_url: str | None = Field(default=None, max_length=2_048)
    visibility: VisibilityValue = "public"
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    _validate_image_url = field_validator("image_url")(validate_safe_asset_url)
    _validate_settings = field_validator("settings")(validate_json_settings)


class CreateCaseStudyRequest(CaseStudyWriteFields):
    pass


class UpdateCaseStudyRequest(CaseStudyWriteFields):
    pass


class CaseStudyRecord(CaseStudyWriteFields):
    id: uuid.UUID
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class CaseStudyEnvelope(CatalogStrictModel):
    data: CaseStudyRecord


class CaseStudyListEnvelope(CatalogStrictModel):
    data: list[CaseStudyRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PublicCaseStudyRecord(CatalogStrictModel):
    slug: str
    title: str
    industry: str | None = None
    background: str
    solution: str
    result: str
    client_display_name: str | None = None
    image_url: str | None = None
    sort_order: int = Field(ge=0)
    published_at: datetime


class PublicCaseStudyEnvelope(CatalogStrictModel):
    data: PublicCaseStudyRecord


class PublicCaseStudyListEnvelope(CatalogStrictModel):
    data: list[PublicCaseStudyRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ForbiddenTopicWriteFields(CatalogStrictModel):
    topic: str = Field(min_length=1, max_length=240)
    match_terms: list[str] = Field(default_factory=list, max_length=64)
    action: ForbiddenAction = "refuse"
    safe_response: str | None = Field(default=None, max_length=5_000)

    @field_validator("match_terms")
    @classmethod
    def normalize_match_terms(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = value.strip()
            if not term or len(term) > 160:
                raise ValueError("match terms must contain 1-160 characters")
            key = term.casefold()
            if key not in seen:
                normalized.append(term)
                seen.add(key)
        return normalized

    @model_validator(mode="after")
    def require_safe_template(self) -> Self:
        if self.action == "safe_template" and not self.safe_response:
            raise ValueError("safe_response is required for safe_template")
        return self


class CreateForbiddenTopicRequest(ForbiddenTopicWriteFields):
    is_active: bool = True


class UpdateForbiddenTopicRequest(ForbiddenTopicWriteFields):
    pass


class ForbiddenTopicRecord(ForbiddenTopicWriteFields):
    id: uuid.UUID
    is_active: bool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ForbiddenTopicEnvelope(CatalogStrictModel):
    data: ForbiddenTopicRecord


class ForbiddenTopicListEnvelope(CatalogStrictModel):
    data: list[ForbiddenTopicRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CardWriteFields(CatalogStrictModel):
    display_name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_048)
    assistant_name: str | None = Field(default=None, max_length=120)
    welcome_message: str | None = Field(default=None, max_length=2_000)
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    policy_versions: dict[str, str] = Field(default_factory=dict)

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)

    @field_validator("suggested_questions")
    @classmethod
    def validate_suggested_questions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("suggested questions must contain 1-200 characters")
        return [value.strip() for value in values]

    @field_validator("policy_versions")
    @classmethod
    def validate_policy_versions(cls, values: dict[str, str]) -> dict[str, str]:
        allowed = {
            "privacy",
            "chat_notice",
            "lead_consent",
            "profile_personalization",
        }
        if set(values) - allowed:
            raise ValueError("unsupported policy version key")
        if any(not value.strip() or len(value) > 64 for value in values.values()):
            raise ValueError("policy versions must contain 1-64 characters")
        return {key: value.strip() for key, value in values.items()}


class CreateCardRequest(CardWriteFields):
    card_kind: CardKindValue = "employee"
    owner_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_card_identity(self) -> Self:
        if self.card_kind == "enterprise" and self.owner_user_id is not None:
            raise ValueError("enterprise cards must not have an employee owner")
        return self


class UpdateManagedCardRequest(CardWriteFields):
    card_kind: CardKindValue
    owner_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_card_identity(self) -> Self:
        if self.card_kind == "enterprise" and self.owner_user_id is not None:
            raise ValueError("enterprise cards must not have an employee owner")
        if self.card_kind == "employee" and self.owner_user_id is None:
            raise ValueError("employee cards require an owner")
        return self


class ManagedCardRecord(CardWriteFields):
    id: uuid.UUID
    card_kind: CardKindValue
    owner_user_id: uuid.UUID | None = None
    slug: str
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    share_url: str
    qr_url: str = Field(description="The public URL that should be encoded into a QR code")
    created_at: datetime
    updated_at: datetime


class ManagedCardEnvelope(CatalogStrictModel):
    data: ManagedCardRecord


class ManagedCardListEnvelope(CatalogStrictModel):
    data: list[ManagedCardRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


__all__ = [
    "CaseStudyEnvelope",
    "CaseStudyListEnvelope",
    "CaseStudyRecord",
    "CreateCardRequest",
    "CreateCaseStudyRequest",
    "CreateForbiddenTopicRequest",
    "CreateProductRequest",
    "ForbiddenTopicEnvelope",
    "ForbiddenTopicListEnvelope",
    "ForbiddenTopicRecord",
    "ManagedCardEnvelope",
    "ManagedCardListEnvelope",
    "ManagedCardRecord",
    "ProductEnvelope",
    "ProductListEnvelope",
    "ProductRecord",
    "PublicCaseStudyEnvelope",
    "PublicCaseStudyListEnvelope",
    "PublicCaseStudyRecord",
    "PublicProductEnvelope",
    "PublicProductListEnvelope",
    "PublicProductRecord",
    "UpdateCaseStudyRequest",
    "UpdateForbiddenTopicRequest",
    "UpdateManagedCardRequest",
    "UpdateProductRequest",
    "validate_safe_asset_url",
]

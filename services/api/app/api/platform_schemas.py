from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateEnterpriseRequest(PlatformModel):
    tenant_slug: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$",
    )
    tenant_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    admin_account: str = Field(min_length=3, max_length=200)
    admin_display_name: str = Field(min_length=1, max_length=120)
    admin_password: SecretStr
    initial_card_title: str | None = Field(default=None, max_length=200)

    @field_validator("admin_account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("admin_account must not contain whitespace")
        return value.casefold()

    @field_validator("admin_password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        if not 12 <= len(value.get_secret_value()) <= 200:
            raise ValueError("admin_password must contain 12-200 characters")
        return value


class EnterpriseRecord(PlatformModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    company_id: uuid.UUID
    company_name: str
    company_status: str
    admin_user_id: uuid.UUID
    admin_membership_id: uuid.UUID
    initial_card_id: uuid.UUID
    initial_card_slug: str
    created_at: datetime


class EnterpriseEnvelope(PlatformModel):
    data: EnterpriseRecord


class EnterpriseListItem(PlatformModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    company_id: uuid.UUID
    company_name: str
    status: str
    created_at: datetime


class EnterpriseListEnvelope(PlatformModel):
    data: list[EnterpriseListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


__all__ = [
    "CreateEnterpriseRequest",
    "EnterpriseEnvelope",
    "EnterpriseListEnvelope",
    "EnterpriseListItem",
    "EnterpriseRecord",
]

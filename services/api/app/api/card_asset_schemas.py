from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CardAssetStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CardAssetRecord(CardAssetStrictModel):
    url: str = Field(min_length=1, max_length=2_048)
    content_type: str = "image/webp"
    width: int = Field(ge=1, le=8_192)
    height: int = Field(ge=1, le=8_192)
    size_bytes: int = Field(ge=1, le=5 * 1024 * 1024)


class CardAssetEnvelope(CardAssetStrictModel):
    data: CardAssetRecord


__all__ = ["CardAssetEnvelope", "CardAssetRecord"]

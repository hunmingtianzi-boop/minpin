from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateVisitRequest(StrictModel):
    source: str = Field(min_length=1, max_length=64)
    campaign: str | None = Field(default=None, max_length=128)
    privacy_notice_version: str = Field(min_length=1, max_length=64)


class VisitSession(StrictModel):
    visit_id: uuid.UUID
    visitor_session_token: str
    expires_at: datetime


class VisitEnvelope(StrictModel):
    data: VisitSession


class PublicCompany(StrictModel):
    id: uuid.UUID
    name: str
    summary: str
    industry: str | None = None
    logo_url: str | None = None


class AiAssistantPublicConfig(StrictModel):
    available: bool
    display_name: str
    disclosure: str
    welcome_message: str
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)


class PolicyVersions(StrictModel):
    privacy: str
    chat_notice: str
    lead_consent: str


class PublicCard(StrictModel):
    id: uuid.UUID
    slug: str
    display_name: str
    title: str
    avatar_url: str | None = None
    contact_fields: list[dict[str, str]] = Field(default_factory=list)
    company: PublicCompany
    featured_products: list[dict[str, Any]] = Field(default_factory=list)
    featured_cases: list[dict[str, Any]] = Field(default_factory=list)
    ai_assistant: AiAssistantPublicConfig
    policy_versions: PolicyVersions


class PublicCardEnvelope(StrictModel):
    data: PublicCard


class ConsentRequest(StrictModel):
    scope: Literal["chat_notice", "lead_contact"]
    policy_version: str = Field(min_length=1, max_length=64)
    granted: Literal[True]


class ConsentRecord(StrictModel):
    id: uuid.UUID
    scope: Literal["chat_notice", "lead_contact"]
    policy_version: str
    granted_at: datetime


class ConsentEnvelope(StrictModel):
    data: ConsentRecord


class CreateConversationRequest(StrictModel):
    chat_notice_version: str = Field(min_length=1, max_length=64)


class ConversationRecord(StrictModel):
    id: uuid.UUID
    status: Literal["active", "closed", "expired", "blocked"]
    created_at: datetime


class ConversationEnvelope(StrictModel):
    data: ConversationRecord


class CreateMessageRequest(StrictModel):
    content: str = Field(min_length=1, max_length=2_000)


class MessageStarted(StrictModel):
    message_id: uuid.UUID
    request_id: str


class MessageDelta(StrictModel):
    text: str


class MessageCitation(StrictModel):
    citation_id: uuid.UUID
    label: str
    source_type: str


class MessageCompleted(StrictModel):
    message_id: uuid.UUID
    finish_reason: Literal["stop", "refusal", "length", "content_filter"]
    lead_prompt: bool = False


class MessageError(StrictModel):
    code: str
    retryable: bool
    request_id: str

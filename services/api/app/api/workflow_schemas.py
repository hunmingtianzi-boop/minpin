from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DailyMetric(WorkflowModel):
    day: str
    visits: int = Field(ge=0)
    conversations: int = Field(ge=0)
    leads: int = Field(ge=0)


class DashboardOverview(WorkflowModel):
    generated_at: datetime
    period_days: int = Field(ge=1, le=365)
    visits: int = Field(ge=0)
    unique_visitors: int = Field(ge=0)
    conversations: int = Field(ge=0)
    ai_answers: int = Field(ge=0)
    new_leads: int = Field(ge=0)
    pending_gaps: int = Field(ge=0)
    unread_notifications: int = Field(ge=0)
    conversation_rate: float = Field(ge=0, le=1)
    lead_rate: float = Field(ge=0, le=1)
    daily: list[DailyMetric] = Field(default_factory=list)


class DashboardEnvelope(WorkflowModel):
    data: DashboardOverview


class VisitItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    source: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    conversation_count: int = Field(ge=0)


class VisitListEnvelope(WorkflowModel):
    data: list[VisitItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ConversationItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    visit_id: uuid.UUID | None = None
    status: str
    primary_intent: str | None = None
    risk_level: str
    started_at: datetime
    last_activity_at: datetime
    message_count: int = Field(ge=0)
    has_current_summary: bool


class ConversationListEnvelope(WorkflowModel):
    data: list[ConversationItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class CitationView(WorkflowModel):
    id: uuid.UUID
    chunk_id: uuid.UUID
    rank: int = Field(ge=1)
    score: float
    title: str
    source_type: str
    source_id: str
    snapshot_text: str


class AiRunView(WorkflowModel):
    provider: str
    model: str
    status: str
    first_token_latency_ms: int | None = Field(default=None, ge=0)
    total_latency_ms: int = Field(ge=0)
    retrieval_result: dict[str, Any] = Field(default_factory=dict)
    safety_result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class MessageView(WorkflowModel):
    id: uuid.UUID
    role: str
    content: str
    status: str
    content_redacted: bool
    created_at: datetime
    citations: list[CitationView] = Field(default_factory=list)
    ai_run: AiRunView | None = None


class SummaryView(WorkflowModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    summary: str
    interests: list[str] = Field(default_factory=list)
    strength: str | None = None
    next_step: str | None = None
    risk_notes: str | None = None
    source_message_ids: list[uuid.UUID]
    is_current: bool
    stale_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationItem):
    messages: list[MessageView]
    current_summary: SummaryView | None = None


class ConversationDetailEnvelope(WorkflowModel):
    data: ConversationDetail


class SummaryEnvelope(WorkflowModel):
    data: SummaryView


class SummaryDraft(WorkflowModel):
    summary: str = Field(min_length=1, max_length=4_000)
    interests: list[str] = Field(default_factory=list, max_length=12)
    strength: Literal["low", "medium", "high", "unknown"] = "unknown"
    next_step: str | None = Field(default=None, max_length=2_000)
    risk_notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 160 for item in cleaned):
            raise ValueError("interest tags must not exceed 160 characters")
        return cleaned[:12]


class KnowledgeGapView(WorkflowModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    reason: str
    status: str
    suggested_answer: str | None = None
    occurrence_count: int = Field(ge=1)
    last_seen_at: datetime
    approved_version_id: uuid.UUID | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KnowledgeGapListEnvelope(WorkflowModel):
    data: list[KnowledgeGapView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UpdateKnowledgeGapRequest(WorkflowModel):
    suggested_answer: str = Field(min_length=1, max_length=20_000)

    @field_validator("suggested_answer")
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suggested_answer must not be blank")
        return value


class KnowledgeGapEnvelope(WorkflowModel):
    data: KnowledgeGapView


class NotificationView(WorkflowModel):
    id: uuid.UUID
    notification_type: str
    title: str
    body: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListEnvelope(WorkflowModel):
    data: list[NotificationView]
    total: int = Field(ge=0)
    unread: int = Field(ge=0)


class NotificationEnvelope(WorkflowModel):
    data: NotificationView


class VisitEventRequest(WorkflowModel):
    event_id: uuid.UUID
    event_type: Literal[
        "page_view",
        "content_view",
        "heartbeat",
        "leave",
        "cta_click",
        "share",
    ]
    object_type: Literal["card", "product", "case", "faq", "contact", "ai"] | None = None
    object_id: str | None = Field(default=None, max_length=160)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: dict[str, str | int | float | bool | None]):
        if len(value) > 12:
            raise ValueError("metadata supports at most 12 fields")
        if any(len(str(key)) > 64 or len(str(item)) > 500 for key, item in value.items()):
            raise ValueError("metadata field is too long")
        return value


class VisitEventView(WorkflowModel):
    id: uuid.UUID
    event_type: str
    occurred_at: datetime


class VisitEventEnvelope(WorkflowModel):
    data: VisitEventView


class LeadCaptureRequest(WorkflowModel):
    conversation_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    mobile: str | None = Field(default=None, min_length=5, max_length=40)
    email: str | None = Field(default=None, min_length=5, max_length=254)
    wechat: str | None = Field(default=None, min_length=2, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    demand: str = Field(min_length=1, max_length=4_000)
    interest_tags: list[str] = Field(default_factory=list, max_length=12)
    consent_policy_version: str = Field(min_length=1, max_length=64)
    consent_granted: Literal[True]

    @model_validator(mode="after")
    def require_contact_and_clean_tags(self) -> "LeadCaptureRequest":
        if not any((self.mobile, self.email, self.wechat)):
            raise ValueError("mobile, email or wechat is required")
        self.interest_tags = list(
            dict.fromkeys(item.strip() for item in self.interest_tags if item.strip())
        )
        if any(len(item) > 160 for item in self.interest_tags):
            raise ValueError("interest tag is too long")
        return self


class LeadCreated(WorkflowModel):
    id: uuid.UUID
    status: str
    created_at: datetime


class LeadCreatedEnvelope(WorkflowModel):
    data: LeadCreated


class LeadListItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID
    status: str
    priority: str
    masked_name: str
    masked_contact: str
    company_name: str | None = None
    interest_tags: list[str] = Field(default_factory=list)
    viewed_at: datetime | None = None
    closed_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class LeadListEnvelope(WorkflowModel):
    data: list[LeadListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class LeadFollowupView(WorkflowModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    followup_type: str
    content: str
    next_at: datetime | None = None
    created_at: datetime


class LeadDetail(LeadListItem):
    name: str
    mobile: str | None = None
    email: str | None = None
    wechat: str | None = None
    demand: str
    followups: list[LeadFollowupView] = Field(default_factory=list)


class LeadDetailEnvelope(WorkflowModel):
    data: LeadDetail


class UpdateLeadRequest(WorkflowModel):
    status: Literal["new", "viewed", "following", "won", "lost", "invalid"]
    priority: Literal["low", "medium", "high"]


class CreateLeadFollowupRequest(WorkflowModel):
    followup_type: Literal["note", "call", "message", "meeting", "status_change"]
    content: str = Field(min_length=1, max_length=10_000)
    next_at: datetime | None = None


class LeadFollowupEnvelope(WorkflowModel):
    data: LeadFollowupView


class PrivacyRequestCreate(WorkflowModel):
    request_type: Literal["access", "correction", "deletion", "withdraw_consent"]
    note: str | None = Field(default=None, max_length=4_000)
    consent_scope: Literal["chat_notice", "lead_contact"] | None = None

    @model_validator(mode="after")
    def validate_withdrawal_scope(self) -> "PrivacyRequestCreate":
        if self.request_type == "withdraw_consent" and self.consent_scope is None:
            raise ValueError("consent_scope is required when withdrawing consent")
        if self.request_type != "withdraw_consent" and self.consent_scope is not None:
            raise ValueError("consent_scope only applies to consent withdrawal")
        return self


class PrivacyRequestView(WorkflowModel):
    id: uuid.UUID
    visitor_id: uuid.UUID
    request_type: str
    status: str
    verification_method: str | None = None
    handled_by: uuid.UUID | None = None
    completed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PrivacyRequestEnvelope(WorkflowModel):
    data: PrivacyRequestView


class PrivacyRequestListEnvelope(WorkflowModel):
    data: list[PrivacyRequestView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UpdatePrivacyRequest(WorkflowModel):
    status: Literal["pending", "verified", "in_progress", "completed", "rejected"]
    verification_method: str | None = Field(default=None, max_length=80)


__all__ = [name for name in globals() if not name.startswith("_")]

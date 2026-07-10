from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    CompanyScopeMixin,
    OptimisticVersionMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

EMBEDDING_DIMENSION = 1024


def db_enum(enum_type: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class TenantType(StrEnum):
    CHAMBER = "chamber"
    ENTERPRISE = "enterprise"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_PENDING = "review_pending"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MembershipRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    COMPANY_ADMIN = "company_admin"
    CARD_OWNER = "card_owner"


class Visibility(StrEnum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    INTERNAL = "internal"


class ConsentScope(StrEnum):
    BROWSE_NOTICE = "browse_notice"
    CHAT_NOTICE = "chat_notice"
    LEAD_CONTACT = "lead_contact"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    HUMAN = "human"


class MessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REFUSED = "refused"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class IndexJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class KnowledgeGapStatus(StrEnum):
    PENDING = "pending"
    DRAFTED = "drafted"
    APPROVED = "approved"
    INDEXING = "indexing"
    INDEXED = "indexed"
    REJECTED = "rejected"
    FAILED = "failed"


class PromptStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_type: Mapped[TenantType] = mapped_column(
        "type",
        db_enum(TenantType, "tenant_type"),
        nullable=False,
    )
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "tenant_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Company(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticVersionMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "id", name="uq_companies_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "normalized_name",
            name="uq_companies_tenant_id_normalized_name",
        ),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        Index("ix_companies_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "company_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticVersionMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_hmac", "email_hmac", unique=True),
        Index("uq_users_mobile_hmac", "mobile_hmac", unique=True),
    )

    email_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mobile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "user_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_memberships_user_scope",
            "user_id",
            "tenant_id",
            "company_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_memberships_scope_status", "tenant_id", "company_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    role: Mapped[MembershipRole] = mapped_column(
        db_enum(MembershipRole, "membership_role"),
        nullable=False,
    )
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "membership_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Card(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "cards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("slug", name="uq_cards_slug"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_cards_scope_id"),
        CheckConstraint("slug = btrim(slug)", name="slug_trimmed"),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'",
            name="slug_public_format",
        ),
        Index("ix_cards_company_status_updated", "company_id", "status", "updated_at"),
        Index(
            "ix_cards_public_slug",
            "slug",
            postgresql_where=text("status = 'published' AND deleted_at IS NULL"),
        ),
    )

    owner_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "card_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Visitor(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_visitors_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "anonymous_hash",
            name="uq_visitors_scope_anonymous_hash",
        ),
        CheckConstraint("char_length(anonymous_hash) = 64", name="anonymous_hash_sha256"),
        Index("ix_visitors_company_last_seen", "company_id", "last_seen_at"),
    )

    anonymous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VisitorProfile(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitor_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("visitor_id", name="uq_visitor_profiles_visitor_id"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class ConsentRecord(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        Index("ix_consent_records_visitor_scope_recorded", "visitor_id", "scope", "recorded_at"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    scope: Mapped[ConsentScope] = mapped_column(
        db_enum(ConsentScope, "consent_scope"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Visit(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_visits_scope_id"),
        Index("ix_visits_card_started", "card_id", "started_at"),
        Index("ix_visits_company_started", "company_id", "started_at"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class VisitEvent(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "visit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            ondelete="CASCADE",
        ),
        Index("ix_visit_events_visit_occurred", "visit_id", "occurred_at"),
        Index("ix_visit_events_company_type_occurred", "company_id", "event_type", "occurred_at"),
    )

    visit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_conversations_scope_id"),
        Index("ix_conversations_card_started", "card_id", "started_at"),
        Index("ix_conversations_company_status_updated", "company_id", "status", "updated_at"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visit_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        db_enum(ConversationStatus, "conversation_status"),
        nullable=False,
        default=ConversationStatus.ACTIVE,
        server_default=text("'active'"),
    )
    primary_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low", server_default=text("'low'")
    )


class Message(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_messages_scope_id"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[MessageRole] = mapped_column(db_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        db_enum(MessageStatus, "message_status"),
        nullable=False,
        default=MessageStatus.COMPLETED,
        server_default=text("'completed'"),
    )
    content_redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    client_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PromptVersion(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_prompt_versions_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "name",
            "version_number",
            name="uq_prompt_versions_name_version",
        ),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        Index("ix_prompt_versions_company_status_updated", "company_id", "status", "updated_at"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[PromptStatus] = mapped_column(
        db_enum(PromptStatus, "prompt_status"),
        nullable=False,
        default=PromptStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelConfig(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "model_configs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_model_configs_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "purpose",
            "provider",
            name="uq_model_configs_purpose_provider",
        ),
        CheckConstraint("timeout_ms > 0", name="timeout_positive"),
        CheckConstraint("max_concurrency > 0", name="concurrency_positive"),
        CheckConstraint("daily_budget_cny >= 0", name="budget_non_negative"),
    )

    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    endpoint_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30000"))
    max_retries: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("2"))
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    daily_budget_cny: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    data_retention: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'no_training'")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class AIRun(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "prompt_version_id"],
            ["prompt_versions.tenant_id", "prompt_versions.company_id", "prompt_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "model_config_id"],
            ["model_configs.tenant_id", "model_configs.company_id", "model_configs.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", name="uq_ai_runs_message_id"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_non_negative"),
        CheckConstraint("total_latency_ms >= 0", name="latency_non_negative"),
        Index("ix_ai_runs_company_created", "company_id", "created_at"),
        Index("ix_ai_runs_trace_id", "trace_id"),
    )

    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    endpoint_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_token_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_cost_cny: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, server_default=text("0")
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    status: Mapped[MessageStatus] = mapped_column(
        db_enum(MessageStatus, "ai_run_status"),
        nullable=False,
        default=MessageStatus.PENDING,
        server_default=text("'pending'"),
    )
    safety_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    retrieval_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeDocument(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "id", "current_version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.document_id",
                "knowledge_versions.id",
            ],
            name="fk_knowledge_documents_current_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_documents_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_type",
            "source_id",
            name="uq_knowledge_documents_source",
        ),
        CheckConstraint(
            "status <> 'published' OR current_version_id IS NOT NULL",
            name="published_requires_current_version",
        ),
        Index(
            "ix_knowledge_documents_company_status_updated", "company_id", "status", "updated_at"
        ),
    )

    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "knowledge_document_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    current_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class KnowledgeVersion(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_versions_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "document_id",
            "id",
            name="uq_knowledge_versions_document_scope_id",
        ),
        UniqueConstraint(
            "document_id", "version_number", name="uq_knowledge_versions_document_version"
        ),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        CheckConstraint(
            "review_status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="approval_state",
        ),
        Index(
            "ix_knowledge_versions_raw_text_fts",
            text("to_tsvector('simple', coalesce(raw_text, ''))"),
            postgresql_using="gin",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        db_enum(ReviewStatus, "knowledge_review_status"),
        nullable=False,
        default=ReviewStatus.DRAFT,
        server_default=text("'draft'"),
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.document_id",
                "knowledge_versions.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_chunks_scope_id"),
        UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunks_version_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
        CheckConstraint("token_count > 0", name="token_count_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name="embedding_metadata",
        ),
        Index(
            "ix_knowledge_chunks_scope_filter",
            "company_id",
            "visibility",
            "is_active",
            "version_id",
        ),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
        Index(
            "ix_knowledge_chunks_text_fts",
            "search_tsv",
            postgresql_using="gin",
        ),
        Index(
            "ix_knowledge_chunks_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        db_enum(Visibility, "knowledge_visibility"),
        nullable=False,
        default=Visibility.PUBLIC,
        server_default=sql_text("'public'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )


class MessageCitation(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.company_id", "knowledge_chunks.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", "chunk_id", name="uq_message_citations_message_chunk"),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("score >= -1 AND score <= 1", name="score_cosine_range"),
        CheckConstraint("char_length(snapshot_hash) = 64", name="snapshot_hash_sha256"),
        Index("ix_message_citations_message_rank", "message_id", "rank"),
    )

    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeIndexJob(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_index_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "version_id", "embedding_model", name="uq_knowledge_index_jobs_version_model"
        ),
        CheckConstraint("attempt >= 0", name="attempt_non_negative"),
        Index(
            "ix_knowledge_index_jobs_company_status_created", "company_id", "status", "created_at"
        ),
    )

    version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[IndexJobStatus] = mapped_column(
        db_enum(IndexJobStatus, "knowledge_index_job_status"),
        nullable=False,
        default=IndexJobStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeGap(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "approved_version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("char_length(normalized_question_hash) = 64", name="question_hash_sha256"),
        CheckConstraint("occurrence_count > 0", name="occurrence_count_positive"),
        Index("ix_knowledge_gaps_company_status_updated", "company_id", "status", "updated_at"),
        Index("ix_knowledge_gaps_company_question_hash", "company_id", "normalized_question_hash"),
        Index(
            "ix_knowledge_gaps_question_trgm",
            "question",
            postgresql_using="gin",
            postgresql_ops={"question": "gin_trgm_ops"},
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    normalized_question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[KnowledgeGapStatus] = mapped_column(
        db_enum(KnowledgeGapStatus, "knowledge_gap_status"),
        nullable=False,
        default=KnowledgeGapStatus.PENDING,
        server_default=text("'pending'"),
    )
    suggested_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class VisitSummary(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visit_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "last_message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "prompt_version_id"],
            ["prompt_versions.tenant_id", "prompt_versions.company_id", "prompt_versions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "conversation_id",
            "last_message_id",
            "prompt_version_id",
            name="uq_visit_summaries_idempotency",
        ),
        Index(
            "uq_visit_summaries_current_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    last_message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    interests: Mapped[list[str]] = mapped_column(
        ARRAY(String(160)), nullable=False, default=list, server_default=text("'{}'::varchar[]")
    )
    strength: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyKey(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "scope", "key", name="uq_idempotency_keys_scope_key"
        ),
        CheckConstraint("char_length(request_hash) = 64", name="request_hash_sha256"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        db_enum(IdempotencyStatus, "idempotency_status"),
        nullable=False,
        default=IdempotencyStatus.PROCESSING,
        server_default=text("'processing'"),
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        CheckConstraint("char_length(entry_hash) = 64", name="entry_hash_sha256"),
        CheckConstraint(
            "previous_hash IS NULL OR char_length(previous_hash) = 64",
            name="previous_hash_sha256",
        ),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
        Index("ix_audit_logs_resource", "company_id", "resource_type", "resource_id"),
        Index("ix_audit_logs_trace_id", "trace_id"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "deduplication_key",
            name="uq_outbox_events_deduplication_key",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_outbox_events_dispatch", "status", "available_at", "created_at"),
        Index("ix_outbox_events_aggregate", "company_id", "aggregate_type", "aggregate_id"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    deduplication_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        db_enum(OutboxStatus, "outbox_status"),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "AIRun",
    "AuditLog",
    "AuthSession",
    "Card",
    "Company",
    "ConsentRecord",
    "Conversation",
    "IdempotencyKey",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeGap",
    "KnowledgeIndexJob",
    "KnowledgeVersion",
    "Membership",
    "Message",
    "MessageCitation",
    "ModelConfig",
    "OutboxEvent",
    "PromptVersion",
    "Tenant",
    "User",
    "Visit",
    "VisitEvent",
    "Visitor",
    "VisitorProfile",
    "VisitSummary",
]

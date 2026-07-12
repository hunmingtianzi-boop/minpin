from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import Settings
from app.db.models import (
    Card,
    Company,
    ConsentRecord,
    ConsentScope,
    ContentStatus,
    Conversation,
    ConversationStatus,
    VisitorProfileSignal,
    VisitorProfileSignalSource,
    VisitSummary,
)
from app.services.workflow_store import WorkflowScope, WorkflowStore


class _ScalarRows:
    def __init__(self, values: list[uuid.UUID]) -> None:
        self.values = values

    def all(self) -> list[uuid.UUID]:
        return self.values


class _AggregationSession:
    def __init__(
        self,
        company: Company,
        consent: ConsentRecord,
        source_message_ids: list[uuid.UUID],
    ) -> None:
        self.company = company
        self.consent = consent
        self.source_message_ids = source_message_ids
        self.signals: list[VisitorProfileSignal] = []
        self.sources: list[VisitorProfileSignalSource] = []

    async def execute(
        self, _statement: Any, _parameters: dict[str, Any] | None = None
    ) -> None:
        return None

    async def get(self, model: Any, identifier: uuid.UUID) -> Any:
        return self.company if model is Company and identifier == self.company.id else None

    async def scalars(self, _statement: Any) -> _ScalarRows:
        return _ScalarRows(self.source_message_ids)

    async def scalar(self, statement: Any) -> Any:
        rendered = str(statement)
        values = set(statement.compile().params.values())
        if "FROM consent_records" in rendered:
            return self.consent
        if "FROM visitor_profile_signal_sources" in rendered:
            return next(
                (
                    source.id
                    for source in self.sources
                    if source.signal_id in values
                    and source.summary_id in values
                    and source.message_id in values
                ),
                None,
            )
        if "FROM visitor_profile_signals" in rendered:
            return next(
                (signal for signal in self.signals if signal.label_hmac in values), None
            )
        return None

    def add(self, value: Any) -> None:
        if isinstance(value, VisitorProfileSignal):
            self.signals.append(value)
        elif isinstance(value, VisitorProfileSignalSource):
            self.sources.append(value)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_summary_interest_aggregation_is_encrypted_explainable_and_idempotent() -> None:
    tenant_id, company_id, visitor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    card = Card(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        owner_user_id=uuid.uuid4(),
        slug="profile-card",
        display_name="画像名片",
        status=ContentStatus.PUBLISHED,
        published_at=datetime.now(UTC),
        settings={"policy_versions": {"profile_personalization": "profile-v2"}},
    )
    company = Company(
        id=company_id,
        tenant_id=tenant_id,
        name="画像企业",
        normalized_name="画像企业",
        status="active",
        settings={"policy_versions": {"profile_personalization": "profile-v2"}},
    )
    consent = ConsentRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        visitor_id=visitor_id,
        scope=ConsentScope.PROFILE_PERSONALIZATION,
        policy_version="profile-v2",
        granted=True,
        recorded_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30),
        evidence={},
    )
    conversation = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        card_id=card.id,
        visitor_id=visitor_id,
        visit_id=uuid.uuid4(),
        status=ConversationStatus.ACTIVE,
        primary_intent="product_evaluation",
    )
    message_ids = [uuid.uuid4(), uuid.uuid4()]
    summary = VisitSummary(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        conversation_id=conversation.id,
        last_message_id=message_ids[-1],
        prompt_version_id=uuid.uuid4(),
        summary="访客关注工业节能项目。",
        interests=["工业节能", "工业节能"],
        strength="strong",
        source_message_ids=message_ids,
        is_current=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
        approved_by=uuid.uuid4(),
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        field_encryption_key="field-encryption-secret-material-v1",
    )
    store = WorkflowStore(None, settings)  # type: ignore[arg-type]
    session = _AggregationSession(company, consent, message_ids)
    scope = WorkflowScope(tenant_id, company_id, uuid.uuid4(), "company_admin")

    await store._aggregate_profile_signals(  # noqa: SLF001
        session, scope=scope, conversation=conversation, summary=summary  # type: ignore[arg-type]
    )
    await store._aggregate_profile_signals(  # noqa: SLF001
        session, scope=scope, conversation=conversation, summary=summary  # type: ignore[arg-type]
    )

    assert len(session.signals) == 2
    assert len(session.sources) == 4
    assert {signal.kind.value for signal in session.signals} == {"interest", "intent"}
    assert all(signal.evidence_count == 2 for signal in session.signals)
    interest = next(signal for signal in session.signals if signal.kind.value == "interest")
    assert "工业节能".encode() not in interest.label_ciphertext
    assert {source.message_id for source in session.sources} == set(message_ids)

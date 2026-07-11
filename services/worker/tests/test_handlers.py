from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from cf_worker.domain import ClaimedEvent, HandlerResult, OutboxRecord, PermanentEventError
from cf_worker.handlers import EventHandlerRegistry


class StubRepository:
    privacy_owner = uuid.uuid4()
    summary_owner = uuid.uuid4()

    async def tenant_slug(self, _event: OutboxRecord) -> str:
        return "tuotu"

    async def privacy_recipient(self, _event: OutboxRecord) -> uuid.UUID:
        return self.privacy_owner

    async def summary_recipient(self, _event: OutboxRecord) -> uuid.UUID:
        return self.summary_owner


class StubEvaluator:
    async def run(self, **_kwargs: Any) -> dict[str, Any]:
        return {"suite_version": "2", "gate": {"passed": True}, "observations": []}


def event(event_type: str, payload: dict[str, Any], *, headers: dict[str, Any] | None = None):
    return OutboxRecord(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        event_type=event_type,
        attempt=1,
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload=payload,
        headers=headers or {},
        deduplication_key=str(uuid.uuid4()),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_lead_handler_creates_only_static_non_pii_notification() -> None:
    record = event(
        "lead.created.v1",
        {
            "lead_id": str(uuid.uuid4()),
            "card_id": str(uuid.uuid4()),
            "owner_user_id": str(uuid.uuid4()),
        },
    )
    result = await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(record)
    assert result.handler_name == "lead-notification-v1"
    assert len(result.notifications) == 1
    assert "联系方式" in result.notifications[0].body
    assert "@" not in result.notifications[0].body


@pytest.mark.asyncio
async def test_evaluation_handler_returns_versioned_report_and_notification() -> None:
    company_id = uuid.uuid4()
    record = event(
        "knowledge.evaluate.requested.v1",
        {"company_id": str(company_id), "requested_by": str(uuid.uuid4())},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(record, field) for field in record.__dataclass_fields__},
            "company_id": company_id,
        }
    )
    result = await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(record)
    assert result.report is not None
    assert result.report.schema_version == 1
    assert result.report.status == "passed"
    assert result.result_hash() == result.result_hash()


@pytest.mark.asyncio
async def test_payload_with_pii_marker_or_extra_field_is_rejected() -> None:
    base = {
        "lead_id": str(uuid.uuid4()),
        "card_id": str(uuid.uuid4()),
        "owner_user_id": str(uuid.uuid4()),
    }
    registry = EventHandlerRegistry(StubRepository(), StubEvaluator())
    with pytest.raises(PermanentEventError, match="pii_payload_forbidden"):
        await registry.handle(event("lead.created.v1", base, headers={"contains_pii": True}))
    with pytest.raises(PermanentEventError, match="unexpected_payload_field"):
        await registry.handle(event("lead.created.v1", {**base, "mobile": "13800000000"}))


@pytest.mark.asyncio
async def test_unknown_event_is_rejected_without_payload_interpretation() -> None:
    with pytest.raises(PermanentEventError, match="unsupported_event_type"):
        await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(
            event("unknown.v1", {"secret": "do-not-log"})
        )


def test_handler_result_hash_is_stable() -> None:
    result = HandlerResult(handler_name="test", metadata={"b": 2, "a": 1})
    assert len(result.result_hash()) == 64


def test_claimed_event_contains_no_payload() -> None:
    claim = ClaimedEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        event_type="lead.created.v1",
        attempt=1,
    )
    assert not hasattr(claim, "payload")

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db.models import (
    VisitorProfileSignal,
    VisitorProfileSignalKind,
    VisitorProfileSignalSource,
)
from app.services.visitor_profile_store import (
    VisitorProfileScope,
    VisitorProfileStore,
    _visible_metrics,
)


class _ScalarRows:
    def __init__(self, rows: list[VisitorProfileSignalSource]) -> None:
        self._rows = rows

    def all(self) -> list[VisitorProfileSignalSource]:
        return self._rows


class _OwnerAwareSession:
    def __init__(
        self,
        sources: list[VisitorProfileSignalSource],
        owners_by_visit: dict[uuid.UUID, uuid.UUID],
    ) -> None:
        self.sources = sources
        self.owners_by_visit = owners_by_visit

    async def scalars(self, statement: Any) -> _ScalarRows:
        params = set(statement.compile().params.values())
        requested_owner = next(
            (owner for owner in self.owners_by_visit.values() if owner in params), None
        )
        rows = self.sources
        if requested_owner is not None:
            rows = [
                source
                for source in rows
                if self.owners_by_visit[source.visit_id] == requested_owner
            ]
        return _ScalarRows(rows)


@pytest.mark.asyncio
async def test_card_owner_sources_and_metrics_are_recomputed_per_owned_card() -> None:
    tenant_id, company_id, signal_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    visit_a, visit_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    consent_id = uuid.uuid4()
    signal = VisitorProfileSignal(
        id=signal_id,
        tenant_id=tenant_id,
        company_id=company_id,
        visitor_id=uuid.uuid4(),
        kind=VisitorProfileSignalKind.INTEREST,
        label_ciphertext=b"encrypted",
        label_hmac="a" * 64,
        strength=0.9,
        confidence=0.95,
        first_seen_at=now,
        last_seen_at=now,
        evidence_count=2,
        retention_expires_at=now + timedelta(days=1),
        encryption_key_ref="test",
    )
    sources = [
        VisitorProfileSignalSource(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            signal_id=signal_id,
            consent_id=consent_id,
            visit_id=visit_a,
            conversation_id=uuid.uuid4(),
            summary_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            contribution=0.3,
            confidence=0.4,
            observed_at=now,
            retention_expires_at=signal.retention_expires_at,
        ),
        VisitorProfileSignalSource(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            signal_id=signal_id,
            consent_id=consent_id,
            visit_id=visit_b,
            conversation_id=uuid.uuid4(),
            summary_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            contribution=0.9,
            confidence=0.95,
            observed_at=now,
            retention_expires_at=signal.retention_expires_at,
        ),
    ]
    session = _OwnerAwareSession(sources, {visit_a: owner_a, visit_b: owner_b})
    scope_a = VisitorProfileScope(tenant_id, company_id, owner_a, "card_owner")
    visible = await VisitorProfileStore._sources(  # noqa: SLF001
        session, signal, scope_a  # type: ignore[arg-type]
    )

    assert [source.visit_id for source in visible] == [visit_a]
    strength, confidence, _first_seen, _last_seen = _visible_metrics(visible)
    assert strength == 0.3
    assert confidence == 0.4

    admin_scope = VisitorProfileScope(
        tenant_id, company_id, uuid.uuid4(), "company_admin"
    )
    all_sources = await VisitorProfileStore._sources(  # noqa: SLF001
        session, signal, admin_scope  # type: ignore[arg-type]
    )
    assert {source.visit_id for source in all_sources} == {visit_a, visit_b}

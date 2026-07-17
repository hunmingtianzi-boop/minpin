from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card, CardKind, ContentStatus
from app.services.public_store import _published_enterprise_card_slug


def _card(kind: CardKind, *, slug: str) -> Card:
    responsible_user_id = uuid.uuid4()
    return Card(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_kind=kind,
        owner_user_id=(responsible_user_id if kind == CardKind.EMPLOYEE else None),
        responsible_user_id=responsible_user_id,
        slug=slug,
        display_name="测试名片",
        status=ContentStatus.PUBLISHED,
        published_at=datetime.now(UTC),
        settings={},
    )


@pytest.mark.asyncio
async def test_employee_card_resolves_published_enterprise_card_slug() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = "official-company-card"

    result = await _published_enterprise_card_slug(
        session,
        card=_card(CardKind.EMPLOYEE, slug="employee-card"),
    )

    assert result == "official-company-card"
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_enterprise_card_uses_its_own_slug_without_extra_query() -> None:
    session = AsyncMock(spec=AsyncSession)

    result = await _published_enterprise_card_slug(
        session,
        card=_card(CardKind.ENTERPRISE, slug="official-company-card"),
    )

    assert result == "official-company-card"
    session.scalar.assert_not_awaited()

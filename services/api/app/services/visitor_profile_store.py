from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.workflow_schemas import (
    VisitorProfileDetail,
    VisitorProfileListItem,
    VisitorProfileSignalPreview,
    VisitorProfileSignalView,
    VisitorProfileSourceView,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    Card,
    Company,
    ConsentRecord,
    ConsentScope,
    Visit,
    Visitor,
    VisitorProfileSignal,
    VisitorProfileSignalKind,
    VisitorProfileSignalSource,
)
from app.db.session import set_rls_context


@dataclass(frozen=True, slots=True)
class VisitorProfileScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


class VisitorProfileStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        self._sessions = session_factory
        self._cipher = PiiCipher.from_settings(settings)

    async def list(
        self, *, scope: VisitorProfileScope, limit: int, offset: int
    ) -> tuple[list[VisitorProfileListItem], int]:
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session, tenant_id=scope.tenant_id, company_id=scope.company_id
            )
            filters = (self._authorized(scope), self._has_active_signal(scope))
            total = int(
                await session.scalar(select(func.count(Visitor.id)).where(*filters)) or 0
            )
            visitors = (
                await session.scalars(
                    select(Visitor)
                    .where(*filters)
                    .order_by(Visitor.last_seen_at.desc(), Visitor.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            items: list[VisitorProfileListItem] = []
            for visitor in visitors:
                signals = await self._signals(session, visitor.id, scope)
                previews: list[VisitorProfileSignalPreview] = []
                for signal in signals:
                    if signal.kind != VisitorProfileSignalKind.INTEREST:
                        continue
                    sources = await self._sources(session, signal, scope)
                    strength, confidence, _first_seen, last_seen = _visible_metrics(sources)
                    previews.append(
                        VisitorProfileSignalPreview(
                            label=self._cipher.decrypt(signal.label_ciphertext),
                            strength=strength,
                            confidence=confidence,
                            last_seen_at=last_seen,
                        )
                    )
                items.append(
                    VisitorProfileListItem(
                        visitor_id=visitor.id,
                        first_seen_at=visitor.first_seen_at,
                        last_seen_at=visitor.last_seen_at,
                        signal_count=len(signals),
                        top_interests=sorted(
                            previews,
                            key=lambda item: (item.strength, item.last_seen_at),
                            reverse=True,
                        )[:5],
                    )
                )
            return items, total

    async def get(
        self, *, scope: VisitorProfileScope, visitor_id: uuid.UUID
    ) -> VisitorProfileDetail:
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session, tenant_id=scope.tenant_id, company_id=scope.company_id
            )
            visitor = await session.scalar(
                select(Visitor).where(
                    Visitor.id == visitor_id,
                    self._authorized(scope),
                    self._has_active_signal(scope),
                )
            )
            if visitor is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "访客画像不存在")
            signals = await self._signals(session, visitor.id, scope)
            views: list[VisitorProfileSignalView] = []
            for signal in signals:
                sources = await self._sources(session, signal, scope)
                strength, confidence, first_seen, last_seen = _visible_metrics(sources)
                views.append(
                    VisitorProfileSignalView(
                        id=signal.id,
                        kind=signal.kind.value,
                        label=self._cipher.decrypt(signal.label_ciphertext),
                        strength=strength,
                        confidence=confidence,
                        first_seen_at=first_seen,
                        last_seen_at=last_seen,
                        evidence_count=len(sources),
                        retention_expires_at=max(
                            source.retention_expires_at for source in sources
                        ),
                        sources=[
                            VisitorProfileSourceView(
                                id=source.id,
                                visit_id=source.visit_id,
                                conversation_id=source.conversation_id,
                                summary_id=source.summary_id,
                                message_id=source.message_id,
                                contribution=source.contribution,
                                confidence=source.confidence,
                                observed_at=source.observed_at,
                            )
                            for source in sources
                        ],
                    )
                )
            return VisitorProfileDetail(
                visitor_id=visitor.id,
                first_seen_at=visitor.first_seen_at,
                last_seen_at=visitor.last_seen_at,
                signals=views,
            )

    @staticmethod
    async def _signals(
        session: AsyncSession,
        visitor_id: uuid.UUID,
        scope: VisitorProfileScope,
    ) -> list[VisitorProfileSignal]:
        return list(
            (
                await session.scalars(
                    select(VisitorProfileSignal)
                    .where(
                        VisitorProfileSignal.visitor_id == visitor_id,
                        VisitorProfileSignal.retention_expires_at > func.now(),
                        VisitorProfileStore._signal_visible_to_scope(scope),
                    )
                    .order_by(
                        VisitorProfileSignal.strength.desc(),
                        VisitorProfileSignal.last_seen_at.desc(),
                    )
                )
            ).all()
        )

    @staticmethod
    async def _sources(
        session: AsyncSession,
        signal: VisitorProfileSignal,
        scope: VisitorProfileScope,
    ) -> list[VisitorProfileSignalSource]:
        statement = (
            select(VisitorProfileSignalSource)
            .where(
                VisitorProfileSignalSource.signal_id == signal.id,
                VisitorProfileSignalSource.consent_id
                == VisitorProfileStore._latest_consent_id(
                    scope, visitor_id=signal.visitor_id
                ),
                VisitorProfileSignalSource.retention_expires_at > func.now(),
            )
            .order_by(VisitorProfileSignalSource.observed_at.desc())
        )
        if scope.is_card_owner:
            statement = (
                statement.join(Visit, Visit.id == VisitorProfileSignalSource.visit_id)
                .join(Card, Card.id == Visit.card_id)
                .where(Card.owner_user_id == scope.actor_user_id)
            )
        return list((await session.scalars(statement)).all())

    @staticmethod
    def _signal_visible_to_scope(scope: VisitorProfileScope) -> object:
        statement = (
            select(VisitorProfileSignalSource.id)
            .join(Visit, Visit.id == VisitorProfileSignalSource.visit_id)
            .join(Card, Card.id == Visit.card_id)
            .where(
                VisitorProfileSignalSource.signal_id == VisitorProfileSignal.id,
                VisitorProfileSignalSource.consent_id
                == VisitorProfileStore._latest_consent_id(
                    scope, visitor_id=VisitorProfileSignal.visitor_id
                ),
                VisitorProfileSignalSource.retention_expires_at > func.now(),
            )
        )
        if scope.is_card_owner:
            statement = statement.where(Card.owner_user_id == scope.actor_user_id)
        return exists(statement)

    @staticmethod
    def _has_active_signal(scope: VisitorProfileScope) -> object:
        return exists(
            select(VisitorProfileSignal.id).where(
                VisitorProfileSignal.visitor_id == Visitor.id,
                VisitorProfileSignal.retention_expires_at > func.now(),
                VisitorProfileStore._signal_visible_to_scope(scope),
            )
        )

    @staticmethod
    def _latest_consent_id(
        scope: VisitorProfileScope, *, visitor_id: object
    ) -> object:
        return (
            select(ConsentRecord.id)
            .where(
                ConsentRecord.tenant_id == scope.tenant_id,
                ConsentRecord.company_id == scope.company_id,
                ConsentRecord.visitor_id == visitor_id,
                ConsentRecord.scope == ConsentScope.PROFILE_PERSONALIZATION,
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
            .scalar_subquery()
        )

    @staticmethod
    def _authorized(scope: VisitorProfileScope) -> object:
        latest_id = (
            select(ConsentRecord.id)
            .where(
                ConsentRecord.tenant_id == scope.tenant_id,
                ConsentRecord.company_id == scope.company_id,
                ConsentRecord.visitor_id == Visitor.id,
                ConsentRecord.scope == ConsentScope.PROFILE_PERSONALIZATION,
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
            .correlate(Visitor)
            .scalar_subquery()
        )
        policy = func.coalesce(
            Company.settings["policy_versions"]["profile_personalization"].as_string(),
            "profile-personalization-v1",
        )
        filters: list[object] = [
            ConsentRecord.id == latest_id,
            ConsentRecord.granted.is_(True),
            ConsentRecord.expires_at > func.now(),
            ConsentRecord.policy_version == policy,
            Visit.visitor_id == Visitor.id,
        ]
        if scope.is_card_owner:
            filters.append(Card.owner_user_id == scope.actor_user_id)
        return exists(
            select(ConsentRecord.id)
            .select_from(ConsentRecord)
            .join(Visit, Visit.visitor_id == ConsentRecord.visitor_id)
            .join(Card, Card.id == Visit.card_id)
            .join(Company, Company.id == Card.company_id)
            .where(*filters)
        )


__all__ = ["VisitorProfileScope", "VisitorProfileStore"]


def _visible_metrics(
    sources: list[VisitorProfileSignalSource],
) -> tuple[float, float, object, object]:
    if not sources:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "访客画像证据不存在")
    return (
        max(source.contribution for source in sources),
        max(source.confidence for source in sources),
        min(source.observed_at for source in sources),
        max(source.observed_at for source in sources),
    )

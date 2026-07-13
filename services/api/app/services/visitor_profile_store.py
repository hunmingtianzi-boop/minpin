from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.workflow_schemas import (
    VisitorProfileDetail,
    VisitorProfileListItem,
    VisitorProfileOverview,
    VisitorProfileOverviewConversation,
    VisitorProfileOverviewGap,
    VisitorProfileOverviewLead,
    VisitorProfileSignalPreview,
    VisitorProfileSignalView,
    VisitorProfileSourceView,
)
from app.core.config import Settings
from app.core.pii import PiiCipher, PiiCipherError, mask_value
from app.db.models import (
    Card,
    Company,
    ConsentRecord,
    ConsentScope,
    Conversation,
    KnowledgeGap,
    Lead,
    Message,
    Visit,
    Visitor,
    VisitorProfile,
    VisitorProfileSignal,
    VisitorProfileSignalKind,
    VisitorProfileSignalSource,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit


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

    async def overview(
        self,
        *,
        scope: VisitorProfileScope,
        visitor_id: uuid.UUID,
        trace_id: str | None,
    ) -> VisitorProfileOverview:
        """Return the authorized visitor's operating context without raw IP or PII."""

        profile = await self.get(scope=scope, visitor_id=visitor_id)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session, tenant_id=scope.tenant_id, company_id=scope.company_id
            )
            card_filters = self._card_filters(scope)
            lead_rows = (
                await session.execute(
                    select(Lead, Card.display_name, VisitorProfile)
                    .join(Card, Card.id == Lead.card_id)
                    .outerjoin(
                        VisitorProfile,
                        (VisitorProfile.tenant_id == Lead.tenant_id)
                        & (VisitorProfile.company_id == Lead.company_id)
                        & (VisitorProfile.visitor_id == Lead.visitor_id),
                    )
                    .where(
                        Lead.tenant_id == scope.tenant_id,
                        Lead.company_id == scope.company_id,
                        Lead.visitor_id == visitor_id,
                        *card_filters,
                    )
                    .order_by(Lead.created_at.desc(), Lead.id.desc())
                    .limit(10)
                )
            ).all()
            leads = [
                self._overview_lead(lead, display_name, contact_profile)
                for lead, display_name, contact_profile in lead_rows
            ]

            message_count = (
                select(func.count(Message.id))
                .where(Message.conversation_id == Conversation.id)
                .correlate(Conversation)
                .scalar_subquery()
            )
            conversation_rows = (
                await session.execute(
                    select(Conversation, Card.display_name, message_count)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        Conversation.tenant_id == scope.tenant_id,
                        Conversation.company_id == scope.company_id,
                        Conversation.visitor_id == visitor_id,
                        *card_filters,
                    )
                    .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
                    .limit(20)
                )
            ).all()
            conversations = [
                VisitorProfileOverviewConversation(
                    id=conversation.id,
                    card_id=conversation.card_id,
                    card_display_name=display_name,
                    status=conversation.status.value,
                    primary_intent=conversation.primary_intent,
                    risk_level=conversation.risk_level,
                    started_at=conversation.started_at,
                    last_activity_at=conversation.last_activity_at,
                    message_count=int(count or 0),
                )
                for conversation, display_name, count in conversation_rows
            ]

            gap_rows = (
                await session.scalars(
                    select(KnowledgeGap)
                    .join(Conversation, Conversation.id == KnowledgeGap.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        KnowledgeGap.tenant_id == scope.tenant_id,
                        KnowledgeGap.company_id == scope.company_id,
                        Conversation.visitor_id == visitor_id,
                        *card_filters,
                    )
                    .order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc())
                    .limit(20)
                )
            ).all()
            gaps = [
                VisitorProfileOverviewGap(
                    id=gap.id,
                    conversation_id=gap.conversation_id,
                    question=gap.question,
                    reason=gap.reason,
                    status=gap.status.value,
                    occurrence_count=gap.occurrence_count,
                    last_seen_at=gap.last_seen_at,
                )
                for gap in gap_rows
            ]
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="visitor_profile.overview_read",
                resource_type="visitor_profile",
                resource_id=visitor_id,
                trace_id=trace_id,
                event_data={
                    "lead_count": len(leads),
                    "conversation_count": len(conversations),
                    "knowledge_gap_count": len(gaps),
                },
            )
            return VisitorProfileOverview(
                profile=profile,
                leads=leads,
                conversations=conversations,
                knowledge_gaps=gaps,
            )

    def _overview_lead(
        self,
        lead: Lead,
        card_display_name: str,
        profile: VisitorProfile | None,
    ) -> VisitorProfileOverviewLead:
        name = self._decrypt_optional(profile.name_ciphertext) if profile else ""
        contact = ""
        contact_kind = "generic"
        if profile:
            for ciphertext, kind in (
                (profile.mobile_ciphertext, "phone"),
                (profile.email_ciphertext, "email"),
                (profile.wechat_ciphertext, "wechat"),
            ):
                if ciphertext:
                    contact = self._decrypt_optional(ciphertext)
                    contact_kind = kind
                    break
        return VisitorProfileOverviewLead(
            id=lead.id,
            card_id=lead.card_id,
            card_display_name=card_display_name,
            conversation_id=lead.conversation_id,
            status=lead.status.value,
            priority=lead.priority,
            masked_name=mask_value(name, kind="name"),
            masked_contact=mask_value(contact, kind=contact_kind),
            company_name=profile.company_name if profile else None,
            created_at=lead.created_at,
        )

    def _decrypt_optional(self, ciphertext: bytes) -> str:
        try:
            return self._cipher.decrypt(ciphertext)
        except PiiCipherError:
            return ""

    @staticmethod
    def _card_filters(scope: VisitorProfileScope) -> tuple[object, ...]:
        if scope.is_card_owner:
            return (Card.owner_user_id == scope.actor_user_id,)
        return ()

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

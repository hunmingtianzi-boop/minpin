"""Short-lived, tenant-scoped cache for published FAQ fast answers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.ai.schemas import RetrievalQuery, RetrievedEvidence


class RedisFAQAnswerCache:
    """Fail-open cache that never stores the raw question in a Redis key.

    FAQ content is already public, but keys are still hashed and scoped by
    tenant, company and card to prevent cross-tenant reuse. A short TTL bounds
    staleness when an administrator republishes knowledge.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        ttl_seconds: int = 60,
        prefix: str = "cf:ai:faq:v1",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    async def get(self, query: RetrievalQuery) -> RetrievedEvidence | None:
        key = self._key(query)
        try:
            raw = await self._redis.get(key)
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return _evidence_from_payload(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            try:
                await self._redis.delete(key)
            except RedisError:
                pass
            return None

    async def put(self, query: RetrievalQuery, evidence: RetrievedEvidence) -> None:
        try:
            await self._redis.set(
                self._key(query),
                json.dumps(_evidence_payload(evidence), ensure_ascii=False, separators=(",", ":")),
                ex=self._ttl_seconds,
            )
        except (RedisError, TypeError, ValueError):
            # Redis must not become a new availability dependency for chat.
            return

    def _key(self, query: RetrievalQuery) -> str:
        material = "\x00".join(
            (
                query.tenant_id,
                query.company_id,
                query.card_id or "",
                " ".join(query.text.casefold().split()),
            )
        ).encode("utf-8")
        digest = hashlib.sha256(material).hexdigest()
        return f"{self._prefix}:{digest}"


def _evidence_payload(evidence: RetrievedEvidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "document_id": evidence.document_id,
        "version_id": evidence.version_id,
        "ordinal": evidence.ordinal,
        "title": evidence.title,
        "text": evidence.text,
        "score": evidence.score,
        "vector_score": evidence.vector_score,
        "lexical_score": evidence.lexical_score,
        "content_hash": evidence.content_hash,
        "embedding_model": evidence.embedding_model,
        "metadata": dict(evidence.metadata),
    }


def _evidence_from_payload(payload: Any) -> RetrievedEvidence:
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata", {}), dict):
        raise ValueError("invalid FAQ cache payload")
    return RetrievedEvidence(
        evidence_id=str(payload["evidence_id"]),
        document_id=str(payload["document_id"]),
        version_id=str(payload["version_id"]),
        ordinal=int(payload["ordinal"]),
        title=str(payload["title"]),
        text=str(payload["text"]),
        score=float(payload["score"]),
        vector_score=(
            float(payload["vector_score"]) if payload.get("vector_score") is not None else None
        ),
        lexical_score=(
            float(payload["lexical_score"]) if payload.get("lexical_score") is not None else None
        ),
        content_hash=(str(payload["content_hash"]) if payload.get("content_hash") else None),
        embedding_model=(
            str(payload["embedding_model"]) if payload.get("embedding_model") else None
        ),
        metadata=dict(payload.get("metadata", {})),
    )


__all__ = ["RedisFAQAnswerCache"]

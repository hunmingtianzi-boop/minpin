from __future__ import annotations

from app.ai.schemas import RetrievalQuery, RetrievedEvidence
from app.services.faq_answer_cache import RedisFAQAnswerCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex == 60
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _query(*, card_id: str = "card-1") -> RetrievalQuery:
    return RetrievalQuery(
        tenant_id="tenant-1",
        company_id="company-1",
        card_id=card_id,
        text="标准版包含什么？",
    )


async def test_faq_cache_round_trip_and_card_scope() -> None:
    redis = FakeRedis()
    cache = RedisFAQAnswerCache(redis)  # type: ignore[arg-type]
    evidence = RetrievedEvidence(
        evidence_id="chunk-1",
        document_id="doc-1",
        version_id="version-1",
        ordinal=0,
        title="标准版包含什么？",
        text="标准版包含智能名片。",
        score=1.0,
        lexical_score=1.0,
        content_hash="sha256:faq",
        metadata={"source_type": "faq", "faq_exact": True},
    )

    await cache.put(_query(), evidence)

    cached = await cache.get(_query())
    assert cached == evidence
    assert await cache.get(_query(card_id="card-2")) is None
    assert all("标准版包含什么" not in key for key in redis.values)

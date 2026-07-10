from __future__ import annotations

import uuid

from app.api.routes.public_conversations import _answer_events
from app.services.public_store import StoredAnswer, StoredCitation


async def test_answer_events_replays_persisted_answer_with_citations() -> None:
    message_id = uuid.uuid4()
    answer = StoredAnswer(
        message_id=message_id,
        text="这是有证据的回答。",
        finish_reason="stop",
        citations=(
            StoredCitation(
                id=uuid.uuid4(),
                label="企业资料",
                source_type="faq",
            ),
        ),
    )

    chunks = [
        chunk.decode("utf-8")
        async for chunk in _answer_events(
            message_id=message_id,
            request_id="request-1",
            stored=answer,
            task=None,
        )
    ]
    body = "".join(chunks)

    assert "event: message.started" in body
    assert "event: message.delta" in body
    assert "event: message.citation" in body
    assert "event: message.completed" in body
    assert body.index("message.delta") < body.index("message.citation")

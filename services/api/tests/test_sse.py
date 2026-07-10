from __future__ import annotations

from app.api.sse import encode_sse


def test_encode_sse_preserves_unicode_and_prevents_event_injection() -> None:
    encoded = encode_sse("message.delta\nevent: bad", {"text": "企业知识"})
    body = encoded.decode("utf-8")

    assert body.startswith("event: message.deltaevent: bad\n")
    assert 'data: {"text":"企业知识"}\n\n' in body

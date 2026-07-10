from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def encode_sse(
    event: str,
    data: Mapping[str, Any],
    *,
    event_id: str | None = None,
    retry_ms: int | None = None,
) -> bytes:
    """Encode one UTF-8 SSE event without allowing line injection."""

    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id.replace(chr(10), '').replace(chr(13), '')}")
    if retry_ms is not None:
        lines.append(f"retry: {max(retry_ms, 0)}")
    lines.append(f"event: {event.replace(chr(10), '').replace(chr(13), '')}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")

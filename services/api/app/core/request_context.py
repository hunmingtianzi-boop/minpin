from __future__ import annotations

import uuid
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    # UUIDv7 is not part of Python 3.12. UUID4 remains opaque and collision-safe.
    return str(uuid.uuid4())

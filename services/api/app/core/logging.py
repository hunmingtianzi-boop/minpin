from __future__ import annotations

import logging
import sys

import structlog

SENSITIVE_EVENT_KEYS = {
    "authorization",
    "content",
    "cookie",
    "embedding_api_key",
    "llm_api_key",
    "password",
    "prompt",
    "refresh_token",
    "token",
}


def _redact_secrets(
    _logger: object, _method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    for key in tuple(event_dict):
        if key.lower() in SENSITIVE_EVENT_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

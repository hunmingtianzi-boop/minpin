"""Safe, transport-agnostic error types for the AI subsystem.

The exceptions in this module deliberately keep upstream response bodies and
request credentials out of their state.  They are therefore safe to expose to
structured application logging without accidentally persisting an API key or
provider payload.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class AIErrorCategory(StrEnum):
    """Stable error classes that API handlers can map to their own status codes."""

    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INVALID_RESPONSE = "invalid_response"
    RETRIEVAL = "retrieval"
    SAFETY = "safety"


class AIServiceError(RuntimeError):
    """Base error containing only explicitly safe diagnostic fields."""

    def __init__(
        self,
        message: str,
        *,
        category: AIErrorCategory,
        code: str,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id

    def to_safe_dict(self) -> dict[str, Any]:
        """Return fields suitable for logs or an API error envelope."""

        result: dict[str, Any] = {
            "category": self.category.value,
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.request_id:
            result["request_id"] = self.request_id
        return result


class AIProviderError(AIServiceError):
    """An OpenAI-compatible provider request failed."""


class AIRetrievalError(AIServiceError):
    """The retrieval repository could not produce evidence."""

    def __init__(self, message: str = "Knowledge retrieval failed.") -> None:
        super().__init__(
            message,
            category=AIErrorCategory.RETRIEVAL,
            code="retrieval_failed",
            retryable=True,
        )


class AIInputError(AIServiceError):
    """The user input failed deterministic validation."""

    def __init__(self, message: str, *, code: str = "invalid_input") -> None:
        super().__init__(
            message,
            category=AIErrorCategory.INVALID_REQUEST,
            code=code,
            retryable=False,
        )

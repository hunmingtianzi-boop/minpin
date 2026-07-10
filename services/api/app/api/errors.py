from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.request_context import request_id_ctx


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ApiErrorEnvelope(BaseModel):
    error: ApiErrorBody


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.safe_message = message
        self.details = dict(details or {})
        self.headers = dict(headers or {})


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    payload = ApiErrorEnvelope(
        error=ApiErrorBody(
            code=exc.code,
            message=exc.safe_message,
            details=exc.details,
            request_id=request_id_ctx.get(),
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(mode="json"),
        headers=exc.headers,
    )

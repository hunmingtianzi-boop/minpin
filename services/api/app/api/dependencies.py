from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request

from app.api.errors import ApiError
from app.core.tokens import VisitorPrincipal, VisitorTokenError, decode_visitor_token


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key or not (8 <= len(idempotency_key) <= 128):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "请求缺少有效的幂等标识",
            details={"field": "Idempotency-Key"},
        )
    return idempotency_key


def get_visitor_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> VisitorPrincipal:
    settings = request.app.state.settings
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "AUTH_REQUIRED", "访客会话已失效，请刷新页面后重试")
    try:
        return decode_visitor_token(
            token,
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
        )
    except VisitorTokenError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "访客会话已失效，请刷新页面后重试") from exc

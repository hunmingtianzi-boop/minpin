from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError

VISITOR_AUDIENCE = "cf-ai-card-public"


class VisitorTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VisitorPrincipal:
    visitor_id: uuid.UUID
    visit_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    card_id: uuid.UUID
    token_id: uuid.UUID

    @property
    def rate_limit_subject(self) -> str:
        raw = f"{self.company_id}:{self.token_id}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]


def issue_visitor_token(
    *,
    signing_key: str,
    issuer: str,
    ttl_seconds: int,
    visitor_id: uuid.UUID,
    visit_id: uuid.UUID,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    card_id: uuid.UUID,
) -> tuple[str, int]:
    now = int(time.time())
    expires_at = now + ttl_seconds
    payload = {
        "iss": issuer,
        "aud": VISITOR_AUDIENCE,
        "sub": str(visitor_id),
        "typ": "visitor_session",
        "jti": str(uuid.uuid4()),
        "visit_id": str(visit_id),
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "card_id": str(card_id),
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, signing_key, algorithm="HS256"), expires_at


def decode_visitor_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
) -> VisitorPrincipal:
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            audience=VISITOR_AUDIENCE,
            issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"]},
        )
        if payload.get("typ") != "visitor_session":
            raise VisitorTokenError("wrong token type")
        return VisitorPrincipal(
            visitor_id=uuid.UUID(payload["sub"]),
            visit_id=uuid.UUID(payload["visit_id"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            company_id=uuid.UUID(payload["company_id"]),
            card_id=uuid.UUID(payload["card_id"]),
            token_id=uuid.UUID(payload["jti"]),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise VisitorTokenError("invalid visitor session token") from exc

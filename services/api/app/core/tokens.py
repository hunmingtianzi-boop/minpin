from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError

VISITOR_AUDIENCE = "cf-ai-card-public"
STAFF_ACCESS_AUDIENCE = "cf-ai-card-staff-access"
STAFF_REFRESH_AUDIENCE = "cf-ai-card-staff-refresh"


class VisitorTokenError(ValueError):
    pass


class StaffTokenError(ValueError):
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


@dataclass(frozen=True, slots=True)
class StaffPrincipal:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    role: str
    permissions: tuple[str, ...]
    session_id: uuid.UUID
    token_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class StaffRefreshPrincipal:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    token_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IssuedStaffTokens:
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int


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


def issue_staff_tokens(
    *,
    signing_key: str,
    issuer: str,
    access_ttl_seconds: int,
    refresh_ttl_seconds: int,
    user_id: uuid.UUID,
    membership_id: uuid.UUID,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    role: str,
    permissions: tuple[str, ...],
    session_id: uuid.UUID,
) -> IssuedStaffTokens:
    now = int(time.time())
    access_expires_at = now + access_ttl_seconds
    refresh_expires_at = now + refresh_ttl_seconds
    common = {
        "iss": issuer,
        "sub": str(user_id),
        "membership_id": str(membership_id),
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "session_id": str(session_id),
        "iat": now,
        "nbf": now,
    }
    access_payload = {
        **common,
        "aud": STAFF_ACCESS_AUDIENCE,
        "typ": "staff_access",
        "jti": str(uuid.uuid4()),
        "role": role,
        "permissions": list(permissions),
        "exp": access_expires_at,
    }
    refresh_payload = {
        **common,
        "aud": STAFF_REFRESH_AUDIENCE,
        "typ": "staff_refresh",
        "jti": str(uuid.uuid4()),
        "exp": refresh_expires_at,
    }
    return IssuedStaffTokens(
        access_token=jwt.encode(access_payload, signing_key, algorithm="HS256"),
        refresh_token=jwt.encode(refresh_payload, signing_key, algorithm="HS256"),
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )


def decode_staff_access_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
) -> StaffPrincipal:
    payload = _decode_staff_token(
        token,
        signing_key=signing_key,
        issuer=issuer,
        audience=STAFF_ACCESS_AUDIENCE,
        expected_kind="staff_access",
    )
    try:
        raw_permissions = payload["permissions"]
        if not isinstance(raw_permissions, list) or len(raw_permissions) > 100:
            raise ValueError("invalid permissions")
        permissions = tuple(dict.fromkeys(_required_claim_string(item) for item in raw_permissions))
        role = _required_claim_string(payload["role"])
        return StaffPrincipal(
            user_id=uuid.UUID(payload["sub"]),
            membership_id=uuid.UUID(payload["membership_id"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            company_id=uuid.UUID(payload["company_id"]),
            role=role,
            permissions=permissions,
            session_id=uuid.UUID(payload["session_id"]),
            token_id=uuid.UUID(payload["jti"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StaffTokenError("invalid staff access token") from exc


def decode_staff_refresh_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
) -> StaffRefreshPrincipal:
    payload = _decode_staff_token(
        token,
        signing_key=signing_key,
        issuer=issuer,
        audience=STAFF_REFRESH_AUDIENCE,
        expected_kind="staff_refresh",
    )
    try:
        return StaffRefreshPrincipal(
            user_id=uuid.UUID(payload["sub"]),
            membership_id=uuid.UUID(payload["membership_id"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            company_id=uuid.UUID(payload["company_id"]),
            session_id=uuid.UUID(payload["session_id"]),
            token_id=uuid.UUID(payload["jti"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StaffTokenError("invalid staff refresh token") from exc


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_staff_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
    audience: str,
    expected_kind: str,
) -> dict[str, object]:
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "iss",
                    "aud",
                    "sub",
                    "jti",
                    "membership_id",
                    "tenant_id",
                    "company_id",
                    "session_id",
                ]
            },
        )
        if payload.get("typ") != expected_kind:
            raise StaffTokenError("wrong staff token type")
        return payload
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise StaffTokenError("invalid staff token") from exc


def _required_claim_string(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 160:
        raise ValueError("invalid string claim")
    return value

from __future__ import annotations

import uuid

import pytest

from app.core.tokens import (
    ProfileLinkTokenError,
    VisitorTokenError,
    decode_profile_link_token,
    decode_visitor_token,
    issue_profile_link_token,
    issue_visitor_token,
)


def test_visitor_token_round_trip_and_scope() -> None:
    ids = {
        name: uuid.uuid4()
        for name in ("visitor_id", "visit_id", "tenant_id", "company_id", "card_id")
    }
    token, expires_at = issue_visitor_token(
        signing_key="x" * 32,
        issuer="test",
        ttl_seconds=600,
        **ids,
    )

    principal = decode_visitor_token(token, signing_key="x" * 32, issuer="test")

    assert principal.company_id == ids["company_id"]
    assert principal.card_id == ids["card_id"]
    assert expires_at > 0


def test_visitor_token_rejects_wrong_key() -> None:
    ids = {
        name: uuid.uuid4()
        for name in ("visitor_id", "visit_id", "tenant_id", "company_id", "card_id")
    }
    token, _ = issue_visitor_token(
        signing_key="x" * 32,
        issuer="test",
        ttl_seconds=600,
        **ids,
    )

    with pytest.raises(VisitorTokenError):
        decode_visitor_token(token, signing_key="y" * 32, issuer="test")


def test_profile_link_token_is_signed_and_company_scoped() -> None:
    ids = {
        name: uuid.uuid4()
        for name in ("visitor_id", "tenant_id", "company_id", "consent_id")
    }
    token, _ = issue_profile_link_token(
        signing_key="x" * 32, issuer="test", ttl_seconds=86_400, **ids
    )
    principal = decode_profile_link_token(
        token, signing_key="x" * 32, issuer="test"
    )
    assert principal.company_id == ids["company_id"]
    assert principal.consent_id == ids["consent_id"]
    with pytest.raises(ProfileLinkTokenError):
        decode_profile_link_token(
            token + "tampered", signing_key="x" * 32, issuer="test"
        )

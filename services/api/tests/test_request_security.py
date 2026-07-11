from __future__ import annotations

from starlette.requests import Request

from app.core.config import Settings
from app.core.request_security import (
    account_subject_hash,
    request_ip_hash,
    trusted_client_ip,
)


def _request(peer: str, forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 443),
            "server": ("api.example.test", 443),
        }
    )


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "field_encryption_key": "field-encryption-secret-material-v1",
    }
    values.update(overrides)
    return Settings(**values)


def test_untrusted_peer_cannot_spoof_forwarded_client_ip() -> None:
    request = _request("198.51.100.8", "203.0.113.5")

    assert trusted_client_ip(request, ["10.0.0.0/8"]) == "198.51.100.8"


def test_trusted_proxy_chain_selects_first_untrusted_address_from_the_right() -> None:
    request = _request("10.0.0.2", "203.0.113.5, 10.0.0.1")

    assert trusted_client_ip(request, ["10.0.0.0/8"]) == "203.0.113.5"


def test_rate_limit_and_audit_subjects_are_keyed_hashes_not_raw_identifiers() -> None:
    settings = _settings()
    request = _request("203.0.113.5")

    ip_digest = request_ip_hash(request, settings)
    account_digest = account_subject_hash(settings, " Admin@Example.TEST ")

    assert len(ip_digest) == len(account_digest) == 64
    assert "203.0.113.5" not in ip_digest
    assert "admin@example.test" not in account_digest
    assert account_digest == account_subject_hash(settings, "admin@example.test")

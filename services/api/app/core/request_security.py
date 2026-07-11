from __future__ import annotations

import json
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from starlette.requests import Request

from app.core.config import Settings
from app.core.pii import PiiCipher


def trusted_client_ip(request: Request, trusted_proxy_cidrs: list[str]) -> str:
    """Resolve the client IP without trusting caller-controlled headers by default."""

    raw_peer = request.client.host if request.client else ""
    peer = _parse_ip(raw_peer)
    if peer is None:
        return "unknown"
    networks = tuple(ip_network(item, strict=False) for item in trusted_proxy_cidrs)
    if not networks or not _is_trusted(peer, networks):
        return str(peer)

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return str(peer)
    chain: list[IPv4Address | IPv6Address] = []
    for item in forwarded.split(","):
        parsed = _parse_ip(item)
        if parsed is None:
            return str(peer)
        chain.append(parsed)
    chain.append(peer)
    for candidate in reversed(chain):
        if not _is_trusted(candidate, networks):
            return str(candidate)
    return str(chain[0])


def security_subject_hash(settings: Settings, namespace: str, *values: object) -> str:
    serialized = json.dumps(
        [namespace, *(str(value) for value in values)],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return PiiCipher.from_settings(settings).hmac(serialized)


def account_subject_hash(settings: Settings, account: str) -> str:
    normalized = " ".join(account.strip().casefold().split())[:200]
    return security_subject_hash(settings, "staff-account", normalized)


def request_ip_hash(request: Request, settings: Settings) -> str:
    return security_subject_hash(
        settings,
        "request-ip",
        trusted_client_ip(request, settings.trusted_proxy_cidrs),
    )


def _parse_ip(value: str) -> IPv4Address | IPv6Address | None:
    candidate = value.strip().strip('"')
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1 and "." in candidate:
        host, _, port = candidate.partition(":")
        if port.isdigit():
            candidate = host
    try:
        return ip_address(candidate)
    except ValueError:
        return None


def _is_trusted(
    address: IPv4Address | IPv6Address,
    networks: tuple[object, ...],
) -> bool:
    return any(address.version == network.version and address in network for network in networks)  # type: ignore[union-attr,operator]


__all__ = [
    "account_subject_hash",
    "request_ip_hash",
    "security_subject_hash",
    "trusted_client_ip",
]

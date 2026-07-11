from __future__ import annotations

import re
from dataclasses import dataclass

_REDACTED_CREDENTIAL = "[已移除敏感凭证]"
_REDACTED_EMAIL = "[已移除邮箱]"
_REDACTED_PHONE = "[已移除手机号]"
_REDACTED_ID = "[已移除证件号]"
_REDACTED_WECHAT = "[已移除微信号]"

_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.IGNORECASE | re.DOTALL,
        ),
        _REDACTED_CREDENTIAL,
    ),
    (
        "authorization",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
        _REDACTED_CREDENTIAL,
    ),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:password|passwd|pwd|api[ _-]?key|secret|access[ _-]?token|"
            r"refresh[ _-]?token)\s*[:=：]\s*[^\s,;，；]{4,}",
            re.IGNORECASE,
        ),
        _REDACTED_CREDENTIAL,
    ),
    (
        "provider_token",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|"
            r"gh[pousr]_[A-Za-z0-9]{20,})\b"
        ),
        _REDACTED_CREDENTIAL,
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        _REDACTED_CREDENTIAL,
    ),
    (
        "email",
        re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
        _REDACTED_EMAIL,
    ),
    (
        "identity_number",
        re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
        _REDACTED_ID,
    ),
    (
        "mobile_phone",
        re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d(?:[ -]?\d){8}(?!\d)"),
        _REDACTED_PHONE,
    ),
    (
        "wechat",
        re.compile(
            r"(?:微信|wechat|weixin|wx)\s*(?:号|id)?\s*[:：=]?\s*[A-Za-z][A-Za-z0-9_-]{5,19}",
            re.IGNORECASE,
        ),
        _REDACTED_WECHAT,
    ),
)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    content: str
    redacted: bool
    categories: tuple[str, ...]


def redact_sensitive_text(value: str) -> RedactionResult:
    content = value
    categories: list[str] = []
    for category, pattern, replacement in _RULES:
        content, count = pattern.subn(replacement, content)
        if count:
            categories.append(category)
    return RedactionResult(
        content=content,
        redacted=bool(categories),
        categories=tuple(categories),
    )


__all__ = ["RedactionResult", "redact_sensitive_text"]

from __future__ import annotations

from app.core.redaction import redact_sensitive_text


def test_credentials_and_contact_pii_are_removed_before_downstream_use() -> None:
    raw = (
        "请帮我看看 sk-testonly0123456789abcdefABCDEF，"
        "邮箱 alice@example.test，手机 13800138000，微信 alice_wechat。"
    )

    result = redact_sensitive_text(raw)

    assert result.redacted
    assert set(result.categories) >= {"provider_token", "email", "mobile_phone", "wechat"}
    for secret in (
        "sk-testonly0123456789abcdefABCDEF",
        "alice@example.test",
        "13800138000",
        "alice_wechat",
    ):
        assert secret not in result.content
    assert "[已移除敏感凭证]" in result.content
    assert "[已移除邮箱]" in result.content
    assert "[已移除手机号]" in result.content
    assert "[已移除微信号]" in result.content
    assert all(fragment not in result.content for fragment in ("宸茬Щ", "闄ゆ晱", "锛"))


def test_private_keys_jwts_and_password_assignments_are_removed() -> None:
    raw = (
        "password=hunter2\n"
        "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturepart\n"
        "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
    )

    result = redact_sensitive_text(raw)

    assert result.redacted
    assert "hunter2" not in result.content
    assert "eyJhbGci" not in result.content
    assert "abc123" not in result.content


def test_normal_business_question_is_not_modified() -> None:
    value = "你们的实施周期、服务范围和报价方式是什么？"

    result = redact_sensitive_text(value)

    assert result.content == value
    assert not result.redacted
    assert result.categories == ()

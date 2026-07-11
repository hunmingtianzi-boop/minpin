from __future__ import annotations

from app.core.logging import _redact_secrets


def test_auth_cookie_and_csrf_values_are_redacted_from_structured_events() -> None:
    event = {
        "cookie": "cf_staff_refresh=raw-refresh-token",
        "refresh_token": "raw-refresh-token",
        "csrf_token": "raw-csrf-token",
        "x_csrf_token": "raw-csrf-token",
        "event": "safe-event-name",
    }

    redacted = _redact_secrets(None, "info", event)

    assert redacted["event"] == "safe-event-name"
    assert all(
        redacted[key] == "[REDACTED]"
        for key in ("cookie", "refresh_token", "csrf_token", "x_csrf_token")
    )
    assert "raw-refresh-token" not in repr(redacted)
    assert "raw-csrf-token" not in repr(redacted)

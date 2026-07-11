from __future__ import annotations

import pytest

from app.cli.bootstrap_platform_admin import PlatformBootstrapInput


def test_platform_bootstrap_requires_explicit_confirmation_and_wraps_password() -> None:
    with pytest.raises(ValueError):
        PlatformBootstrapInput(
            _env_file=None,
            tenant_slug="template",
            account="platform@example.test",
            password="A-secure-platform-password",  # noqa: S106
        )

    configured = PlatformBootstrapInput(
        _env_file=None,
        tenant_slug="template",
        account=" platform@example.test ",
        password="A-secure-platform-password",  # noqa: S106
        display_name=" 平台管理员 ",
        confirm="CREATE_FIRST_PLATFORM_ADMIN",
    )

    assert configured.account == "platform@example.test"
    assert configured.display_name == "平台管理员"
    assert "A-secure" not in repr(configured.password)


def test_platform_bootstrap_rejects_ambiguous_or_unsafe_input() -> None:
    with pytest.raises(ValueError):
        PlatformBootstrapInput(
            _env_file=None,
            tenant_slug="../other-tenant",
            account="platform@example.test",
            password="A-secure-platform-password",  # noqa: S106
            confirm="CREATE_FIRST_PLATFORM_ADMIN",
        )

    with pytest.raises(ValueError):
        PlatformBootstrapInput(
            _env_file=None,
            tenant_slug="template",
            account="platform@example.test",
            password="short",  # noqa: S106
            confirm="CREATE_FIRST_PLATFORM_ADMIN",
        )

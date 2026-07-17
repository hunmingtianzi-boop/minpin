from __future__ import annotations

import pytest

from app.core.config import Settings


def test_empty_provider_secrets_are_treated_as_unconfigured() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_api_key="",
        embedding_provider=None,
        embedding_base_url=None,
        embedding_api_key="",
        embedding_model=None,
    )

    assert settings.llm_api_key is None
    assert settings.embedding_api_key is None


def test_empty_embedding_settings_are_treated_as_unconfigured() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        embedding_provider="  ",
        embedding_base_url="",
        embedding_model="\t",
    )

    assert settings.embedding_provider is None
    assert settings.embedding_base_url is None
    assert settings.embedding_model is None


def test_production_subpath_settings_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        asgi_root_path="c/",
        api_docs_enabled=True,
    )

    assert settings.asgi_root_path == "/c"
    assert settings.api_docs_enabled is True


def test_public_card_base_is_an_origin_and_remote_http_requires_opt_in() -> None:
    with pytest.raises(ValueError, match="without /c"):
        Settings(
            _env_file=None,
            app_env="test",
            public_card_base_url="https://cards.example.test/c",
        )

    with pytest.raises(ValueError, match="ALLOW_INSECURE_PUBLIC_CARD_HTTP"):
        Settings(
            _env_file=None,
            app_env="test",
            public_card_base_url="http://47.83.235.176",
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        public_card_base_url="http://47.83.235.176/",
        allow_insecure_public_card_http=True,
    )
    assert settings.public_card_base_url == "http://47.83.235.176"


def test_staff_bootstrap_settings_are_all_or_none_and_secret_wrapped() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        Settings(
            _env_file=None,
            app_env="test",
            admin_bootstrap_tenant_slug="tuotu",
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        admin_bootstrap_tenant_slug="tuotu",
        admin_bootstrap_account="admin@example.test",
        admin_bootstrap_password="a-strong-bootstrap-password",  # noqa: S106
    )

    assert settings.admin_bootstrap_password is not None
    assert "a-strong" not in repr(settings.admin_bootstrap_password)
    assert settings.refresh_token_ttl_seconds > settings.access_token_ttl_seconds


def test_production_requires_secure_auth_cookies_and_explicit_origins() -> None:
    production: dict[str, object] = {
        "_env_file": None,
        "app_env": "production",
        "jwt_signing_key": "j" * 32,
        "field_encryption_key": "production-field-encryption-secret",
        "field_encryption_key_ref": "kms/pii/v1",
        "llm_api_key": "provider-key",
        "metrics_bearer_token": "metrics-secret",
        "llm_input_price_cny_per_million": 1,
        "llm_output_price_cny_per_million": 1,
    }

    with pytest.raises(ValueError, match="STAFF_AUTH_COOKIE_SECURE"):
        Settings(**production, staff_auth_cookie_secure=False)

    with pytest.raises(ValueError, match="wildcard origin"):
        Settings(
            **production,
            staff_auth_cookie_secure=True,
            cors_allowed_origins=["*"],
        )

    temporary_ip_public_card = Settings(
        **production,
        staff_auth_cookie_secure=True,
        public_card_base_url="http://47.83.235.176",
        allow_insecure_public_card_http=True,
    )
    assert temporary_ip_public_card.staff_auth_cookie_secure is True
    assert temporary_ip_public_card.allow_insecure_public_card_http is True

    with pytest.raises(ValueError, match="STAFF_AUTH_COOKIE_SECURE"):
        Settings(
            **production,
            staff_auth_cookie_secure=False,
            public_card_base_url="http://47.83.235.176",
            allow_insecure_public_card_http=True,
        )

    settings = Settings(**production, staff_auth_cookie_secure=True)
    assert settings.staff_auth_cookie_secure is True


def test_staging_requires_metrics_authentication() -> None:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "jwt_signing_key": "j" * 32,
        "field_encryption_key": "e" * 32,
        "field_encryption_key_ref": "kms/pii/staging-v1",
        "llm_api_key": "provider-key",
        "llm_input_price_cny_per_million": 1,
        "llm_output_price_cny_per_million": 1,
    }

    with pytest.raises(ValueError, match="METRICS_BEARER_TOKEN"):
        Settings(**values)

from __future__ import annotations

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

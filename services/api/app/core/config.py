from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets stay wrapped in ``SecretStr`` so accidental model dumps and log calls
    cannot reveal provider or signing keys.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "cf-ai-card"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:4173", "http://localhost:4173"]
    )

    database_url: str = (
        "postgresql+asyncpg://cf_ai_card_app:change-me-app-local-only@localhost:5432/cf_ai_card"
    )
    migration_database_url: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_statement_timeout_ms: int = Field(default=8_000, ge=500, le=60_000)
    redis_url: str = "redis://localhost:6379/0"

    jwt_signing_key: SecretStr = SecretStr("replace-with-at-least-32-random-bytes")
    visitor_token_ttl_seconds: int = Field(default=7_200, ge=300, le=86_400)
    access_token_ttl_seconds: int = Field(default=900, ge=300, le=3_600)

    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr | None = None
    llm_model: str = "deepseek-v4-flash"
    llm_thinking: Literal["enabled", "disabled"] = "disabled"
    llm_reasoning_effort: Literal["high", "max"] = "high"
    llm_timeout_seconds: float = Field(default=30.0, ge=2, le=120)
    llm_max_output_tokens: int = Field(default=1_000, ge=128, le=8_192)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_concurrency: int = Field(default=20, ge=1, le=500)
    llm_queue_timeout_seconds: float = Field(default=3.0, ge=0.1, le=30)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_input_price_cny_per_million: float = Field(default=0.0, ge=0)
    llm_output_price_cny_per_million: float = Field(default=0.0, ge=0)

    embedding_provider: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimension: int = Field(default=1_024, ge=64, le=4_096)
    embedding_timeout_seconds: float = Field(default=20.0, ge=2, le=120)

    retrieval_top_k: int = Field(default=8, ge=1, le=30)
    retrieval_context_k: int = Field(default=5, ge=1, le=10)
    retrieval_vector_weight: float = Field(default=0.65, ge=0, le=1)
    retrieval_min_vector_score: float = Field(default=0.55, ge=-1, le=1)
    retrieval_min_lexical_score: float = Field(default=0.08, ge=0, le=1)

    public_chat_rate_limit_per_minute: int = Field(default=10, ge=1, le=300)
    max_message_chars: int = Field(default=2_000, ge=100, le=10_000)
    max_conversation_messages: int = Field(default=30, ge=2, le=200)
    model_daily_budget_cny: float = Field(default=100.0, gt=0)

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("llm_api_key", "embedding_api_key", mode="before")
    @classmethod
    def empty_secret_is_unconfigured(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            signing_key = self.jwt_signing_key.get_secret_value()
            if signing_key.startswith("replace-") or len(signing_key) < 32:
                raise ValueError(
                    "JWT_SIGNING_KEY must be a strong secret outside local development"
                )
            if not self.llm_api_key:
                raise ValueError("LLM_API_KEY is required outside local development")
            if (
                self.llm_input_price_cny_per_million <= 0
                or self.llm_output_price_cny_per_million <= 0
            ):
                raise ValueError("LLM token prices must be configured outside local development")
        if self.embedding_provider and not (
            self.embedding_base_url and self.embedding_api_key and self.embedding_model
        ):
            raise ValueError(
                "EMBEDDING_BASE_URL, EMBEDDING_API_KEY and EMBEDDING_MODEL are required "
                "when EMBEDDING_PROVIDER is enabled"
            )
        if self.llm_thinking == "enabled" and self.llm_temperature != 0.1:
            # DeepSeek V4 ignores sampling temperature in thinking mode. Rejecting a
            # misleading production configuration is safer than silently accepting it.
            raise ValueError("LLM_TEMPERATURE must remain at its neutral default in thinking mode")
        if self.retrieval_context_k > self.retrieval_top_k:
            raise ValueError("RETRIEVAL_CONTEXT_K cannot exceed RETRIEVAL_TOP_K")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

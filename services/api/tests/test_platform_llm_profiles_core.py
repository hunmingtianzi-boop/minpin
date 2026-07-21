from __future__ import annotations

import socket
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import PlatformLLMProfile
from app.services import platform_llm_profiles as llm_module
from app.services.platform_llm_profiles import (
    EffectiveChatConfig,
    LLMRuntimeUnavailable,
    PlatformLLMActor,
    PlatformLLMProfileService,
    UpdateProfileInput,
    database_chat_config,
    key_hint,
    probe_openai_models,
    validate_provider_base_url,
)


def _settings(**updates: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "app_env": "test",
        "field_encryption_key": "test-field-encryption-material-32-bytes",
        "field_encryption_key_ref": "test/platform-llm/v1",
        "llm_api_key": "environment-placeholder-token",
    }
    values.update(updates)
    return Settings(**values)


def _profile(
    settings: Settings,
    *,
    enabled: bool = True,
    allow_general_answers: bool = True,
    faq_fast_path_enabled: bool = True,
) -> PlatformLLMProfile:
    cipher = PiiCipher.from_settings(settings)
    placeholder_token = "database-placeholder-token"  # noqa: S105 - inert test value
    return PlatformLLMProfile(
        id=uuid.uuid4(),
        name="默认主配置",
        purpose="chat_main",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        api_key_ciphertext=cipher.encrypt(placeholder_token),
        api_key_key_ref=cipher.key_ref,
        api_key_hint=key_hint(placeholder_token),
        model="model-a",
        thinking="disabled",
        reasoning_effort=None,
        timeout_seconds=Decimal("12.0"),
        max_retries=1,
        max_concurrency=20,
        max_output_tokens=1000,
        temperature=Decimal("0.1"),
        daily_budget_cny=Decimal("88.50"),
        input_price_cny_per_million=Decimal("1.5"),
        output_price_cny_per_million=Decimal("6"),
        allow_general_answers=allow_general_answers,
        faq_fast_path_enabled=faq_fast_path_enabled,
        enabled=enabled,
        is_active=True,
        version=3,
        last_test_status="untested",
        last_test_latency_ms=None,
        last_tested_at=None,
        updated_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _actor(role: str = "platform_admin") -> PlatformLLMActor:
    return PlatformLLMActor(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role=role,
    )


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, row: PlatformLLMProfile | None) -> None:
        self.row = row

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction()

    async def scalar(self, _statement: object) -> PlatformLLMProfile | None:
        return self.row

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def add(self, value: PlatformLLMProfile) -> None:
        self.row = value

    async def flush(self) -> None:
        return None

    async def refresh(self, _value: object) -> None:
        return None


class _Factory:
    def __init__(self, row: PlatformLLMProfile | None) -> None:
        self.session = _Session(row)

    def __call__(self) -> _Session:
        return self.session


class _SequenceSession(_Session):
    def __init__(self, values: list[object]) -> None:
        super().__init__(None)
        self.values = values

    async def scalar(self, _statement: object) -> object | None:
        return self.values.pop(0) if self.values else None


class _SequenceFactory:
    def __init__(self, values: list[object]) -> None:
        self.session = _SequenceSession(values)

    def __call__(self) -> _SequenceSession:
        return self.session


def test_model_contract_has_no_plaintext_key_and_enforces_one_active_index() -> None:
    columns = PlatformLLMProfile.__table__.columns
    index_names = {index.name for index in PlatformLLMProfile.__table__.indexes}

    assert "api_key" not in columns
    assert "api_key_ciphertext" in columns
    assert "api_key_hint" in columns
    assert "api_key_key_ref" in columns
    assert {
        "purpose",
        "thinking",
        "max_concurrency",
        "max_output_tokens",
        "temperature",
        "input_price_cny_per_million",
        "output_price_cny_per_million",
        "allow_general_answers",
        "faq_fast_path_enabled",
        "last_test_status",
        "last_test_latency_ms",
        "last_tested_at",
    } <= set(columns.keys())
    assert columns["reasoning_effort"].nullable is True
    assert "uq_platform_llm_profiles_one_active" in index_names
    assert "uq_platform_llm_profiles_name_normalized" in index_names


def test_migration_is_clean_after_current_head_and_refuses_secret_destroying_downgrade() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations/versions/20260715_0016_platform_llm_profiles.py"
    ).read_text(encoding="utf-8").casefold()

    assert 'down_revision: str | none = "20260715_0015"' in migration
    assert "deferrable initially deferred" in migration
    assert "uq_platform_llm_profiles_one_active" in migration
    assert "enable row level security" in migration
    assert "grant select, insert, update" in migration
    assert "grant delete" not in migration
    assert "refusing to drop platform_llm_profiles" in migration
    assert "api_key varchar" not in migration


def test_behavior_controls_migration_defaults_existing_profiles_to_strict_mode() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations/versions/20260717_0023_platform_llm_behavior_controls.py"
    ).read_text(encoding="utf-8").casefold()

    assert 'down_revision: str | none = "20260717_0022"' in migration
    assert "allow_general_answers" in migration
    assert "faq_fast_path_enabled" in migration
    assert migration.count("server_default=sa.false()") == 2


def test_database_config_decrypts_without_exposing_secret_in_repr_and_fails_closed() -> None:
    settings = _settings()
    row = _profile(settings)

    runtime = database_chat_config(row, settings=settings)

    assert runtime.source == "database"
    assert runtime.allow_general_answers is True
    assert runtime.faq_fast_path_enabled is True
    request_settings = runtime.apply_to_settings(settings)
    assert request_settings.llm_allow_general_answers is True
    assert request_settings.rag_faq_fast_path_enabled is True
    assert runtime.api_key.get_secret_value() == "database-placeholder-token"
    assert "database-placeholder-token" not in repr(runtime)
    assert "environment-placeholder-token" not in repr(runtime)

    row.enabled = False
    with pytest.raises(LLMRuntimeUnavailable) as disabled:
        database_chat_config(row, settings=settings)
    assert disabled.value.code == "configuration_disabled"

    row.enabled = True
    row.api_key_ciphertext = b"invalid-ciphertext"
    with pytest.raises(LLMRuntimeUnavailable) as invalid:
        database_chat_config(row, settings=settings)
    assert invalid.value.code == "configuration_invalid"


def test_key_hint_reveals_only_last_four_characters() -> None:
    assert key_hint("sk-example-123456") == "••••3456"
    assert key_hint("abc") == "••••"
    assert key_hint("   ") == ""

    create = llm_module.CreateProfileInput(
        name="安全配置",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        api_key="repr-placeholder-token",
        model="model-a",
    )
    update = UpdateProfileInput(
        name=create.name,
        provider=create.provider,
        base_url=create.base_url,
        api_key="update-repr-placeholder-token",
        model=create.model,
        expected_version=1,
    )
    assert "repr-placeholder-token" not in repr(create)
    assert "update-repr-placeholder-token" not in repr(update)


def test_provider_url_rejects_credentials_query_fragment_and_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public_dns(
        hostname: str,
        port: int,
        **_kwargs: object,
    ) -> list[tuple[object, ...]]:
        assert hostname == "api.example.test"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(llm_module.socket, "getaddrinfo", public_dns)
    assert (
        validate_provider_base_url(
            "https://api.example.test/v1/",
            app_env="production",
        )
        == "https://api.example.test/v1"
    )
    for value in (
        "http://api.example.test/v1",
        "https://user:pass@api.example.test/v1",
        "https://api.example.test/v1?debug=1",
        "https://api.example.test/v1#fragment",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest",
    ):
        with pytest.raises(ValueError):
            validate_provider_base_url(value, app_env="production")


class _UnreadableStream(httpx.AsyncByteStream):
    async def __aiter__(self):  # type: ignore[override]
        raise AssertionError("provider response body must not be consumed")
        yield b"unreachable"

    async def aclose(self) -> None:
        return None


async def test_models_probe_is_single_bounded_streaming_request_and_secret_safe() -> None:
    requests: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer database-placeholder-token"
        return httpx.Response(200, stream=_UnreadableStream())

    config = EffectiveChatConfig(
        profile_id=uuid.uuid4(),
        profile_name="主配置",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        api_key=SecretStr("database-placeholder-token"),
        model="model-a",
        thinking="disabled",
        reasoning_effort="high",
        timeout_seconds=4,
        max_retries=0,
        max_concurrency=20,
        max_output_tokens=1000,
        temperature=0.1,
        daily_budget_cny=10,
        input_price_cny_per_million=0,
        output_price_cny_per_million=0,
        allow_general_answers=False,
        faq_fast_path_enabled=True,
        enabled=True,
        source="database",
        version=2,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        result = await probe_openai_models(client, config)

    assert result.ok is True
    assert result.profile_id == config.profile_id
    assert result.tested_version == 2
    assert result.error_code is None
    assert len(requests) == 1
    assert "database-placeholder-token" not in repr(result)


async def test_temporary_probe_key_updates_status_without_persisting_or_auditing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    row = _profile(settings)
    original_ciphertext = row.api_key_ciphertext
    temporary = "temporary-probe-placeholder-token"
    audit_payloads: list[dict[str, object]] = []

    async def no_scope(*_args: object, **_kwargs: object) -> None:
        return None

    async def capture_audit(*_args: object, **kwargs: object) -> None:
        audit_payloads.append(dict(kwargs["event_data"]))  # type: ignore[arg-type]

    async def provider(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {temporary}"
        return httpx.Response(200, stream=_UnreadableStream())

    monkeypatch.setattr(llm_module, "set_rls_context", no_scope)
    monkeypatch.setattr(llm_module, "append_audit", capture_audit)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        service = PlatformLLMProfileService(
            _Factory(row),  # type: ignore[arg-type]
            settings,
            client,
        )
        result = await service.test_profile_connection(
            actor=_actor(),
            profile_id=row.id,
            api_key_override=SecretStr(temporary),
            trace_id="temporary-key-probe",
        )

    assert result.ok is True
    assert row.api_key_ciphertext == original_ciphertext
    assert row.last_test_status == "succeeded"
    assert row.last_test_latency_ms is not None
    assert row.last_tested_at is not None
    assert temporary not in repr(audit_payloads)


async def test_blank_key_update_preserves_ciphertext_and_stale_version_is_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    row = _profile(settings)
    original_ciphertext = row.api_key_ciphertext
    original_hint = row.api_key_hint

    async def no_scope(*_args: object, **_kwargs: object) -> None:
        return None

    async def no_audit(*_args: object, **_kwargs: object) -> None:
        return None

    async def no_duplicate(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(llm_module, "set_rls_context", no_scope)
    monkeypatch.setattr(llm_module, "append_audit", no_audit)
    async with httpx.AsyncClient() as client:
        service = PlatformLLMProfileService(
            _Factory(row),  # type: ignore[arg-type]
            settings,
            client,
        )
        monkeypatch.setattr(service, "_name_exists", no_duplicate)
        view = await service.update_profile(
            actor=_actor(),
            profile_id=row.id,
            body=UpdateProfileInput(
                name="更新后的主配置",
                provider="openai_compatible",
                base_url="https://provider.example.test/v2",
                api_key="   ",
                model="model-b",
                thinking="enabled",
                reasoning_effort="max",
                timeout_seconds=20,
                max_retries=2,
                max_concurrency=40,
                max_output_tokens=2000,
                temperature=0.1,
                daily_budget_cny=120,
                input_price_cny_per_million=2,
                output_price_cny_per_million=8,
                allow_general_answers=False,
                faq_fast_path_enabled=True,
                enabled=True,
                expected_version=3,
            ),
            trace_id="safe-trace",
        )

        assert row.api_key_ciphertext == original_ciphertext
        assert row.api_key_hint == original_hint
        assert row.version == 4
        assert view.key_configured is True
        assert view.allow_general_answers is False
        assert view.faq_fast_path_enabled is True
        assert not hasattr(view, "api_key")
        assert "database-placeholder-token" not in repr(view)

        with pytest.raises(ApiError) as stale:
            await service.update_profile(
                actor=_actor(),
                profile_id=row.id,
                body=UpdateProfileInput(
                    name=row.name,
                    provider=row.provider,
                    base_url=row.base_url,
                    model=row.model,
                    expected_version=3,
                ),
                trace_id="stale-trace",
            )
    assert stale.value.status_code == 409
    assert stale.value.code == "LLM_PROFILE_VERSION_CONFLICT"


async def test_create_encrypts_key_and_audit_payload_is_secret_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    factory = _Factory(None)
    audit_payloads: list[dict[str, object]] = []

    async def no_scope(*_args: object, **_kwargs: object) -> None:
        return None

    async def capture_audit(*_args: object, **kwargs: object) -> None:
        audit_payloads.append(dict(kwargs["event_data"]))  # type: ignore[arg-type]

    monkeypatch.setattr(llm_module, "set_rls_context", no_scope)
    monkeypatch.setattr(llm_module, "append_audit", capture_audit)
    async with httpx.AsyncClient() as client:
        service = PlatformLLMProfileService(
            factory,  # type: ignore[arg-type]
            settings,
            client,
        )
        view = await service.create_profile(
            actor=_actor(),
            body=llm_module.CreateProfileInput(
                name="生产主配置",
                provider="openai_compatible",
                base_url="https://provider.example.test/v1",
                api_key="new-database-placeholder-token",
                model="model-main",
                allow_general_answers=True,
                faq_fast_path_enabled=True,
            ),
            trace_id="create-safe",
        )

    row = factory.session.row
    assert row is not None
    assert row.is_active is True
    assert row.allow_general_answers is True
    assert row.faq_fast_path_enabled is True
    assert view.allow_general_answers is True
    assert view.faq_fast_path_enabled is True
    assert row.api_key_ciphertext is not None
    assert b"new-database-placeholder-token" not in row.api_key_ciphertext
    assert PiiCipher.from_settings(settings).decrypt(row.api_key_ciphertext) == (
        "new-database-placeholder-token"
    )
    assert view.key_hint == "••••oken"
    assert not hasattr(view, "api_key")
    assert "new-database-placeholder-token" not in repr(view)
    assert "new-database-placeholder-token" not in repr(audit_payloads)


async def test_activation_checks_seen_active_id_and_switches_exactly_one_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    current = _profile(settings)
    target = _profile(settings)
    current.name = "当前配置"
    target.name = "备用配置"
    target.is_active = False
    target.version = 7

    async def no_scope(*_args: object, **_kwargs: object) -> None:
        return None

    async def no_audit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(llm_module, "set_rls_context", no_scope)
    monkeypatch.setattr(llm_module, "append_audit", no_audit)
    async with httpx.AsyncClient() as client:
        service = PlatformLLMProfileService(
            _SequenceFactory([target, current]),  # type: ignore[arg-type]
            settings,
            client,
        )
        view = await service.activate_profile(
            actor=_actor(),
            profile_id=target.id,
            body=llm_module.ActivateProfileInput(
                expected_version=7,
                expected_active_profile_id=current.id,
            ),
            trace_id="activate-safe",
        )

    assert current.is_active is False
    assert current.version == 4
    assert target.is_active is True
    assert target.version == 8
    assert view.id == target.id

    async with httpx.AsyncClient() as client:
        conflict_service = PlatformLLMProfileService(
            _SequenceFactory([target, current]),  # type: ignore[arg-type]
            settings,
            client,
        )
        with pytest.raises(ApiError) as conflict:
            await conflict_service.activate_profile(
                actor=_actor(),
                profile_id=target.id,
                body=llm_module.ActivateProfileInput(
                    expected_version=target.version,
                    expected_active_profile_id=uuid.uuid4(),
                ),
                trace_id="stale-active",
            )
    assert conflict.value.code == "LLM_ACTIVE_PROFILE_CONFLICT"


async def test_resolver_uses_environment_only_for_zero_database_profiles() -> None:
    settings = _settings()
    environment = await llm_module.resolve_effective_chat_config(
        _SequenceFactory([None]),  # type: ignore[arg-type]
        settings,
    )
    assert environment.source == "environment"

    inactive = _profile(settings)
    inactive.is_active = False
    with pytest.raises(LLMRuntimeUnavailable) as corrupted:
        await llm_module.resolve_effective_chat_config(
            _SequenceFactory([inactive]),  # type: ignore[arg-type]
            settings,
        )
    assert corrupted.value.code == "active_configuration_missing"


async def test_non_platform_actor_is_rejected_before_database_access() -> None:
    async with httpx.AsyncClient() as client:
        service = PlatformLLMProfileService(
            None,  # type: ignore[arg-type]
            _settings(),
            client,
        )
        with pytest.raises(ApiError) as captured:
            await service.list_profiles(actor=_actor("company_admin"))
    assert captured.value.status_code == 403
    assert captured.value.code == "FORBIDDEN"

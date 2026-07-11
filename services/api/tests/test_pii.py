from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.core.pii import (
    PiiCipher,
    PiiCipherError,
    mask_email,
    mask_name,
    mask_phone,
    mask_wechat,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "field_encryption_key": "field-encryption-secret-material-v1",
        "field_encryption_key_ref": "kms/pii/v1",
    }
    values.update(overrides)
    return Settings(**values)


def test_aes_gcm_round_trip_is_randomized_authenticated_and_secret_safe() -> None:
    cipher = PiiCipher.from_settings(_settings())

    first = cipher.encrypt("13800138000")
    second = cipher.encrypt("13800138000")

    assert first != second
    assert cipher.decrypt(first) == "13800138000"
    assert cipher.key_ref == "kms/pii/v1"
    assert "field-encryption-secret" not in repr(cipher)

    tampered = first[:-1] + bytes((first[-1] ^ 1,))
    with pytest.raises(PiiCipherError, match="authentication failed"):
        cipher.decrypt(tampered)


def test_search_hmac_is_keyed_deterministic_and_domain_separated() -> None:
    first = PiiCipher.from_settings(_settings())
    second = PiiCipher.from_settings(
        _settings(field_encryption_key="different-field-encryption-secret-v1")
    )

    digest = first.hmac("normalized@example.test")

    assert len(digest) == 64
    assert digest == first.hmac("normalized@example.test")
    assert digest != second.hmac("normalized@example.test")
    assert "normalized@example.test" not in digest


def test_key_rotation_decrypts_retired_ciphertext_without_using_old_key_for_writes() -> None:
    old = PiiCipher.from_settings(
        _settings(
            field_encryption_key="old-field-encryption-secret-material",
            field_encryption_key_ref="kms/pii/v0",
        )
    )
    old_payload = old.encrypt("历史数据")
    rotated = PiiCipher.from_settings(
        _settings(
            field_encryption_key="new-field-encryption-secret-material",
            field_encryption_key_ref="kms/pii/v1",
            field_encryption_previous_keys=json.dumps(
                {"kms/pii/v0": "old-field-encryption-secret-material"}
            ),
        )
    )

    assert rotated.decrypt(old_payload) == "历史数据"
    assert b"kms/pii/v1" in rotated.encrypt("新数据")


def test_mask_helpers_preserve_only_operationally_useful_fragments() -> None:
    assert mask_phone("+86 138-0013-8000") == "138****8000"
    assert mask_email("alice@example.test") == "a***@example.test"
    assert mask_wechat("alice_wechat") == "al***t"
    assert mask_name("张小明") == "张*明"


def test_production_rejects_placeholder_field_encryption_key() -> None:
    with pytest.raises(ValueError, match="FIELD_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_signing_key="j" * 32,
            field_encryption_key="replace-with-kms-backed-key",
            llm_api_key="provider-key",
            llm_input_price_cny_per_million=1,
            llm_output_price_cny_per_million=1,
        )

    with pytest.raises(ValueError, match="FIELD_ENCRYPTION_KEY_REF"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_signing_key="j" * 32,
            field_encryption_key="production-field-encryption-secret",
            field_encryption_key_ref="local-v1",
            llm_api_key="provider-key",
            llm_input_price_cny_per_million=1,
            llm_output_price_cny_per_million=1,
        )

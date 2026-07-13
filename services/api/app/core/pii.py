from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
import os
from dataclasses import dataclass, field
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

_MAGIC = b"CFPII"
_FORMAT_VERSION = 1
_NONCE_BYTES = 12
_TAG_BYTES = 16


class PiiCipherError(ValueError):
    """A deliberately non-specific field encryption error."""


@dataclass(frozen=True, slots=True)
class PiiCipher:
    """Versioned AES-GCM field encryption with a domain-separated search HMAC.

    Ciphertext embeds only the non-secret key reference, format version, nonce,
    and authenticated ciphertext. The source key is never returned or logged.
    """

    _encryption_key: bytes = field(repr=False)
    _hmac_key: bytes = field(repr=False)
    key_ref: str
    _decryption_keys: tuple[tuple[str, bytes], ...] = field(repr=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "PiiCipher":
        previous_keys: dict[str, str] = {}
        if settings.field_encryption_previous_keys is not None:
            try:
                loaded = json.loads(settings.field_encryption_previous_keys.get_secret_value())
            except json.JSONDecodeError as exc:
                raise PiiCipherError("previous field encryption keys are invalid") from exc
            if not isinstance(loaded, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in loaded.items()
            ):
                raise PiiCipherError("previous field encryption keys are invalid")
            previous_keys = loaded
        return cls.from_secret(
            settings.field_encryption_key.get_secret_value(),
            key_ref=settings.field_encryption_key_ref,
            previous_keys=previous_keys,
        )

    @classmethod
    def from_secret(
        cls,
        secret: str,
        *,
        key_ref: str,
        previous_keys: dict[str, str] | None = None,
    ) -> "PiiCipher":
        material = secret.encode("utf-8")
        if len(material) < 16:
            raise PiiCipherError("field encryption key is too short")
        encoded_ref = key_ref.encode("utf-8")
        if not encoded_ref or len(encoded_ref) > 128:
            raise PiiCipherError("field encryption key reference is invalid")
        encryption_key = _derive_encryption_key(material)
        search_key = hmac_module.new(
            material,
            b"cf-ai-card/field-encryption/search-hmac/v1",
            hashlib.sha256,
        ).digest()
        decryption_keys: list[tuple[str, bytes]] = [(key_ref, encryption_key)]
        for previous_ref, previous_secret in (previous_keys or {}).items():
            previous_material = previous_secret.encode("utf-8")
            if (
                not previous_ref
                or len(previous_ref.encode("utf-8")) > 128
                or len(previous_material) < 16
            ):
                raise PiiCipherError("previous field encryption keys are invalid")
            if previous_ref != key_ref:
                decryption_keys.append((previous_ref, _derive_encryption_key(previous_material)))
        return cls(encryption_key, search_key, key_ref, tuple(decryption_keys))

    def encrypt(self, value: str) -> bytes:
        return self.encrypt_bytes(value.encode("utf-8"))

    def encrypt_bytes(self, value: bytes) -> bytes:
        """Encrypt arbitrary bounded application data.

        Most PII columns carry text, but the knowledge-import queue also has to
        retain opaque office and image uploads until the worker consumes them.
        Keeping the byte API here avoids base64-expanding the file and preserves
        the same versioned key-rotation envelope as normal fields.
        """
        if not isinstance(value, bytes):
            raise TypeError("encrypted value must be bytes")
        encoded_ref = self.key_ref.encode("utf-8")
        header = _MAGIC + bytes((_FORMAT_VERSION, len(encoded_ref))) + encoded_ref
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(self._encryption_key).encrypt(
            nonce,
            value,
            header,
        )
        return header + nonce + ciphertext

    def decrypt(self, payload: bytes) -> str:
        try:
            return self.decrypt_bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PiiCipherError("encrypted field authentication failed") from exc

    def decrypt_bytes(self, payload: bytes) -> bytes:
        minimum = len(_MAGIC) + 2 + 1 + _NONCE_BYTES + _TAG_BYTES
        if not isinstance(payload, bytes) or len(payload) < minimum:
            raise PiiCipherError("encrypted field is invalid")
        if payload[: len(_MAGIC)] != _MAGIC:
            raise PiiCipherError("encrypted field is invalid")
        offset = len(_MAGIC)
        version = payload[offset]
        ref_length = payload[offset + 1]
        if version != _FORMAT_VERSION or ref_length == 0:
            raise PiiCipherError("encrypted field is invalid")
        header_end = offset + 2 + ref_length
        nonce_end = header_end + _NONCE_BYTES
        if len(payload) < nonce_end + _TAG_BYTES:
            raise PiiCipherError("encrypted field is invalid")
        try:
            payload_ref = payload[offset + 2 : header_end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PiiCipherError("encrypted field is invalid") from exc
        decryption_key = next(
            (
                key
                for reference, key in self._decryption_keys
                if hmac_module.compare_digest(payload_ref, reference)
            ),
            None,
        )
        if decryption_key is None:
            raise PiiCipherError("encrypted field key reference is unavailable")
        header = payload[:header_end]
        nonce = payload[header_end:nonce_end]
        ciphertext = payload[nonce_end:]
        try:
            return AESGCM(decryption_key).decrypt(nonce, ciphertext, header)
        except InvalidTag as exc:
            raise PiiCipherError("encrypted field authentication failed") from exc

    def hmac(self, value: str) -> str:
        return hmac_module.new(
            self._hmac_key,
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


def mask_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    if len(digits) >= 7:
        return f"{digits[:3]}{'*' * max(4, len(digits) - 7)}{digits[-4:]}"
    return mask_value(value)


def mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator or not local or not domain:
        return mask_value(value)
    return f"{local[0]}***@{domain}"


def mask_wechat(value: str) -> str:
    normalized = value.strip()
    if len(normalized) <= 2:
        return "*" * len(normalized)
    return f"{normalized[:2]}***{normalized[-1]}"


def mask_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) <= 1:
        return "*" if normalized else ""
    if len(normalized) == 2:
        return f"{normalized[0]}*"
    return f"{normalized[0]}{'*' * (len(normalized) - 2)}{normalized[-1]}"


def mask_value(
    value: str,
    kind: Literal["phone", "email", "wechat", "name", "generic"] = "generic",
) -> str:
    if kind == "phone":
        return mask_phone(value)
    if kind == "email":
        return mask_email(value)
    if kind == "wechat":
        return mask_wechat(value)
    if kind == "name":
        return mask_name(value)
    normalized = value.strip()
    if not normalized:
        return ""
    if len(normalized) == 1:
        return "*"
    return f"{normalized[0]}{'*' * max(3, len(normalized) - 2)}{normalized[-1]}"


def _derive_encryption_key(material: bytes) -> bytes:
    return hmac_module.new(
        material,
        b"cf-ai-card/field-encryption/aes-gcm/v1",
        hashlib.sha256,
    ).digest()


__all__ = [
    "PiiCipher",
    "PiiCipherError",
    "mask_email",
    "mask_name",
    "mask_phone",
    "mask_value",
    "mask_wechat",
]

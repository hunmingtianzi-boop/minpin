from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_SALT_BYTES = 16
SCRYPT_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_CHARS = 200
MAX_ACCOUNT_CHARS = 200


def normalize_staff_account(account: str) -> str:
    normalized = account.strip().casefold()
    if not 3 <= len(normalized) <= MAX_ACCOUNT_CHARS:
        raise ValueError("staff account length is invalid")
    if any(character.isspace() for character in normalized):
        raise ValueError("staff account must not contain whitespace")
    return normalized


def hash_staff_password(password: str, *, salt: bytes | None = None) -> str:
    if not MIN_PASSWORD_CHARS <= len(password) <= MAX_PASSWORD_CHARS:
        raise ValueError("staff password length is invalid")
    selected_salt = salt or secrets.token_bytes(SCRYPT_SALT_BYTES)
    if len(selected_salt) != SCRYPT_SALT_BYTES:
        raise ValueError("scrypt salt length is invalid")
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=selected_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _encode(selected_salt),
            _encode(digest),
        )
    )


def verify_staff_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        salt = _decode(raw_salt)
        expected = _decode(raw_digest)
        if len(salt) != SCRYPT_SALT_BYTES or len(expected) != SCRYPT_DKLEN:
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(candidate, expected)
    except (UnicodeError, ValueError):
        return False


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


# Unknown accounts still run the same expensive primitive as known accounts.
_DUMMY_PASSWORD_HASH = hash_staff_password(
    "not-a-real-staff-password",
    salt=b"cf-card-auth-v1!",
)


def verify_staff_password_or_dummy(password: str, encoded_hash: str | None) -> bool:
    return verify_staff_password(password, encoded_hash or _DUMMY_PASSWORD_HASH)


__all__ = [
    "MAX_ACCOUNT_CHARS",
    "MAX_PASSWORD_CHARS",
    "MIN_PASSWORD_CHARS",
    "hash_staff_password",
    "normalize_staff_account",
    "verify_staff_password",
    "verify_staff_password_or_dummy",
]

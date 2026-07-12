from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class TextIntegrityError(ValueError):
    """Raised when text contains evidence of a broken Unicode decode."""


def ensure_text_integrity(value: str) -> str:
    """Reject characters that cannot occur in clean user-authored UTF-8 text.

    The C1 control range is especially important here: UTF-8 bytes decoded as
    Latin-1 turn continuation bytes into these code points. Accepting that text
    makes the corruption permanent once it is encoded as valid UTF-8 again.
    """

    for character in value:
        codepoint = ord(character)
        if character == "\ufffd":
            raise TextIntegrityError("text contains a Unicode replacement character")
        if (codepoint < 0x20 and character not in {"\t", "\n", "\r"}) or (
            0x7F <= codepoint <= 0x9F
        ):
            raise TextIntegrityError("text contains a forbidden control character")
        if 0xD800 <= codepoint <= 0xDFFF:
            raise TextIntegrityError("text contains an unpaired Unicode surrogate")
    if _looks_like_utf8_decoded_as_latin1(value):
        raise TextIntegrityError("text appears to be UTF-8 decoded as Latin-1")
    return value


def _looks_like_utf8_decoded_as_latin1(value: str) -> bool:
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False
    return repaired != value and any(ord(character) > 0xFF for character in repaired)


def ensure_text_tree(value: Any) -> Any:
    """Validate every string in a JSON-like value without changing the payload."""

    if isinstance(value, str):
        return ensure_text_integrity(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            ensure_text_tree(key)
            ensure_text_tree(item)
        return value
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            ensure_text_tree(item)
    return value

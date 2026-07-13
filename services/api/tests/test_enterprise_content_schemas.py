from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.enterprise_schemas import OverrideWriteRequest


def test_custom_override_allows_only_presentation_fields() -> None:
    payload = OverrideWriteRequest.model_validate(
        {"mode": "custom", "custom_display": {"title": "名片专属标题", "sort_order": 3}}
    )
    assert payload.custom_display is not None
    assert payload.custom_display.as_dict() == {"title": "名片专属标题", "sort_order": 3}


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "custom"},
        {"mode": "hidden", "custom_display": {"title": "不允许"}},
        {"mode": "custom", "custom_display": {"detail": "不得覆盖源正文"}},
        {"mode": "custom", "custom_display": {"visibility": "internal"}},
    ],
)
def test_override_never_accepts_source_body_or_visibility(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OverrideWriteRequest.model_validate(payload)

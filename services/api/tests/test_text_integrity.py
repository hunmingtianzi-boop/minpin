from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.admin_schemas import PutKnowledgeDocumentRequest
from app.api.knowledge_ops_schemas import FaqWriteRequest
from app.core.text_integrity import ensure_text_integrity


def _latin1_mojibake(value: str) -> str:
    return value.encode("utf-8").decode("latin-1")


def test_clean_chinese_text_is_preserved() -> None:
    value = "企业可以怎样与拓浙 AI 集团合作？"

    assert ensure_text_integrity(value) == value


@pytest.mark.parametrize(
    "payload",
    [
        {
            "question": _latin1_mojibake("企业如何合作？"),
            "answer": "请先提交具体场景。",
        },
        {
            "question": "企业如何合作？",
            "answer": _latin1_mojibake("请先提交具体场景。"),
        },
    ],
)
def test_faq_write_rejects_utf8_text_decoded_as_latin1(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="forbidden control character"):
        FaqWriteRequest.model_validate(payload)


def test_knowledge_metadata_rejects_corrupted_source_label() -> None:
    with pytest.raises(ValidationError, match="forbidden control character"):
        PutKnowledgeDocumentRequest(
            raw_text="正常知识内容",
            title="正常问题",
            metadata={"source_label": _latin1_mojibake("企业 FAQ")},
        )


def test_replacement_character_is_rejected() -> None:
    with pytest.raises(ValueError, match="replacement character"):
        ensure_text_integrity("损坏文本\ufffd")


def test_latin1_mojibake_without_control_characters_is_rejected() -> None:
    with pytest.raises(ValueError, match="decoded as Latin-1"):
        ensure_text_integrity(_latin1_mojibake("\u9fff"))

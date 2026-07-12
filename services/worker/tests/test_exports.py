from __future__ import annotations

import csv
import io

from cf_worker.repository import (
    PostgresOutboxRepository,
    _csv_content,
    _safe_csv_cell,
)


def test_csv_is_excel_utf8_and_neutralizes_formula_injection() -> None:
    content = _csv_content(
        "leads",
        [
            {
                "id": "lead-1",
                "card_name": "示例名片",
                "status": "new",
                "priority": "high",
                "interest_tags": ["AI", "生态"],
                "name": "=HYPERLINK(\"https://evil.invalid\")",
                "mobile": "+123456789",
                "email": " user@example.com",
                "wechat": "\t=cmd|' /C calc'!A0",
                "company_name": " @SUM(1,2)",
                "requirement": "-2+3",
            }
        ],
    )

    assert content.startswith("\ufeff")
    assert "\r\n" in content
    parsed = list(csv.DictReader(io.StringIO(content.removeprefix("\ufeff"))))
    row = parsed[0]
    assert row["name"].startswith("'=")
    assert row["mobile"].startswith("'+")
    assert row["wechat"].startswith("'\t")
    assert row["company_name"].startswith("' @")
    assert row["requirement"].startswith("'-")
    assert row["email"] == " user@example.com"


def test_formula_guard_handles_whitespace_and_plain_values() -> None:
    assert _safe_csv_cell("   =1+1") == "'   =1+1"
    assert _safe_csv_cell("@SUM(A1:A2)") == "'@SUM(A1:A2)"
    assert _safe_csv_cell("普通文本") == "普通文本"
    assert _safe_csv_cell(None) == ""


def test_conversation_export_redacts_contact_data_unless_sensitive_is_authorized() -> None:
    repository = object.__new__(PostgresOutboxRepository)
    content = "联系 13800138000 或 visitor@example.com"

    masked = repository._present_export_row(
        "conversations", {"content": content}, include_sensitive=False
    )
    sensitive = repository._present_export_row(
        "conversations", {"content": content}, include_sensitive=True
    )

    assert masked["content"] == "联系 [redacted-phone] 或 [redacted-email]"
    assert sensitive["content"] == content

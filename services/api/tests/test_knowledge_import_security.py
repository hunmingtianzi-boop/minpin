from __future__ import annotations

import io
import zipfile

import pytest
from docx import Document
from pypdf import PdfWriter

from app.services.knowledge_import import (
    KnowledgeImportError,
    parse_payload,
    safe_file_name,
    validate_upload,
)


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_csv_import_produces_drafts_and_rejects_formula_injection() -> None:
    payload = "title,raw_text,visibility\n产品说明,正文内容,internal\n".encode()
    assert validate_upload("docs.csv", "text/csv", payload) == "csv"
    assert parse_payload("csv", "docs.csv", payload)[0].visibility == "internal"

    with pytest.raises(KnowledgeImportError, match="IMPORT_DANGEROUS_VALUE"):
        parse_payload("csv", "docs.csv", b"title,raw_text\n=cmd,content\n")


def test_csv_import_rejects_extra_columns_and_oversized_cells() -> None:
    with pytest.raises(KnowledgeImportError, match="IMPORT_CSV_COLUMNS"):
        parse_payload("csv", "docs.csv", b"title,raw_text\nA,content,unexpected\n")

    oversized = b"raw_text\n" + (b"a" * 100_001) + b"\n"
    with pytest.raises(KnowledgeImportError, match="IMPORT_CSV_CELL_TOO_LARGE"):
        parse_payload("csv", "docs.csv", oversized)


def test_docx_is_parsed_but_macro_and_archive_paths_are_rejected() -> None:
    payload = _docx_bytes("企业安全知识")
    assert (
        validate_upload(
            "guide.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            payload,
        )
        == "docx"
    )
    assert parse_payload("docx", "guide.docx", payload)[0].raw_text == "企业安全知识"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("../vbaProject.bin", b"macro")
    with pytest.raises(KnowledgeImportError, match="IMPORT_ARCHIVE_PATH"):
        validate_upload(
            "bad.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
        )


def test_encrypted_pdf_and_mime_magic_mismatches_are_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(KnowledgeImportError, match="IMPORT_ENCRYPTED_PDF"):
        parse_payload("pdf", "secret.pdf", buffer.getvalue())

    with pytest.raises(KnowledgeImportError, match="IMPORT_MIME_MISMATCH"):
        validate_upload("file.pdf", "text/plain", b"%PDF-1.7")
    with pytest.raises(KnowledgeImportError, match="IMPORT_MAGIC_MISMATCH"):
        validate_upload("file.pdf", "application/pdf", b"not-a-pdf")


@pytest.mark.parametrize("name", ["../file.csv", "folder/file.csv", "folder\\file.csv", ""])
def test_unsafe_file_names_are_rejected(name: str) -> None:
    with pytest.raises(KnowledgeImportError, match="IMPORT_UNSAFE_FILENAME"):
        safe_file_name(name)

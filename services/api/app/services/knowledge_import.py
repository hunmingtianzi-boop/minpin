from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from docx import Document
from pypdf import PdfReader

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_BATCH_BYTES = 25 * 1024 * 1024
MAX_FILES = 5
MAX_CSV_ROWS = 1_000
MAX_CSV_COLUMNS = 16
MAX_CSV_CELL_CHARS = 100_000
MAX_TEXT_CHARS = 1_000_000
MAX_PDF_PAGES = 500
MAX_ARCHIVE_ENTRIES = 2_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 20 * 1024 * 1024
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MIMES = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
}


class KnowledgeImportError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImportDraft:
    title: str
    raw_text: str
    visibility: Literal["public", "authenticated", "internal"]


def safe_file_name(value: str | None) -> str:
    name = (value or "").strip()
    if not name or name in {".", ".."} or PurePath(name).name != name:
        raise KnowledgeImportError("IMPORT_UNSAFE_FILENAME")
    if any(character in name for character in ("/", "\\", "\x00")):
        raise KnowledgeImportError("IMPORT_UNSAFE_FILENAME")
    return name[:255]


def validate_upload(name: str, content_type: str | None, payload: bytes) -> str:
    if not payload:
        raise KnowledgeImportError("IMPORT_EMPTY_FILE")
    if len(payload) > MAX_FILE_BYTES:
        raise KnowledgeImportError("IMPORT_FILE_TOO_LARGE")
    extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
    if extension not in _MIMES:
        raise KnowledgeImportError("IMPORT_UNSUPPORTED_TYPE")
    normalized_mime = (content_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime not in _MIMES[extension]:
        raise KnowledgeImportError("IMPORT_MIME_MISMATCH")
    if extension == "pdf" and not payload.startswith(b"%PDF-"):
        raise KnowledgeImportError("IMPORT_MAGIC_MISMATCH")
    if extension == "docx":
        if not payload.startswith(b"PK\x03\x04"):
            raise KnowledgeImportError("IMPORT_MAGIC_MISMATCH")
        _validate_docx_archive(payload)
    if extension == "csv" and (payload.startswith(b"%PDF-") or payload.startswith(b"PK\x03\x04")):
        raise KnowledgeImportError("IMPORT_MAGIC_MISMATCH")
    return extension


def parse_payload(source_type: str, file_name: str, payload: bytes) -> list[ImportDraft]:
    if source_type == "pdf":
        return [_parse_pdf(file_name, payload)]
    if source_type == "docx":
        return [_parse_docx(file_name, payload)]
    if source_type == "csv":
        return _parse_csv(payload)
    raise KnowledgeImportError("IMPORT_UNSUPPORTED_TYPE")


def encode_draft(draft: ImportDraft) -> bytes:
    return json.dumps(
        {"title": draft.title, "raw_text": draft.raw_text, "visibility": draft.visibility},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_draft(payload: bytes) -> ImportDraft:
    try:
        value = json.loads(payload.decode("utf-8"))
        return _validated_draft(value["title"], value["raw_text"], value["visibility"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeImportError("IMPORT_PAYLOAD_INVALID") from exc


def _parse_pdf(file_name: str, payload: bytes) -> ImportDraft:
    try:
        reader = PdfReader(io.BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise KnowledgeImportError("IMPORT_ENCRYPTED_PDF")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise KnowledgeImportError("IMPORT_PDF_TOO_MANY_PAGES")
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except KnowledgeImportError:
        raise
    except Exception as exc:
        raise KnowledgeImportError("IMPORT_PDF_INVALID") from exc
    return _validated_draft(file_name.rsplit(".", 1)[0], text, "public")


def _parse_docx(file_name: str, payload: bytes) -> ImportDraft:
    _validate_docx_archive(payload)
    try:
        document = Document(io.BytesIO(payload))
        parts = [
            paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
        ]
        for table in document.tables:
            for row in table.rows:
                line = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if line:
                    parts.append(line)
    except Exception as exc:
        raise KnowledgeImportError("IMPORT_DOCX_INVALID") from exc
    return _validated_draft(file_name.rsplit(".", 1)[0], "\n\n".join(parts), "public")


def _parse_csv(payload: bytes) -> list[ImportDraft]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise KnowledgeImportError("IMPORT_CSV_ENCODING") from exc
    if "\x00" in text:
        raise KnowledgeImportError("IMPORT_CSV_INVALID")
    drafts: list[ImportDraft] = []
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_fields = [
            str(field).strip() for field in (reader.fieldnames or []) if field is not None
        ]
        fields = set(raw_fields)
        if len(raw_fields) > MAX_CSV_COLUMNS or len(raw_fields) != len(fields):
            raise KnowledgeImportError("IMPORT_CSV_HEADERS")
        if "raw_text" not in fields or fields - {"title", "raw_text", "visibility"}:
            raise KnowledgeImportError("IMPORT_CSV_HEADERS")
        for row in reader:
            if len(drafts) >= MAX_CSV_ROWS:
                raise KnowledgeImportError("IMPORT_CSV_TOO_MANY_ROWS")
            if None in row:
                raise KnowledgeImportError("IMPORT_CSV_COLUMNS")
            values = {str(key).strip(): value or "" for key, value in row.items()}
            for value in values.values():
                if len(value) > MAX_CSV_CELL_CHARS:
                    raise KnowledgeImportError("IMPORT_CSV_CELL_TOO_LARGE")
                if value.lstrip().startswith(_DANGEROUS_PREFIXES):
                    raise KnowledgeImportError("IMPORT_DANGEROUS_VALUE")
            drafts.append(
                _validated_draft(
                    values.get("title") or f"批量导入第 {reader.line_num - 1} 条",
                    values.get("raw_text", ""),
                    values.get("visibility") or "public",
                )
            )
    except csv.Error as exc:
        raise KnowledgeImportError("IMPORT_CSV_INVALID") from exc
    if not drafts:
        raise KnowledgeImportError("IMPORT_EMPTY_TEXT")
    return drafts


def _validated_draft(title: str, raw_text: str, visibility: str) -> ImportDraft:
    normalized_title = str(title).strip()
    normalized_text = str(raw_text).strip()
    normalized_visibility = str(visibility).strip().casefold()
    if not normalized_title or len(normalized_title) > 500:
        raise KnowledgeImportError("IMPORT_TITLE_INVALID")
    if not normalized_text:
        raise KnowledgeImportError("IMPORT_EMPTY_TEXT")
    if len(normalized_text) > MAX_TEXT_CHARS:
        raise KnowledgeImportError("IMPORT_TEXT_TOO_LARGE")
    if _CONTROL_RE.search(normalized_title) or _CONTROL_RE.search(normalized_text):
        raise KnowledgeImportError("IMPORT_DANGEROUS_VALUE")
    if normalized_title.lstrip().startswith(_DANGEROUS_PREFIXES):
        raise KnowledgeImportError("IMPORT_DANGEROUS_VALUE")
    if normalized_visibility not in {"public", "authenticated", "internal"}:
        raise KnowledgeImportError("IMPORT_VISIBILITY_INVALID")
    return ImportDraft(normalized_title, normalized_text, normalized_visibility)  # type: ignore[arg-type]


def _validate_docx_archive(payload: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise KnowledgeImportError("IMPORT_ARCHIVE_LIMIT")
            if sum(item.file_size for item in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise KnowledgeImportError("IMPORT_ARCHIVE_LIMIT")
            names = [item.filename for item in infos]
            if "word/document.xml" not in names:
                raise KnowledgeImportError("IMPORT_DOCX_INVALID")
            for item in infos:
                name = item.filename
                if item.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                    raise KnowledgeImportError("IMPORT_ARCHIVE_LIMIT")
                if item.file_size > 1_000_000 and item.compress_size * 100 < item.file_size:
                    raise KnowledgeImportError("IMPORT_ARCHIVE_LIMIT")
                path = PurePath(name.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise KnowledgeImportError("IMPORT_ARCHIVE_PATH")
                lowered = name.casefold()
                if lowered.endswith(("vbaproject.bin", ".docm")) or "macros" in lowered:
                    raise KnowledgeImportError("IMPORT_MACRO_DOCUMENT")
    except KnowledgeImportError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise KnowledgeImportError("IMPORT_DOCX_INVALID") from exc


__all__ = [
    "ImportDraft",
    "KnowledgeImportError",
    "MAX_BATCH_BYTES",
    "MAX_FILES",
    "decode_draft",
    "encode_draft",
    "parse_payload",
    "safe_file_name",
    "validate_upload",
]

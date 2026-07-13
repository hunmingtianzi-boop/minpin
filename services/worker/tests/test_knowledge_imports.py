from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace

import pytest
from app.core.pii import PiiCipher
from app.services.knowledge_import import KnowledgeImportError

from cf_worker.config import WorkerSettings
from cf_worker.knowledge_imports import ClaimedKnowledgeImport, KnowledgeImportExecutor


class _Repository:
    def __init__(self) -> None:
        self.result = None
        self.actions: list[str] = []

    async def create_knowledge_import_draft(self, claim, draft, chunks):
        self.actions.append("draft")
        self.result = claim, draft, chunks
        return uuid.uuid4(), uuid.uuid4(), False

    async def publish_knowledge_import(self, *args, **kwargs) -> None:
        self.actions.append("publish")

    async def complete_knowledge_import(self, *args, **kwargs) -> None:
        self.actions.append("complete")
        return None


def _claim(settings: WorkerSettings, plaintext: bytes) -> ClaimedKnowledgeImport:
    cipher = PiiCipher.from_settings(settings)
    return ClaimedKnowledgeImport(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        file_name="bulk.csv",
        source_type="csv",
        content_type="text/csv",
        row_number=2,
        auto_publish=False,
        payload_ciphertext=cipher.encrypt_bytes(plaintext),
        payload_sha256=hashlib.sha256(plaintext).hexdigest(),
        encryption_key_ref=cipher.key_ref,
        attempts=1,
        max_attempts=6,
        requested_by=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_executor_verifies_and_creates_unpublished_draft_chunks() -> None:
    settings = WorkerSettings()
    repository = _Repository()
    plaintext = json.dumps(
        {"title": "导入文档", "raw_text": "需要审核的正文", "visibility": "internal"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    await KnowledgeImportExecutor(repository, settings).execute(_claim(settings, plaintext))
    assert repository.result is not None
    _, draft, chunks = repository.result
    assert draft.title == "导入文档"
    assert chunks == ("需要审核的正文",)


@pytest.mark.asyncio
async def test_executor_rejects_tampered_payload_before_database_write() -> None:
    settings = WorkerSettings()
    repository = _Repository()
    claim = _claim(settings, b'{"title":"a","raw_text":"b","visibility":"public"}')
    claim = replace(claim, payload_sha256="0" * 64)
    with pytest.raises(KnowledgeImportError, match="IMPORT_PAYLOAD_TAMPERED"):
        await KnowledgeImportExecutor(repository, settings).execute(claim)
    assert repository.result is None


def test_queue_cipher_round_trips_non_utf8_office_bytes() -> None:
    cipher = PiiCipher.from_settings(WorkerSettings())
    original = b"PK\x03\x04\x00\xff\x00office"
    assert cipher.decrypt_bytes(cipher.encrypt_bytes(original)) == original


@pytest.mark.asyncio
async def test_auto_publish_waits_for_existing_publish_pipeline_before_completion() -> None:
    settings = WorkerSettings()
    repository = _Repository()
    claim = _claim(settings, b'{"title":"a","raw_text":"b","visibility":"public"}')
    claim = replace(claim, auto_publish=True)

    await KnowledgeImportExecutor(repository, settings).execute(claim)

    assert repository.actions == ["draft", "publish", "complete"]

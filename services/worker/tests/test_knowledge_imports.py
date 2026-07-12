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

    async def create_knowledge_import_draft(self, claim, draft, chunks) -> None:
        self.result = claim, draft, chunks


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
        payload_ciphertext=cipher.encrypt(plaintext.decode()),
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

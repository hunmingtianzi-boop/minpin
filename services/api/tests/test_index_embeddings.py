from __future__ import annotations

import uuid

from app.cli.index_embeddings import (
    index_job_id,
    model_fingerprint,
    target_chunk_id,
    target_version_id,
)


def test_embedding_index_ids_are_deterministic_and_model_revision_scoped() -> None:
    source = uuid.UUID("9a1b7415-bf25-4dce-80e4-32865b2bb593")
    fingerprint = model_fingerprint("intfloat/multilingual-e5-large", 1024)
    target = target_version_id(source, fingerprint)

    assert target == target_version_id(source, fingerprint)
    assert target != target_version_id(source, model_fingerprint("other/model", 1024))
    assert target_chunk_id(target, 0) == target_chunk_id(target, 0)
    assert target_chunk_id(target, 0) != target_chunk_id(target, 1)
    assert index_job_id(target, "intfloat/multilingual-e5-large") == index_job_id(
        target, "intfloat/multilingual-e5-large"
    )

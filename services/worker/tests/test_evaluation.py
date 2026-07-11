from __future__ import annotations

import uuid
from typing import Any

import pytest

import cf_worker.evaluation as evaluation_module
from cf_worker.config import WorkerSettings
from cf_worker.domain import PermanentEventError
from cf_worker.evaluation import ApiEvaluationRunner


@pytest.mark.asyncio
async def test_evaluation_uses_allowlisted_dataset_and_redacts_report(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "acme.v2.json"
    dataset.write_text("{}", encoding="utf-8")

    async def fake_run_evaluation(**_kwargs: Any) -> dict[str, Any]:
        return {
            "dataset": "C:/secret/path/acme.v2.json",
            "suite_version": "2",
            "gate": {"passed": False},
            "observations": [
                {"case_id": "case-1", "debug": "person@example.com sk-secret-token-value"}
            ],
        }

    monkeypatch.setattr(evaluation_module, "run_evaluation", fake_run_evaluation)
    runner = ApiEvaluationRunner(
        WorkerSettings(
            evaluation_dataset_dir=tmp_path,
            evaluation_suite_version="v2",
        )
    )
    report = await runner.run(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        tenant_slug="acme",
    )
    rendered = str(report)
    assert report["dataset"] == "acme.v2.json"
    assert "person@example.com" not in rendered
    assert "sk-secret-token-value" not in rendered
    assert "C:/secret/path" not in rendered


@pytest.mark.asyncio
async def test_evaluation_rejects_slug_path_traversal(tmp_path) -> None:
    runner = ApiEvaluationRunner(WorkerSettings(evaluation_dataset_dir=tmp_path))
    with pytest.raises(PermanentEventError, match="invalid_tenant_slug"):
        await runner.run(
            tenant_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            tenant_slug="../escape",
        )

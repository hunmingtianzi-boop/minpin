from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.cli.evaluate_rag import run_evaluation
from app.core.config import Settings as ApiSettings
from app.core.redaction import redact_sensitive_text

from cf_worker.config import WorkerSettings
from cf_worker.domain import PermanentEventError

_SAFE_TENANT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_MAX_REPORT_BYTES = 2_000_000


class ApiEvaluationRunner:
    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings

    async def run(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        tenant_slug: str,
    ) -> dict[str, Any]:
        dataset = self._dataset_for(tenant_slug)
        api_settings = ApiSettings(database_url=self._settings.database_url)
        report = await run_evaluation(
            dataset=dataset,
            settings=api_settings,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        report["dataset"] = dataset.name
        sanitized = _redact_json(report)
        rendered = json.dumps(
            sanitized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(rendered.encode("utf-8")) > _MAX_REPORT_BYTES:
            raise PermanentEventError("evaluation_report_too_large")
        return sanitized

    def _dataset_for(self, tenant_slug: str) -> Path:
        if not _SAFE_TENANT_SLUG.fullmatch(tenant_slug):
            raise PermanentEventError("invalid_tenant_slug")
        root = self._settings.evaluation_dataset_dir.resolve()
        candidates = (
            root / f"{tenant_slug}.{self._settings.evaluation_suite_version}.json",
            root / f"{tenant_slug}.v1.json",
            root / "template.v1.json",
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.parent == root and resolved.is_file():
                return resolved
        raise PermanentEventError("evaluation_dataset_missing")


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key)[:160]: _redact_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value).content[:20_000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_sensitive_text(str(value)).content[:2_000]


__all__ = ["ApiEvaluationRunner"]

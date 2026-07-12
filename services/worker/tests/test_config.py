from __future__ import annotations

import pytest
from pydantic import ValidationError

from cf_worker.config import WorkerSettings


def test_worker_secrets_are_not_exposed_by_repr() -> None:
    settings = WorkerSettings(
        worker_database_url="postgresql+asyncpg://worker:super-secret@localhost/db",
        celery_broker_url="redis://:broker-secret@localhost:6379/1",
    )
    rendered = repr(settings)
    assert "super-secret" not in rendered
    assert "broker-secret" not in rendered
    assert "**********" in rendered


def test_local_default_database_uses_explicit_ipv4_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_DATABASE_URL", raising=False)

    settings = WorkerSettings(_env_file=None)

    assert "@127.0.0.1:5432/" in settings.database_url


def test_heartbeat_must_fit_inside_lease() -> None:
    with pytest.raises(ValidationError):
        WorkerSettings(outbox_lease_seconds=60, outbox_heartbeat_seconds=30)


def test_production_rejects_local_worker_identity() -> None:
    with pytest.raises(ValidationError):
        WorkerSettings(app_env="production")

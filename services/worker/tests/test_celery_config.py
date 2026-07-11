from __future__ import annotations

from cf_worker.celery_app import celery_app, settings


def test_celery_uses_redis_late_ack_and_visibility_larger_than_database_lease() -> None:
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert (
        celery_app.conf.broker_transport_options["visibility_timeout"]
        > settings.outbox_lease_seconds
    )
    assert "poll-postgresql-outbox" in celery_app.conf.beat_schedule

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from cf_worker import tasks


def test_periodic_database_failures_open_a_shared_cooldown(monkeypatch) -> None:
    now = 100.0
    calls = 0
    monkeypatch.setattr(tasks.time, "monotonic", lambda: now)
    tasks._database_paused_until = 0.0

    async def failing() -> int:
        nonlocal calls
        calls += 1
        raise SQLAlchemyError("database unavailable")

    assert tasks._run_database_poll("poll", failing) == 0
    assert calls == 1
    assert tasks._database_paused_until == 130.0

    async def succeeding() -> int:
        nonlocal calls
        calls += 1
        return 7

    assert tasks._run_database_poll("other_poll", succeeding) == 0
    assert calls == 1

    now = 131.0
    assert tasks._run_database_poll("poll", succeeding) == 7
    assert calls == 2
    assert tasks._database_paused_until == 0.0

from __future__ import annotations

from pathlib import Path

from cf_worker.repository import calculate_backoff_seconds, should_dead_letter

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "services/api/migrations/versions/20260711_0007_worker_outbox.py"


def test_backoff_is_exponential_and_capped() -> None:
    assert calculate_backoff_seconds(attempt=1, base_seconds=5, maximum_seconds=900) == 5
    assert calculate_backoff_seconds(attempt=2, base_seconds=5, maximum_seconds=900) == 10
    assert calculate_backoff_seconds(attempt=20, base_seconds=5, maximum_seconds=900) == 900


def test_dead_letter_policy_handles_permanent_and_exhausted_events() -> None:
    assert should_dead_letter(attempt=1, max_attempts=6, permanent=True)
    assert should_dead_letter(attempt=6, max_attempts=6, permanent=False)
    assert not should_dead_letter(attempt=5, max_attempts=6, permanent=False)


def test_migration_enforces_skip_locked_leases_rls_and_worker_identity() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "for update skip locked" in sql
    assert "lease_expires_at" in sql
    assert "lock_token" in sql
    assert "security definer" in sql
    assert "set search_path = pg_catalog, public, app" in sql
    assert "outbox_deliveries" in sql
    assert "worker_job_results" in sql
    assert "force row level security" in sql
    assert "cf_ai_card_worker" in sql
    assert "bypassrls" not in sql

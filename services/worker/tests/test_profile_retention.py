from __future__ import annotations

from typing import Any

import pytest

from cf_worker.repository import PostgresOutboxRepository


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def scalar(self, statement: Any) -> int:
        self.statements.append(str(statement))
        return 7


class _Begin:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Engine:
    def __init__(self) -> None:
        self.connection = _Connection()

    def begin(self) -> _Begin:
        return _Begin(self.connection)


@pytest.mark.asyncio
async def test_retention_purge_calls_the_restricted_database_function() -> None:
    repository = object.__new__(PostgresOutboxRepository)
    engine = _Engine()
    repository._engine = engine  # type: ignore[attr-defined]  # noqa: SLF001

    deleted = await repository.purge_expired_visitor_profiles()

    assert deleted == 7
    assert engine.connection.statements == [
        "SELECT app.purge_expired_visitor_profiles()"
    ]

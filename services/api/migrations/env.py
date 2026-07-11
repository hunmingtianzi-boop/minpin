from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Enum, String, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def compare_column_type(
    _context: object,
    _inspected_column: object,
    _metadata_column: object,
    inspected_type: object,
    metadata_type: object,
) -> bool | None:
    """Treat reflected VARCHAR + CHECK enums as the declared non-native enum.

    PostgreSQL reflection intentionally exposes the storage type rather than
    reconstructing SQLAlchemy's Python enum wrapper. The migration DDL and
    database contract tests own the CHECK constraints and permitted values.
    """

    if isinstance(metadata_type, Enum) and isinstance(inspected_type, String):
        return False
    return None


def _index_column_names(value: object) -> tuple[str, ...]:
    expressions = getattr(value, "expressions", ())
    result: list[str] = []
    for expression in expressions:
        current = getattr(expression, "element", expression)
        name = getattr(current, "name", None)
        if name is None:
            return ()
        result.append(str(name))
    return tuple(result)


def include_schema_object(
    obj: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    compare_to: object | None,
) -> bool:
    """Ignore only reflection-only ordering differences for the same index.

    A missing index still has ``compare_to=None`` and remains a migration drift.
    """

    if type_ == "index" and compare_to is not None and name == getattr(compare_to, "name", None):
        left = _index_column_names(obj)
        right = _index_column_names(compare_to)
        if left and left == right:
            return False
    return True


def database_url() -> str:
    settings = get_settings()
    return (
        os.getenv("MIGRATION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or settings.migration_database_url
        or settings.database_url
        or config.get_main_option("sqlalchemy.url")
    )


def migration_options() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "compare_type": compare_column_type,
        "compare_server_default": True,
        "include_object": include_schema_object,
        "include_schemas": True,
        "transaction_per_migration": True,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **migration_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **migration_options())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

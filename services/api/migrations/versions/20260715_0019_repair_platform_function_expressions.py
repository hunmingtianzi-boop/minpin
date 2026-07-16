"""Repair schema-qualified conditional expressions in platform functions.

Revision ID: 20260715_0019
Revises: 20260715_0018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260715_0019"
down_revision: str | None = "20260715_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # COALESCE and NULLIF are PostgreSQL conditional expressions, not ordinary
    # pg_catalog functions. Earlier platform migrations stored the qualified
    # spelling inside PL/pgSQL bodies, which fails only when those paths run.
    # Rebuild only affected functions in our private schema and preserve their
    # complete signatures, security attributes and configuration verbatim.
    op.execute(
        r"""
        DO $repair_platform_functions$
        DECLARE
          target record;
          corrected_definition text;
        BEGIN
          FOR target IN
            SELECT
              function_row.oid,
              pg_catalog.pg_get_functiondef(function_row.oid) AS definition
            FROM pg_catalog.pg_proc AS function_row
            JOIN pg_catalog.pg_namespace AS namespace_row
              ON namespace_row.oid = function_row.pronamespace
            WHERE namespace_row.nspname = 'app'
              AND function_row.prokind = 'f'
              AND (
                pg_catalog.strpos(
                  pg_catalog.pg_get_functiondef(function_row.oid),
                  'pg_catalog.coalesce'
                ) > 0
                OR pg_catalog.strpos(
                  pg_catalog.pg_get_functiondef(function_row.oid),
                  'pg_catalog.nullif'
                ) > 0
              )
            ORDER BY function_row.oid
          LOOP
            corrected_definition := pg_catalog.replace(
              pg_catalog.replace(
                target.definition,
                'pg_catalog.coalesce',
                'COALESCE'
              ),
              'pg_catalog.nullif',
              'NULLIF'
            );
            EXECUTE corrected_definition;
          END LOOP;

          IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_proc AS function_row
            JOIN pg_catalog.pg_namespace AS namespace_row
              ON namespace_row.oid = function_row.pronamespace
            WHERE namespace_row.nspname = 'app'
              AND function_row.prokind = 'f'
              AND (
                pg_catalog.strpos(
                  pg_catalog.pg_get_functiondef(function_row.oid),
                  'pg_catalog.coalesce'
                ) > 0
                OR pg_catalog.strpos(
                  pg_catalog.pg_get_functiondef(function_row.oid),
                  'pg_catalog.nullif'
                ) > 0
              )
          ) THEN
            RAISE EXCEPTION 'platform function expression repair was incomplete';
          END IF;
        END
        $repair_platform_functions$;
        """
    )


def downgrade() -> None:
    # The repair makes earlier intended functions executable. Restoring their
    # invalid spelling would break the 0018 application, so downgrade is a no-op.
    pass

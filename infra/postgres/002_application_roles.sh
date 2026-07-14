#!/bin/sh
set -eu

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${WORKER_DB_PASSWORD:?WORKER_DB_PASSWORD is required}"

# `format(... %L ...)` safely quotes the environment-injected password.  This
# keeps the application and Worker principals least-privileged without baking
# development passwords into a production image or database volume.
psql -U "${POSTGRES_USER:-postgres}" -v ON_ERROR_STOP=1 \
  --set=app_db_password="$APP_DB_PASSWORD" \
  --set=worker_db_password="$WORKER_DB_PASSWORD" <<'SQL'
SELECT format(
  'DO $role$ BEGIN
     IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''cf_ai_card_app'') THEN
       CREATE ROLE cf_ai_card_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
     ELSE
       ALTER ROLE cf_ai_card_app PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
     END IF;
   END $role$;',
  :'app_db_password',
  :'app_db_password'
) \gexec

SELECT format(
  'DO $role$ BEGIN
     IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''cf_ai_card_worker'') THEN
       CREATE ROLE cf_ai_card_worker LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
     ELSE
       ALTER ROLE cf_ai_card_worker PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
     END IF;
   END $role$;',
  :'worker_db_password',
  :'worker_db_password'
) \gexec

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM cf_ai_card_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO cf_ai_card_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM cf_ai_card_worker;
SQL

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Local-only runtime role. Production creates an equivalent least-privilege role
-- through the platform secret/identity system and never reuses the migration owner.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
    CREATE ROLE cf_ai_card_app
      LOGIN
      PASSWORD 'change-me-app-local-only'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
  END IF;
END
$$;

-- The asynchronous worker has a separate login and only receives the table
-- grants/functions required by worker migrations. It is deliberately not a
-- superuser and cannot bypass RLS.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
    CREATE ROLE cf_ai_card_worker
      LOGIN
      PASSWORD 'change-me-worker-local-only'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
  END IF;
END
$$;

-- Table privileges are granted explicitly by each migration.  A blanket
-- default grant would silently give future sensitive tables UPDATE/DELETE.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM cf_ai_card_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO cf_ai_card_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM cf_ai_card_worker;

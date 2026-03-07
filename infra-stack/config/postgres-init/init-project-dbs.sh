#!/bin/bash
# init-project-dbs.sh
# Runs on first ai-postgres startup. Creates per-project databases and users
# so each application stack can share the global postgres instance.
# To add a new project: add a block below and restart ai-postgres (first-run only).
# Existing data is preserved — postgres only runs init scripts on a fresh volume.

set -e

# ── brandmatik ────────────────────────────────────────────────────────────────
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'brandmatik') THEN
      CREATE USER brandmatik WITH PASSWORD 'brandmatik123';
    END IF;
  END
  \$\$;
  CREATE DATABASE brandmatik OWNER brandmatik;
  GRANT ALL PRIVILEGES ON DATABASE brandmatik TO brandmatik;
EOSQL

# ── taskflow ──────────────────────────────────────────────────────────────────
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'taskflow') THEN
      CREATE USER taskflow WITH PASSWORD 'taskflow123';
    END IF;
  END
  \$\$;
  CREATE DATABASE taskflow OWNER taskflow;
  GRANT ALL PRIVILEGES ON DATABASE taskflow TO taskflow;
EOSQL

# ── Add more projects below as needed ─────────────────────────────────────────
# psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
#   CREATE USER myapp WITH PASSWORD 'myapp123';
#   CREATE DATABASE myapp OWNER myapp;
#   GRANT ALL PRIVILEGES ON DATABASE myapp TO myapp;
# EOSQL

#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "database"

# Role and database "varsis", created only if missing. PostgreSQL listens on localhost only (Ubuntu's default
# listen_addresses); the backend logs in with the generated password over TCP 127.0.0.1.
#
# Postgres has no CREATE ROLE IF NOT EXISTS, so a DO block checks first. The here-document is unquoted, so bash
# fills in $DB_PASSWORD; \$\$ is escaped so Postgres gets $$ (its quote marker for the block).
sudo -u postgres psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'varsis') THEN
    CREATE ROLE varsis LOGIN PASSWORD '$DB_PASSWORD';
  END IF;
END \$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='varsis'" | grep -q 1; then
    sudo -u postgres createdb -O varsis varsis
fi

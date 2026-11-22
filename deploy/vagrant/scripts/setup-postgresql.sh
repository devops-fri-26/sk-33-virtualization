#!/bin/bash

set -euo pipefail

# Role and database "varsis", created only if they don't exist yet.
#
# No password: the backend connects over PostgreSQL's local Unix socket (/run/postgresql), where Ubuntu's default
# pg_hba.conf uses "peer" authentication: the operating system user (varsis) must match the database role (varsis).
# Nothing to leak, and PostgreSQL still listens on localhost only (Ubuntu's default listen_addresses).

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='varsis'" | grep -q 1; then
    echo "PostgreSQL role varsis already exists"
else
    sudo -u postgres createuser varsis
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='varsis'" | grep -q 1; then
    echo "PostgreSQL database varsis already exists"
else
    sudo -u postgres createdb -O varsis varsis
fi

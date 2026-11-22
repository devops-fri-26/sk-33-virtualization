#!/bin/bash

set -euo pipefail

SECRETS=/etc/varsis/secrets.env
ENV=/etc/varsis/backend.env

# SECRET_KEY signs session cookies and email links. Generated once, on the VM: it is never in the repository, and
# re-provisioning keeps it (otherwise everyone would be logged out).
if [ ! -f "$SECRETS" ]; then
    install -o root -g root -m 600 /dev/null "$SECRETS"
    echo "SECRET_KEY=$(openssl rand -hex 32)" > "$SECRETS"
fi
. "$SECRETS"

# The backend's settings (read by the systemd service). Readable by the varsis group only.
install -o root -g varsis -m 640 /dev/null "$ENV"
cat > "$ENV" <<EOF
# Unix socket, peer authentication: no password (see setup-postgresql.sh)
DATABASE_URL=postgresql+asyncpg://varsis@/varsis?host=/run/postgresql
SECRET_KEY=$SECRET_KEY
# The address in the browser: links in mails use it, and https makes the session cookie Secure
APP_URL=https://localhost:8443
ADMIN_EMAILS=${ADMIN_EMAILS:-}
DEFAULT_QUOTA_GB=10
# All mail goes to Mailpit (setup-mailpit.sh)
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USER=
SMTP_PASS=
SMTP_FROM=varsis@localhost
SMTP_TLS=false
MUSIC_DIR=/var/lib/varsis/music
COVERS_DIR=/var/lib/varsis/covers
EOF

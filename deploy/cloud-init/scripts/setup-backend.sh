#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "backend"

# uv (installed once with pipx, for all users) installs exactly the versions in uv.lock (--frozen), without dev
# tools, with Python 3.13 from apt (no downloaded Python). Bytecode is compiled now: the sandboxed service can't
# write it later.
command -v uv >/dev/null || PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install uv
cd /opt/varsis/backend
UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 uv sync --frozen --no-dev --python python3.13

# With Mailpit, every mail goes to it instead of the SMTP_* settings.
if [ "${MAILPIT:-false}" = "true" ]; then
    SMTP_HOST=127.0.0.1 SMTP_PORT=1025 SMTP_USER= SMTP_PASS= SMTP_TLS=false
fi

# Data folders, owned by the service user (created by cloud-init's users:). 750: other users can't read the music.
install -d -o varsis -g varsis -m 0750 /var/lib/varsis /var/lib/varsis/music /var/lib/varsis/covers

# The backend's settings, read by systemd (as root) from the service's EnvironmentFile. 600: contains secrets.
umask 077
cat > /etc/varsis/backend.env <<ENV
DATABASE_URL=postgresql+asyncpg://varsis:$DB_PASSWORD@127.0.0.1:5432/varsis
SECRET_KEY=$SECRET_KEY
APP_URL=https://$SITE
ADMIN_EMAILS=$ADMIN_EMAILS
DEFAULT_QUOTA_GB=$DEFAULT_QUOTA_GB
SMTP_HOST=${SMTP_HOST:-localhost}
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS
SMTP_FROM=$SMTP_FROM
SMTP_TLS=$SMTP_TLS
MUSIC_DIR=/var/lib/varsis/music
COVERS_DIR=/var/lib/varsis/covers
ENV
umask 022

install -m 644 "$FILES/varsis-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now varsis-backend
systemctl restart varsis-backend # pick up new code and settings when run again

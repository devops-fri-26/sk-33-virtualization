#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"

# Testing only (MAILPIT=true): Mailpit catches every mail the app sends. Off: the service is stopped and disabled.
MAILPIT_VERSION=v1.33.0

if [ "${MAILPIT:-false}" != "true" ]; then
    systemctl disable --now mailpit 2>/dev/null || true
    exit 0
fi

log "mailpit $MAILPIT_VERSION"
# Not packaged in apt: a pinned release from GitHub, downloaded only if this version isn't installed yet.
if [ "$(/usr/local/bin/mailpit version 2>/dev/null | awk '{print $2}')" != "$MAILPIT_VERSION" ]; then
    curl -fsSL "https://github.com/axllent/mailpit/releases/download/$MAILPIT_VERSION/mailpit-linux-$(dpkg --print-architecture).tar.gz" \
        | tar -xz -C /usr/local/bin mailpit
fi

# Password for the inbox at /mailpit/ (start-caddy.sh puts it behind basic auth), generated once.
if [ -z "${MAILPIT_PASSWORD:-}" ]; then
    (umask 077; echo "MAILPIT_PASSWORD=$(openssl rand -hex 16)" >> /etc/varsis/secrets.env)
fi

install -m 644 "$FILES/mailpit.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mailpit

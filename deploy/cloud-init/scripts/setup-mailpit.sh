#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"

# Testing only (MAILPIT=true): Mailpit catches every mail the app sends. Off: the service is stopped and disabled.
MAILPIT_VERSION=v1.33.0
# SHA-256 of that release's mailpit-linux-amd64.tar.gz (GitHub shows it next to the file on the release page). A
# download that doesn't match (replaced or damaged) stops the setup before anything is installed. amd64 only, like
# our VMs: another architecture needs its own file and hash.
MAILPIT_SHA256=d0ec50080cbf3e7c1fa2cda2ee68125d7894175811084b1f8f47c6cfc6f487c8

if [ "${MAILPIT:-false}" != "true" ]; then
    systemctl disable --now mailpit 2>/dev/null || true
    exit 0
fi

log "mailpit $MAILPIT_VERSION"
# Not packaged in apt: a pinned release from GitHub, downloaded only if this version isn't installed yet. The version
# is the 2nd word of the first line of `mailpit version` (later lines may announce a newer release).
if [ "$(/usr/local/bin/mailpit version 2>/dev/null | awk 'NR==1{print $2}')" != "$MAILPIT_VERSION" ]; then
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL -o "$tmp" "https://github.com/axllent/mailpit/releases/download/$MAILPIT_VERSION/mailpit-linux-amd64.tar.gz"
    echo "$MAILPIT_SHA256  $tmp" | sha256sum -c -
    tar -xzf "$tmp" -C /usr/local/bin mailpit
fi

# Password for the inbox at /mailpit/ (start-caddy.sh puts it behind basic auth), generated once.
if [ -z "${MAILPIT_PASSWORD:-}" ]; then
    (umask 077; echo "MAILPIT_PASSWORD=$(openssl rand -hex 16)" >> /etc/varsis/secrets.env)
fi

install -m 644 "$FILES/mailpit.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mailpit

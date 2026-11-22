#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "firewall"

# SSH, HTTP (certificate checks + redirect to https), HTTPS incl. HTTP/3 (UDP). Everything else stays closed; the
# backend, PostgreSQL and Mailpit listen on 127.0.0.1 anyway. SSH is allowed before enabling, so it can't lock you out.
ufw allow 22/tcp # by port: minimal images (e.g. Incus) have no OpenSSH ufw profile
ufw allow 80/tcp
ufw allow 443
ufw --force enable

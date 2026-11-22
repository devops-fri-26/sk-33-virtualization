#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"

# If something here fails, the script fails, so cloud-init reports the deployment as failed instead of "done" with a
# broken app.

# 1. The backend creates its database tables at startup: give it up to a minute.
for i in $(seq 30); do
    if curl -fs http://127.0.0.1:8000/api/health >/dev/null; then
        break
    fi
    if [ "$i" = 30 ]; then
        log "backend not healthy: journalctl -u varsis-backend"
        exit 1
    fi
    sleep 2
done

# 2. Caddy: plain http for the site's name must get Caddy's redirect to https (308), which shows that Caddy runs with
# our Caddyfile. Not checked over https: a Let's Encrypt certificate also needs DNS and the host's port forwards,
# which may be added after the VM was launched; Caddy keeps trying until then.
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $SITE_HOST" http://127.0.0.1/ || true)
if [ "$code" != 308 ]; then
    log "caddy didn't redirect http://$SITE_HOST to https (HTTP status: $code): journalctl -u caddy"
    exit 1
fi

log "done: https://$SITE"
